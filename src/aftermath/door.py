"""How far the generator is from a door, from one phone photo taken where the generator stands.

SAM 3.1 finds the door. Its height in pixels, measured down the middle of the mask, and the camera's focal length in
pixels give the distance by the pinhole model:

    distance = focal length in pixels × door height / door height in pixels.

The focal length comes from EXIF's 35 mm-equivalent focal length over the image diagonal (the 35 mm equivalent is
defined on the 43.27 mm diagonal of a 36 × 24 mm frame), so it holds for any phone and for downscaled copies.

Some photos carry no lens data: iPhone Safari's own camera leaves it out (seen Oct 29), and so do photos sent by
text. Those are measured as if taken at 1× through a 23 mm-equivalent lens, the widest 1× camera common on phones, so
a photo that was taken at 1× reads no farther than it is (an iPhone 15 Pro's, at 24 mm, about 4% closer; a zoomed-in
one closer still). A photo taken at 0.5× (about 13 mm) would read nearly twice as far as it is, so the rules don't
let such a distance count until the person says the camera was at 1×.

The door's height is an assumption: 80 in is the standard leaf in the US, and SAM outlines the leaf, not the frame.
The distance is proportional to the height assumed, so a door shorter than 80 in comes out too far away, the unsafe
direction (a taller one comes out too close). The person is asked to confirm the height, and a height they give
rescales the reading. Only doors are used as the reference: windows have no standard size.

The reading comes with an error range, and the safety rules use its low end. The range is ±6%. Six iPhone photos of
one double door, tape-measured at 10–30 ft on Oct 29, read 0.2–3.1% far with the leaf's 80 in (3–6% far with the
frame's 82.5 in). The range will be refined as more doors are measured. A photo that can't be measured honestly is
refused, with the reason, instead of measured badly.
"""

import math
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

FULL_FRAME_DIAGONAL_MM = math.hypot(36.0, 24.0)  # 43.27 mm
ASSUMED_FOCAL_35 = 23.0  # mm, for a photo with no lens data: the widest 1× camera common on phones (Samsung's 23 mm,
#                          iPhone Pros' 24 mm, other iPhones' 26 mm), so a 1× photo reads no farther than it is
INCH, FOOT = 0.0254, 0.3048  # m
ERROR = 0.06  # the measured error range, ± a share of the distance (see the module's docstring)
LEAF_IN = 80.0  # the standard US door leaf, 6 ft 8 in
EXIF_IFD, FOCAL_35, FOCAL, ZOOM, MAKE, MODEL = 0x8769, 0xA405, 0x920A, 0xA404, 0x010F, 0x0110
TILT_LIMIT_DEG = 8.0  # beyond this, the phone's tilt adds a few percent of error
SMALLEST_PX = 120  # a door shorter than this in the photo is too small to measure well


class Segmenter(Protocol):
    def segment(self, image_path: str | Path, phrases: list[str]) -> dict[str, list]: ...


@dataclass(frozen=True)
class Optics:
    focal_px: float
    source: str  # where the focal length came from, for the record
    camera: str
    zoom: float  # EXIF digital zoom ratio, 1 when absent
    assumed: bool = False  # the photo had no lens data: ASSUMED_FOCAL_35, as if taken at 1×


def optics(width: int, height: int, exif: Image.Exif, sensor_width_mm: float | None = None) -> Optics | None:
    """The focal length in pixels of an upright image of this size, from its EXIF; None when EXIF can't give it."""
    sub = exif.get_ifd(EXIF_IFD)
    camera = " ".join(str(exif[k]).strip() for k in (MAKE, MODEL) if k in exif) or "unknown camera"
    zoom = float(sub.get(ZOOM) or 1.0) or 1.0
    if sub.get(FOCAL_35):
        f35, diagonal = float(sub[FOCAL_35]), math.hypot(width, height)
        return Optics(f35 * diagonal / FULL_FRAME_DIAGONAL_MM,
                      f"35 mm-equivalent {f35:g} mm over the {diagonal:.0f} px diagonal", camera, zoom)
    if sub.get(FOCAL) and sensor_width_mm:
        focal = float(sub[FOCAL])
        return Optics(focal * max(width, height) / sensor_width_mm,
                      f"focal length {focal:g} mm on a {sensor_width_mm:g} mm sensor", camera, zoom)
    return None


def assumed(width: int, height: int, exif: Image.Exif, focal_35: float = ASSUMED_FOCAL_35) -> Optics:
    """The optics of a photo with no lens data, taken as if at 1× through a ``focal_35`` mm-equivalent lens."""
    camera = " ".join(str(exif[k]).strip() for k in (MAKE, MODEL) if k in exif) or "unknown camera"
    diagonal = math.hypot(width, height)
    return Optics(focal_35 * diagonal / FULL_FRAME_DIAGONAL_MM,
                  f"assumed {focal_35:g} mm-equivalent (1×; the photo had no lens data) over the {diagonal:.0f} px "
                  "diagonal", camera, 1.0, assumed=True)


@dataclass(frozen=True)
class Shape:
    """What the door's mask says about how it was photographed."""

    height_px: float  # down the middle of the door
    column: int
    top: int
    bottom: int
    width_px: float  # at mid-height
    taper: float  # width near the top ÷ width near the bottom (1 for a level phone)


def shape(mask: np.ndarray) -> Shape:
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    middle = int(np.median(np.nonzero(mask)[1]))
    spans = []
    for x in range(max(cols[0], middle - 2), min(cols[-1], middle + 2) + 1):
        inside = np.flatnonzero(mask[:, x])
        if inside.size:
            spans.append((inside[-1] - inside[0] + 1, int(inside[0]), int(inside[-1])))
    height, top, bottom = sorted(spans)[len(spans) // 2]

    def width_at(share: float) -> float:
        row = int(round(top + share * (bottom - top)))
        return float(mask[max(row - 2, 0): row + 3].sum(axis=1).mean())

    return Shape(height_px=float(height), column=middle, top=top, bottom=bottom, width_px=width_at(0.5),
                 taper=width_at(0.1) / max(width_at(0.9), 1.0))


def tilt_degrees(taper: float, distance_m: float, door_m: float) -> float:
    """The phone's pitch from the door's taper: a phone tilted up makes the door narrower at the top, by about
    (height ÷ distance) × tan(pitch) between rows 80% of the door apart."""
    return math.degrees(math.atan((1 - taper) * distance_m / (0.8 * door_m)))


@dataclass
class DoorReading:
    photo: str
    feet: float | None = None
    lowest_ft: float | None = None
    highest_ft: float | None = None
    refused: str | None = None  # why there's no distance: a key in phrases.DOOR_NOTES
    warnings: list[str] = field(default_factory=list)  # keys in phrases.DOOR_NOTES
    values: dict = field(default_factory=dict)  # numbers behind the warnings and the record
    mask: np.ndarray | None = None


def readable(path: Path, workdir: Path) -> Path:
    """A JPEG copy of a HEIC photo (sips keeps the EXIF); other formats as they are."""
    if path.suffix.lower() not in (".heic", ".heif"):
        return path
    out = workdir / f"{path.stem}.jpg"
    subprocess.run(["sips", "-s", "format", "jpeg", str(path), "--out", str(out)], check=True, capture_output=True)
    return out


def measure(photo: str | Path, segmenter: Segmenter, leaf_height_in: float = LEAF_IN,
            sensor_width_mm: float | None = None, assume_focal_35: float | None = ASSUMED_FOCAL_35) -> DoorReading:
    """The distance from the camera to the door in the photo, with its error range and anything that weakens it. A
    photo with no lens data is measured as if taken at 1× through ``assume_focal_35`` (``lens_assumed`` in its
    values, and a warning), or refused if that's None."""
    photo = Path(photo)
    reading = DoorReading(photo=photo.name, values={"leaf_height_in": leaf_height_in})
    with tempfile.TemporaryDirectory() as tmp:
        jpeg = readable(photo, Path(tmp))
        with Image.open(jpeg) as raw:
            exif = raw.getexif()
            width, height = ImageOps.exif_transpose(raw).size
        lens = optics(width, height, exif, sensor_width_mm)
        if lens is None and assume_focal_35:
            lens = assumed(width, height, exif, assume_focal_35)
            reading.warnings.append("lens-assumed")
        if lens is None:
            reading.refused = "no-focal-length"
            return reading
        reading.values.update(focal_px=lens.focal_px, focal_source=lens.source, camera=lens.camera,
                              size=[width, height], lens_assumed=lens.assumed)
        doors = sorted(segmenter.segment(jpeg, ["door"])["door"], key=lambda d: -d.score * d.mask.sum())
    if not doors:
        reading.refused = "no-door"
        return reading
    door = doors[0]
    reading.mask = door.mask
    found = shape(door.mask)
    reading.values.update(sam_score=door.score, doors_found=len(doors), door_px=found.height_px)
    if found.top <= 1 or found.bottom >= height - 2:
        reading.refused = "door-cut-off"
        return reading
    metres = lens.focal_px * leaf_height_in * INCH / found.height_px
    reading.feet = metres / FOOT
    reading.lowest_ft, reading.highest_ft = reading.feet / (1 + ERROR), reading.feet / (1 - ERROR)
    tilt = tilt_degrees(found.taper, metres, leaf_height_in * INCH)
    reading.values.update(tilt_deg=tilt, aspect=found.height_px / max(found.width_px, 1.0), error=ERROR,
                          span=[found.column, found.top, found.bottom])

    if lens.zoom > 1.01:
        reading.warnings.append("zoom")
    if abs(tilt) > TILT_LIMIT_DEG:
        reading.warnings.append("tilt")
    if found.height_px / max(found.width_px, 1.0) < 1.3:
        reading.warnings.append("garage-door")
    if abs(found.column - width / 2) > 0.3 * width:
        reading.warnings.append("off-centre")
    if found.height_px < SMALLEST_PX:
        reading.warnings.append("small")
    # Another door the same height (the other leaf of a double door, say) gives the same distance; one that isn't
    # is at a different distance, and the person should make sure the right one was measured.
    if any(abs(shape(other.mask).height_px / found.height_px - 1) > 0.10 for other in doors[1:]):
        reading.warnings.append("several-doors")
    return reading


def overlay(photo: str | Path, reading: DoorReading, out: Path, label: bool = True) -> Path:
    """The photo with the door SAM 3.1 found outlined and the measured span drawn, to check a reading by eye, and
    the distance written on it unless ``label`` is False."""
    with tempfile.TemporaryDirectory() as tmp:
        with Image.open(readable(Path(photo), Path(tmp))) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
    draw = ImageDraw.Draw(image)
    if reading.mask is not None:
        mask = reading.mask
        inner = np.pad(mask, 1)
        edge = mask & ~(inner[2:, 1:-1] & inner[:-2, 1:-1] & inner[1:-1, 2:] & inner[1:-1, :-2])
        ys, xs = np.nonzero(edge)
        draw.point(list(zip(xs.tolist(), ys.tolist())), fill=(255, 210, 0))
    if "span" in reading.values:
        column, top, bottom = reading.values["span"]
        draw.line([(column, top), (column, bottom)], fill=(255, 0, 0), width=max(3, image.width // 300))
    if label:
        text = (f"{reading.feet:.1f} ft ({reading.lowest_ft:.1f}–{reading.highest_ft:.1f})" if reading.feet
                else f"not measured: {reading.refused}")
        font = ImageFont.load_default(size=max(24, image.width // 25))
        draw.text((20, 20), text, fill=(255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0))
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{Path(photo).stem}-door.jpg"
    image.save(path, quality=85)
    return path
