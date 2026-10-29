import math
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from aftermath.door import ERROR, measure, tilt_degrees
from aftermath.segment import Instance

SIZE = (1008, 1344)  # a downscaled portrait photo: the 35 mm-equivalent method doesn't care


class FakeSam:
    def __init__(self, *masks):
        self.masks = masks

    def segment(self, image_path, phrases):
        found = []
        for mask in self.masks:
            rows, cols = np.nonzero(mask)
            found.append(Instance("door", 0.95, (cols.min(), rows.min(), cols.max() + 1, rows.max() + 1), mask))
        return {phrase: found for phrase in phrases}


def door_photo(path, feet, f35=24, leaf_in=80.0, width_in=36.0, taper=1.0, centre=0.5, zoom=None, focal=True,
               drop=0.55):
    """A photo and the door's true mask: a door ``leaf_in`` tall exactly ``feet`` from a camera with this lens.
    ``taper`` is the door's width at the top over the bottom (a tilted phone); ``drop`` places its bottom edge."""
    width, height = SIZE
    focal_px = f35 * math.hypot(width, height) / math.hypot(36, 24)
    door_h = focal_px * leaf_in / (feet * 12)
    door_w = door_h * width_in / leaf_in
    bottom, top = height / 2 + drop * door_h, height / 2 + drop * door_h - door_h
    mask = np.zeros((height, width), bool)
    for row in range(max(0, int(math.ceil(top))), min(height, int(bottom))):  # a door too close is cut off
        w = door_w * (1 - (1 - taper) * (bottom - row) / door_h)
        mask[row, int(round(centre * width - w / 2)): int(round(centre * width + w / 2))] = True
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "Apple", "test phone"
    if focal:
        exif.get_ifd(0x8769)[0xA405] = f35
    if zoom:
        exif.get_ifd(0x8769)[0xA404] = zoom
    image = Image.new("RGB", SIZE, (210, 200, 180))
    image.save(path, exif=exif)
    return path, mask


@pytest.mark.parametrize("feet", [10, 20, 30])
def test_the_distance_comes_back_with_its_error_range(tmp_path, feet):
    photo, mask = door_photo(tmp_path / "door.jpg", feet)
    reading = measure(photo, FakeSam(mask))
    assert reading.refused is None and reading.warnings == []
    assert reading.feet == pytest.approx(feet, rel=0.01)
    assert reading.lowest_ft == pytest.approx(reading.feet / (1 + ERROR))
    assert reading.highest_ft == pytest.approx(reading.feet / (1 - ERROR))
    assert reading.values["camera"] == "Apple test phone" and "35 mm-equivalent 24 mm" in reading.values["focal_source"]


def test_a_taller_leaf_means_the_generator_is_farther_than_an_80_inch_guess(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 20, leaf_in=96)
    assert measure(photo, FakeSam(mask)).feet == pytest.approx(20 * 80 / 96, rel=0.01)  # read as 80 in: too close
    assert measure(photo, FakeSam(mask), leaf_height_in=96).feet == pytest.approx(20, rel=0.01)


@pytest.mark.skipif(shutil.which("sips") is None, reason="needs macOS sips")
def test_an_iphone_heic_photo_is_read_through_sips(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 15)
    heic = tmp_path / "IMG_0001.HEIC"
    subprocess.run(["sips", "-s", "format", "heic", str(photo), "--out", str(heic)], check=True, capture_output=True)
    assert measure(heic, FakeSam(mask)).feet == pytest.approx(15, rel=0.01)


@pytest.mark.parametrize("f35, reads", [(24, 20 * 23 / 24), (26, 20 * 23 / 26), (13, 20 * 23 / 13)])
def test_a_photo_with_no_lens_data_is_measured_as_if_at_1x_through_the_widest_common_lens(tmp_path, f35, reads):
    # iPhone Safari's own camera leaves the lens out. Taken at 1× (24 or 26 mm), the photo reads no farther than it
    # is; taken at 0.5× (13 mm), nearly twice as far, which is why the rules wait for the person to say it was 1×.
    photo, mask = door_photo(tmp_path / "plain.jpg", 20, f35=f35, focal=False)
    reading = measure(photo, FakeSam(mask))
    assert reading.refused is None and reading.feet == pytest.approx(reads, rel=0.01)
    assert reading.values["lens_assumed"] is True and reading.warnings == ["lens-assumed"]
    assert "assumed 23 mm" in reading.values["focal_source"]
    assert measure(photo, FakeSam(mask), assume_focal_35=None).refused == "no-focal-length"
    with_lens, mask = door_photo(tmp_path / "door.jpg", 20)
    assert measure(with_lens, FakeSam(mask)).values["lens_assumed"] is False


def test_photos_that_cant_be_measured_honestly_are_refused(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 20)
    assert measure(photo, FakeSam()).refused == "no-door"
    photo, mask = door_photo(tmp_path / "close.jpg", 4)  # too close to fit: cut off at the top and bottom
    reading = measure(photo, FakeSam(mask))
    assert reading.refused == "door-cut-off" and reading.feet is None


def test_a_tilted_phone_is_noticed_from_the_doors_taper(tmp_path):
    # Tilted up 10° at 20 ft, an 80 in door is about 5.9% narrower at the top than at the bottom.
    full_taper = 1 - (80 * 0.0254 / (20 * 0.3048)) * math.tan(math.radians(10))
    photo, mask = door_photo(tmp_path / "door.jpg", 20, taper=full_taper)
    reading = measure(photo, FakeSam(mask))
    assert reading.values["tilt_deg"] == pytest.approx(10, abs=1.5) and reading.warnings == ["tilt"]
    assert tilt_degrees(1.0, 6.0, 2.0) == 0


def test_zoom_garage_doors_edges_and_extra_doors_are_flagged(tmp_path):
    photo, mask = door_photo(tmp_path / "zoom.jpg", 20, zoom=2.0)
    assert measure(photo, FakeSam(mask)).warnings == ["zoom"]
    photo, mask = door_photo(tmp_path / "garage.jpg", 20, leaf_in=84, width_in=192)
    assert "garage-door" in measure(photo, FakeSam(mask)).warnings
    photo, mask = door_photo(tmp_path / "edge.jpg", 20, centre=0.88)
    assert measure(photo, FakeSam(mask)).warnings == ["off-centre"]
    photo, mask = door_photo(tmp_path / "two.jpg", 20)
    _, other = door_photo(tmp_path / "other.jpg", 30, centre=0.25)
    assert measure(photo, FakeSam(mask, other)).warnings == ["several-doors"]


def test_the_other_leaf_of_a_double_door_is_not_a_second_door(tmp_path):
    photo, left = door_photo(tmp_path / "double.jpg", 20, centre=0.42)
    _, right = door_photo(tmp_path / "right.jpg", 20, centre=0.58)
    assert measure(photo, FakeSam(left, right)).warnings == []
