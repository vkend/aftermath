"""Vision-language calls: Muse Glimmer on this machine, or Muse Spark on the Meta Model API.

Every call asks for JSON that matches a schema and goes through the response cache.
"""

import base64
import io
import json
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps

from . import meta_api
from .cache import ResponseCache, file_digest

EXIF_ORIENTATION = 0x0112


class LocalGlimmer:
    """Muse Glimmer 30B served by Ollama on this machine, through its OpenAI-compatible chat API."""

    backend = "ollama"

    # Tried in order until one gives a usable answer. A retry needs a change: at temperature 0 the same request
    # fails the same way. The last attempt drops the schema grammar and checks the fields here instead.
    ATTEMPTS = (("low", "schema"), ("medium", "schema"), ("low", "json"))

    def __init__(
        self,
        cache: ResponseCache,
        model: str = "muse-glimmer:30b-mlx",
        base_url: str = "http://localhost:11434",
        attempts: tuple[tuple[str, str], ...] = ATTEMPTS,
        max_tokens: int = 3000,
        timeout: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.cache = cache
        self.model = model
        self.attempts = attempts
        self.max_tokens = max_tokens  # good answers so far took 330–600 tokens
        self.http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._weights: str | None = None

    def weights_digest(self) -> str:
        """Ollama's digest of the model, so answers from a re-pulled model aren't replayed from the cache."""
        if self._weights is None:
            models = self.http.get("/api/tags").raise_for_status().json()["models"]
            self._weights = next(m["digest"] for m in models if m["name"] == self.model)
        return self._weights

    def ask_json(self, prompt: str, schema: dict[str, Any], images: list[str | Path] = ()) -> dict[str, Any]:
        """Ask about some images and get back JSON with every field ``schema`` requires.

        Raises ``UnusableAnswer`` when every attempt in ``attempts`` fails. Failed answers are never cached.
        """
        digests = [file_digest(path) for path in images]
        errors = []
        try:
            weights = self.weights_digest()
        except (httpx.HTTPError, StopIteration) as error:
            raise ReadFailed(f"Ollama hasn't got {self.model}: {error!r}") from error
        for effort, mode in self.attempts:
            request = {
                "task": "ask-json",
                "backend": self.backend,
                "model": self.model,
                "weights": weights,
                "effort": effort,
                "mode": mode,
                "prompt": prompt,
                "schema": schema,
                "images": digests,
            }
            try:
                record = self.cache.fetch(request, lambda: self._chat(prompt, schema, images, effort, mode))
                return record["result"]["answer"]
            except UnusableAnswer as error:
                errors.append(f"{effort}/{mode}: {error}")
            except httpx.HTTPError as error:
                raise ReadFailed(f"Ollama: {error!r}") from error
        raise UnusableAnswer("; ".join(errors))

    def _chat(self, prompt: str, schema: dict[str, Any], images, effort: str, mode: str) -> dict[str, Any]:
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": image_data_url(path)}} for path in images]
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "reasoning_effort": effort,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "response_format": (
                {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}
                if mode == "schema"
                else {"type": "json_object"}
            ),
        }
        if mode != "schema":
            content[0]["text"] += "\n\nAnswer with JSON matching this schema:\n" + json.dumps(schema)
        text, usage, finish, blank_run = [], None, None, 0
        with self.http.stream("POST", "/v1/chat/completions", json=body) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    piece = choice.get("delta", {}).get("content") or ""
                    text.append(piece)
                    finish = choice.get("finish_reason") or finish
                    if piece.strip():
                        blank_run = 0
                    else:
                        blank_run += len(piece)
                if blank_run > STALL:
                    # The schema grammar allows any whitespace between fields; a model that doesn't want to write
                    # the next required field can emit spaces until max_tokens. Stop early instead.
                    raise UnusableAnswer(f"stalled on whitespace after {len(''.join(text))} characters")
        if finish == "length":
            raise UnusableAnswer(f"hit max_tokens={self.max_tokens}")
        try:
            answer = json.loads("".join(text))
        except json.JSONDecodeError as error:
            raise UnusableAnswer(f"not JSON: {error}") from None
        missing = missing_fields(answer, schema)
        if missing:
            raise UnusableAnswer(f"missing {', '.join(missing)}")
        return {"answer": answer, "usage": usage}


class MuseSpark:
    """Muse Spark on the Meta Model API (its Responses API), with the same ``ask_json`` as ``LocalGlimmer``: the
    reader for the API mode. The key comes from MODEL_API_KEY (or META_API_KEY).

    Each request asks Meta not to store the response (``store: false``) and sets its reasoning effort, and answers are
    cached here like every model call. The schema is sent strict (``strict_schema``): every field required, and those
    the caller left optional may be null, which stands for "not stated" and is dropped from the answer. Without that,
    Spark with little reasoning wrote nearly every optional field (8 of 156 turns on Oct 29, mostly "no"); with it,
    none of those 8. Photos go without their metadata (no location), at most 2048 pixels across.
    """

    backend = "meta-api"

    # Tried in order until one gives a usable answer. On Oct 29, "minimal" read a Hindi "हाँ, है।" right in 1.1 s
    # (188 reasoning tokens) and "low" in 2.8 s (564). Spark has no "none".
    EFFORTS = ("minimal", "low")

    def __init__(self, cache: ResponseCache, model: str = "muse-spark-1.3", efforts: tuple[str, ...] = EFFORTS,
                 max_tokens: int = 2000, client: httpx.Client | None = None, retries: int = 2) -> None:
        self.cache, self.model, self.efforts, self.retries = cache, model, efforts, retries
        self.max_tokens = max_tokens  # reasoning counts against it
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = meta_api.client(timeout=60)
        return self._client

    def ask_json(self, prompt: str, schema: dict[str, Any], images: list[str | Path] = ()) -> dict[str, Any]:
        """Ask about some images and get back JSON with every field ``schema`` requires.

        Raises ``UnusableAnswer`` when every effort in ``efforts`` fails, and ``ReadFailed`` when the API can't be
        reached or refuses the request. Failed answers are never cached.
        """
        digests = [file_digest(path) for path in images]
        errors = []
        for effort in self.efforts:
            request = {"task": "ask-json", "backend": self.backend, "model": self.model, "effort": effort,
                       "prompt": prompt, "schema": schema, "strict": True, "images": digests}
            try:
                record = self.cache.fetch(request, lambda: self._respond(prompt, schema, images, effort))
                return record["result"]["answer"]
            except UnusableAnswer as error:
                errors.append(f"{effort}: {error}")
            except httpx.HTTPError as error:
                raise ReadFailed(f"Meta API: {error!r}") from error
        raise UnusableAnswer("; ".join(errors))

    def _respond(self, prompt: str, schema: dict[str, Any], images, effort: str) -> dict[str, Any]:
        content = [{"type": "input_text", "text": prompt}]
        content += [{"type": "input_image", "image_url": image_data_url(path, bare=True)} for path in images]
        body = {
            "model": self.model,
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": "answer", "schema": strict_schema(schema),
                                "strict": True}},
            "reasoning": {"effort": effort},
            "max_output_tokens": self.max_tokens,
            "store": False,
        }
        try:
            response = meta_api.post(self._http(), "/responses", self.retries, json=body).json()
        except ValueError as error:
            raise UnusableAnswer(f"the API's reply isn't JSON: {error}") from None
        if response.get("status") != "completed":
            reason = (response.get("incomplete_details") or {}).get("reason")
            raise UnusableAnswer(f"{response.get('status')}" + (f" ({reason})" if reason else ""))
        text = "".join(part.get("text") or "" for item in response.get("output", []) if item.get("type") == "message"
                       for part in item.get("content", []) if part.get("type") == "output_text")
        try:
            answer = without_nulls(json.loads(text), schema)
        except json.JSONDecodeError as error:
            raise UnusableAnswer(f"not JSON: {error}") from None
        missing = missing_fields(answer, schema)
        if missing:
            raise UnusableAnswer(f"missing {', '.join(missing)}")
        return {"answer": answer, "usage": response.get("usage")}


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A schema as a strict structured-output mode takes it: in every object, every field required and no others;
    a field that was optional may be null instead."""
    kind = schema.get("type")
    if kind == "object":
        required = set(schema.get("required", []))
        fields = {name: strict_schema(sub) if name in required else nullable(strict_schema(sub))
                  for name, sub in schema.get("properties", {}).items()}
        return {**schema, "properties": fields, "required": list(fields), "additionalProperties": False}
    if kind == "array":
        return {**schema, "items": strict_schema(schema.get("items", {}))}
    return schema


def nullable(schema: dict[str, Any]) -> dict[str, Any]:
    kind = schema.get("type")
    if not isinstance(kind, str):
        return {"anyOf": [schema, {"type": "null"}]}
    loose = {**schema, "type": [kind, "null"]}
    if "enum" in schema:
        loose["enum"] = [*schema["enum"], None]
    return loose


def without_nulls(value: Any, schema: dict[str, Any]) -> Any:
    """An answer to a strict_schema, with the optional fields left null taken out, as if never written."""
    if schema.get("type") == "object" and isinstance(value, dict):
        required, fields = set(schema.get("required", [])), schema.get("properties", {})
        return {name: without_nulls(item, fields.get(name, {})) for name, item in value.items()
                if item is not None or name in required}
    if schema.get("type") == "array" and isinstance(value, list):
        return [without_nulls(item, schema.get("items", {})) for item in value]
    return value


STALL = 200  # characters of unbroken whitespace in an answer that mean the model has stalled


class ReadFailed(RuntimeError):
    """Nothing usable came back: the model couldn't be reached, or its answer couldn't be used. The conversation and
    the plate reader take it as nothing read, so it can never take a danger off the list."""


class UnusableAnswer(ReadFailed):
    """The model's answer was cut off, stalled, not JSON, or missing required fields."""


def missing_fields(value: Any, schema: dict[str, Any], path: str = "") -> list[str]:
    """Required fields absent anywhere in ``value``, as dotted paths. Only objects and arrays are walked."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return [path or "(top level)"]
        missing = [f"{path}{name}" for name in schema.get("required", []) if name not in value]
        for name, sub in schema.get("properties", {}).items():
            if name in value:
                missing += missing_fields(value[name], sub, f"{path}{name}.")
        return missing
    if kind == "array":
        if not isinstance(value, list):
            return [path.rstrip(".") or "(top level)"]
        return [m for i, item in enumerate(value) for m in missing_fields(item, schema.get("items", {}), f"{path}{i}.")]
    return []


def image_data_url(path: str | Path, bare: bool = False, longest: int = 2048) -> str:
    """A data URL for an image as displayed: a photo with an EXIF rotation is re-encoded upright. ``bare`` (for a
    photo that leaves the laptop) always re-encodes it, which drops its metadata, location included, and shrinks it
    to at most ``longest`` pixels across."""
    data = Path(path).read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        mime = Image.MIME.get(image.format, "image/jpeg")
        if bare or image.getexif().get(EXIF_ORIENTATION, 1) != 1:
            upright = ImageOps.exif_transpose(image).convert("RGB")
            if bare:
                upright.thumbnail((longest, longest))
            buffer = io.BytesIO()
            upright.save(buffer, "JPEG", quality=92)  # no exif= given: none is written
            data, mime = buffer.getvalue(), "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"
