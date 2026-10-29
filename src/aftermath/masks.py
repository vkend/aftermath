"""Binary masks: run-length encoding for storage, and simple geometry read off them."""

import numpy as np


def rle_encode(mask: np.ndarray) -> dict:
    """COCO-style uncompressed RLE: run lengths over the column-major pixels, starting with background."""
    height, width = mask.shape
    flat = np.asarray(mask, dtype=bool).ravel(order="F")
    if flat.size == 0:
        return {"size": [height, width], "counts": []}
    changes = np.flatnonzero(flat[1:] != flat[:-1]) + 1
    counts = np.diff(np.concatenate(([0], changes, [flat.size]))).tolist()
    if flat[0]:
        counts.insert(0, 0)
    return {"size": [height, width], "counts": counts}


def rle_decode(rle: dict) -> np.ndarray:
    """The boolean (height, width) mask for an RLE made by ``rle_encode``."""
    height, width = rle["size"]
    counts = np.asarray(rle["counts"], dtype=np.int64)
    flat = np.repeat(np.arange(counts.size) % 2 == 1, counts)
    return flat.reshape((height, width), order="F")


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """The mask's box as half-open pixel bounds (x1, y1, x2, y2), or None for an empty mask."""
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(mask.any(axis=0))
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1
