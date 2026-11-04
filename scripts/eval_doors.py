"""The app's door distance against metric ground truth, on public scans with laser or rendered depth.

    uv run --offline python scripts/eval_doors.py      # needs data/evals/doors (see its README.md)

Two sets, kept in data/evals/doors (never committed):
- DIODE validation (Vasiljevic et al. 2019, MIT): real photos with a FARO laser's depth. 19 images: 9 with the whole
  door in view (3 doors from several angles, 6–9 m away) and 10 hard ones (the bottom hidden, open doors seen edge on,
  a door cut off by the frame). DIODE's published intrinsics are about 1.5× too small: room corners only come out
  square with f ≈ 1322 px, which devkit issue #20's 42.3° × 32.4° field of view also gives, and with it two standard
  doors measure 2.12 and 2.15 m tall (3.0 m with the published value). So f = 1322 px, square pixels.
- Hypersim (Roberts et al. 2021, CC BY-SA 3.0, so only numbers from it): synthetic indoor renders with exact depth and
  labelled doors, many of them glass. 39 doors in 30 frames, f = 886.81 px.

Each image goes to the app's own door.measure, with SAM 3.1 run fresh. The scans have no EXIF, so each gets its exact
focal length written as EXIF FocalLength on a 36 mm sensor, which door.optics turns back into the same pixels. The
door the app chose is matched to a labelled one by the overlap of their outlines. The reference is the median z-depth
over the door (gt_z_median_m), which is what focal × height ÷ pixel height estimates. Measured twice:
(a) with the door's true height: the error left is the geometry's and SAM's outline;
(b) with the app's assumption, an 80 in leaf: what a person gets. Its band (from the low end of the ±6% range, as the
    app gives it, at best borderline when a warning says it may read too far: door.READS_FAR) is compared with the
    band of the true distance, and any "meets the guidance" for a door that is really under 20 ft (6.1 m) is
    counted: that is the error that must not happen. The summary also gives what the cap costs: right "meets the
    guidance" verdicts it turns into "borderline".
The hard rows report what the app did: refused, warned, or measured, and how far off.
"""

import csv
import json
import statistics
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, TiffImagePlugin

from aftermath.cache import ResponseCache
from aftermath.door import FOOT, LEAF_IN, READS_FAR, measure
from aftermath.rules import band

DATA = Path("data/evals/doors")
SETS = {"diode": "DIODE (real, laser depth)", "hypersim": "Hypersim (synthetic)"}
SENSOR_MM = 36.0
INCH = 0.0254
UNDER = 20 * FOOT  # the CDC's 20 ft, in metres


def with_focal(image: Path, focal_px: float, out: Path) -> Path:
    """The image as a JPEG whose EXIF FocalLength on a 36 mm sensor is ``focal_px``."""
    picture = Image.open(image).convert("RGB")
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x920A] = TiffImagePlugin.IFDRational(round(focal_px * SENSOR_MM / max(picture.size)
                                                                         * 100000), 100000)
    picture.save(out, quality=95, exif=exif)
    return out


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / max((a | b).sum(), 1))


def evaluate(name: str, sam) -> list[dict]:
    folder = DATA / name
    rows = list(csv.DictReader((folder / "manifest.csv").open()))
    by_image: dict[str, list[dict]] = {}
    for row in rows:
        by_image.setdefault(row["image"], []).append(row)
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for image, doors in by_image.items():
            photo = with_focal(folder / image, float(doors[0]["fx"]), Path(tmp) / f"{Path(image).stem}.jpg")
            assumed = measure(photo, sam, LEAF_IN, sensor_width_mm=SENSOR_MM)
            result = {"set": name, "image": image, "refused": assumed.refused, "warnings": assumed.warnings,
                      "focal_px": assumed.values.get("focal_px")}
            match, best = None, 0.0
            if assumed.mask is not None:
                for row in doors:
                    labelled = np.array(Image.open(folder / row["door_mask"]).convert("L")) > 127
                    if labelled.shape == assumed.mask.shape and overlap(labelled, assumed.mask) > best:
                        match, best = row, overlap(labelled, assumed.mask)
            result["overlap"] = round(best, 3)
            if match is None or best < 0.5:  # the app measured something else, or nothing
                result.update(category=doors[0]["category"] if len(doors) == 1 else "several",
                              matched=False, feet=assumed.feet)
                out.append(result)
                continue
            truth_m = float(match["gt_z_median_m"])
            result.update(category=match["category"], matched=True, truth_ft=truth_m / FOOT, notes=match.get("notes"))
            if assumed.feet is not None:
                far = bool(READS_FAR & set(assumed.warnings))
                result.update(feet=assumed.feet, lowest_ft=assumed.lowest_ft,
                              error_80in=assumed.feet * FOOT / truth_m - 1, reads_far=far,
                              band=band(assumed.lowest_ft, far), uncapped_band=band(assumed.lowest_ft),
                              true_band=band(truth_m / FOOT),
                              meets_under_20=band(assumed.lowest_ft, far) == "meets the guidance" and truth_m < UNDER,
                              meets_under_20_uncapped=band(assumed.lowest_ft) == "meets the guidance"
                              and truth_m < UNDER)
            height = match.get("gt_door_height_m")
            if height and match["category"].startswith("clean") and not match.get("mask_touches_edge"):
                true = measure(photo, sam, float(height) / INCH, sensor_width_mm=SENSOR_MM)
                if true.feet is not None:
                    result.update(door_height_m=float(height), error_true_height=true.feet * FOOT / truth_m - 1)
            out.append(result)
            print(f"  {name} {Path(image).name}: {result.get('category')} {result.get('feet') or 0:.1f} ft"
                  f" vs {result.get('truth_ft') or 0:.1f} ft, {assumed.refused or ', '.join(assumed.warnings) or 'ok'}",
                  flush=True)
    return out


def summary(results: list[dict]) -> list[str]:
    lines = []
    for name, title in SETS.items():
        rows = [r for r in results if r["set"] == name]
        clean = [r for r in rows if r.get("matched") and r["category"].startswith("clean") and "feet" in r
                 and r.get("error_80in") is not None]
        true = [r["error_true_height"] for r in clean if "error_true_height" in r]
        lines.append(f"{title}: {len(rows)} images")
        if true:
            lines.append(f"  (a) true door height, {len(true)} clean doors: median error {statistics.median(true):+.1%}"
                         f", worst {max(true, key=abs):+.1%}")
        if clean:
            errors = [r["error_80in"] for r in clean]
            right = sum(r["band"] == r["true_band"] for r in clean)
            lines.append(f"  (b) 80 in assumed, {len(clean)} clean doors: median error {statistics.median(errors):+.1%},"
                         f" range {min(errors):+.1%} to {max(errors):+.1%}; band right {right} of {len(clean)}")
        measured = [r for r in rows if r.get("matched") and r.get("error_80in") is not None]
        wrong = [r for r in measured if r.get("meets_under_20")]
        before = [r for r in measured if r.get("meets_under_20_uncapped")]
        lines.append(f"  'meets the guidance' for a door under 20 ft: {len(wrong)} of {len(measured)} measured "
                     f"({len(before)} without the cap on readings that may be too far)")
        right = [r for r in measured if r["true_band"] == "meets the guidance" and r["uncapped_band"] == r["true_band"]]
        kept = [r for r in right if r["band"] == "meets the guidance"]
        lines.append(f"  right 'meets the guidance' kept under the cap: {len(kept)} of {len(right)} "
                     f"(the cap's cost: {len(right) - len(kept)} now borderline)")
        hard = [r for r in rows if not (r.get("matched") and r["category"].startswith("clean"))]
        refused = sum(bool(r["refused"]) for r in hard)
        warned = sum(bool(not r["refused"] and r["warnings"]) for r in hard)
        lines.append(f"  hard or other ({len(hard)}): refused {refused}, measured with a warning {warned}, "
                     f"measured without one {len(hard) - refused - warned}")
        for r in hard:
            if not r["refused"] and r.get("error_80in") is not None:
                lines.append(f"    {r['category']}: {r['feet']:.1f} ft vs {r['truth_ft']:.1f} ft ({r['error_80in']:+.0%}),"
                             f" {r['band']} (truly {r['true_band']}); warnings {r['warnings'] or 'none'}")
            elif not r["refused"]:
                lines.append(f"    {r['category']}: measured another door or no door (overlap {r['overlap']}), "
                             f"{r.get('feet') or 0:.1f} ft; warnings {r['warnings'] or 'none'}")
    return lines


def main() -> None:
    from aftermath.segment import LocalSam31

    if not DATA.exists():
        sys.exit(f"no {DATA}: see the docstring")
    sam = LocalSam31(ResponseCache(Path("data/cache")))
    results = [r for name in SETS for r in evaluate(name, sam)]
    (DATA / "results-app.json").write_text(json.dumps(results, indent=1, default=float))
    print("\n".join(summary(results)))


if __name__ == "__main__":
    main()
