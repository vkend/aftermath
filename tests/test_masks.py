import numpy as np
import pytest

from aftermath.masks import bounding_box, rle_decode, rle_encode


@pytest.mark.parametrize("fill", ["random", "zeros", "ones", "first-pixel"])
def test_rle_round_trip(fill):
    rng = np.random.default_rng(0)
    mask = {
        "random": rng.random((37, 51)) > 0.6,
        "zeros": np.zeros((5, 4), bool),
        "ones": np.ones((5, 4), bool),
        "first-pixel": np.eye(1, 12, dtype=bool).reshape(3, 4),
    }[fill]
    rle = rle_encode(mask)
    assert rle["size"] == list(mask.shape)
    assert sum(rle["counts"]) == mask.size
    assert np.array_equal(rle_decode(rle), mask)


def test_rle_is_column_major_starting_with_background():
    mask = np.array([[0, 1], [1, 1]], bool)  # column-major pixels: 0, 1, 1, 1
    assert rle_encode(mask)["counts"] == [1, 3]
    assert rle_encode(~mask)["counts"] == [0, 1, 3]


def test_bounding_box_is_half_open():
    mask = np.zeros((10, 20), bool)
    mask[2:5, 7:9] = True
    assert bounding_box(mask) == (7, 2, 9, 5)
    assert bounding_box(np.zeros((3, 3), bool)) is None
