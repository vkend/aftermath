"""Text-prompted segmentation with SAM 3.1.

The local backend runs Meta's SAM 3.1 open weights, converted to MLX (``mlx-community/sam3.1-bf16``), through
mlx-vlm on Apple silicon. Results are cached per image and phrase, so each phrase runs once per image.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .cache import ResponseCache, file_digest
from .masks import rle_decode, rle_encode


@dataclass(frozen=True)
class Instance:
    """One match for a phrase, in image pixels."""

    phrase: str
    score: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    mask: np.ndarray  # (height, width), bool


def load_image(path: str | Path) -> Image.Image:
    """An RGB image as displayed, with its EXIF rotation applied (SAM expects displayed pixels)."""
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


class LocalSam31:
    """SAM 3.1 on this machine. ``segment`` returns every match above the score threshold, per phrase."""

    backend = "mlx-vlm"
    model = "mlx-community/sam3.1-bf16"
    revision = "a992e302ea9b0f03f41dfd93414a4fd0e818f65b"

    def __init__(self, cache: ResponseCache, score_threshold: float = 0.3) -> None:
        self.cache = cache
        self.score_threshold = score_threshold
        self._predictor = None

    def segment(self, image_path: str | Path, phrases: list[str]) -> dict[str, list[Instance]]:
        digest = file_digest(image_path)
        requests = {phrase: self._request(digest, phrase) for phrase in phrases}
        records = {phrase: self.cache.get(request) for phrase, request in requests.items()}
        missing = [phrase for phrase, record in records.items() if record is None]
        if missing:
            self.cache.misses += len(missing)
            records.update(self._run(image_path, missing, requests))
        self.cache.hits += len(phrases) - len(missing)
        return {phrase: [_instance(phrase, match) for match in records[phrase]["result"]] for phrase in phrases}

    def _request(self, image_digest: str, phrase: str) -> dict[str, Any]:
        return {
            "task": "segment-image",
            "backend": self.backend,
            "model": self.model,
            "revision": self.revision,
            "image": image_digest,
            "phrase": phrase,
            "score_threshold": self.score_threshold,
        }

    def _run(self, image_path, phrases, requests) -> dict[str, dict]:
        from mlx_vlm.models.sam3_1.generate import predict_multi

        predictor = self._load()
        # A PIL image, not an array: mlx-vlm's postprocessing swaps width and height for numpy input.
        image = load_image(image_path)
        start = time.perf_counter()
        # One vision-backbone pass for the image, then text and decoder passes per phrase; NMS per phrase.
        result = predict_multi(predictor, image, phrases, score_threshold=self.score_threshold)
        elapsed = (time.perf_counter() - start) / len(phrases)
        records = {}
        for phrase in phrases:
            matches = [
                {
                    "score": round(float(result.scores[i]), 4),
                    "box": [round(float(v), 1) for v in result.boxes[i]],
                    "mask": rle_encode(result.masks[i].astype(bool)),
                }
                for i, label in enumerate(result.labels)
                if label == phrase
            ]
            matches.sort(key=lambda match: -match["score"])
            records[phrase] = self.cache.put(requests[phrase], matches, elapsed)
        return records

    def _load(self):
        if self._predictor is None:
            from mlx_vlm.models.sam3.generate import Sam3Predictor
            from mlx_vlm.models.sam3_1.processing_sam3_1 import Sam31Processor
            from mlx_vlm.utils import get_model_path, load_model

            path = get_model_path(self.model, revision=self.revision)
            self._predictor = Sam3Predictor(
                load_model(path), Sam31Processor.from_pretrained(str(path)), score_threshold=self.score_threshold
            )
        return self._predictor


def _instance(phrase: str, match: dict) -> Instance:
    return Instance(phrase=phrase, score=match["score"], box=tuple(match["box"]), mask=rle_decode(match["mask"]))
