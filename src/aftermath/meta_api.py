"""The Meta Model API, for Muse Voice Transcribe and Muse Spark: one client, the key from MODEL_API_KEY (or
META_API_KEY), and Meta's advice for a busy or failed request (back off and try again)."""

import os
import time

API = "https://api.meta.ai/v1"
RETRIED = (429, 500, 502, 503, 504)


def key() -> str | None:
    return os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")


def client(timeout: float = 60):
    import httpx

    if not key():
        raise RuntimeError("no Meta Model API key: set MODEL_API_KEY")
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key()}"}, timeout=timeout)


def post(http, path: str, retries: int = 2, **request):
    """A POST that backs off and tries again when the API is busy or fails, and raises on any other error."""
    for attempt in range(retries + 1):
        response = http.post(path, **request)
        if response.status_code not in RETRIED or attempt == retries:
            break
        time.sleep(0.5 * 2 ** attempt)
    response.raise_for_status()
    return response
