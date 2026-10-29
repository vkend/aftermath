"""Content-addressed cache for model calls.

Every model call, local or on the Meta API, is described by a JSON request: the backend, the model and its
revision, digests of the input files (never their paths) and the parameters. The SHA-256 of that request names
the stored result, so re-runs and demo takes replay from disk instead of running the model again.
"""

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    """JSON with sorted keys and no whitespace, so equal requests serialize to equal bytes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_key(request: dict[str, Any]) -> str:
    """The SHA-256 hex digest of a request's canonical JSON."""
    return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()


def file_digest(path: str | os.PathLike[str]) -> str:
    """The SHA-256 hex digest of a file's bytes, used to name an input inside a request."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ResponseCache:
    """One JSON record per request, stored at ``root/<first two hex digits>/<key>.json``.

    A record holds the request, the result, how long the call took and when it ran. The request holds only
    digests and parameters, so records are safe to keep and to list.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.hits = 0
        self.misses = 0

    def path(self, request: dict[str, Any]) -> Path:
        key = request_key(request)
        return self.root / key[:2] / f"{key}.json"

    def get(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """The stored record for a request, or None."""
        try:
            with self.path(request).open(encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def put(self, request: dict[str, Any], result: Any, elapsed_s: float) -> dict[str, Any]:
        """Store a result. The write is atomic, so an interrupted run never leaves a partial record."""
        record = {"request": request, "result": result, "elapsed_s": round(elapsed_s, 3), "created": time.time()}
        path = self.path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
        return record

    def fetch(self, request: dict[str, Any], compute: Callable[[], Any]) -> dict[str, Any]:
        """The record for a request, running ``compute()`` only on a miss. ``record["result"]`` is the result."""
        record = self.get(request)
        if record is not None:
            self.hits += 1
            return record
        self.misses += 1
        start = time.perf_counter()
        result = compute()
        return self.put(request, result, time.perf_counter() - start)
