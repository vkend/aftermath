import base64
import io
import json

import httpx
import pytest
from PIL import Image

from aftermath.cache import ResponseCache
from aftermath.meta_api import API
from aftermath.vlm import (LocalGlimmer, MuseSpark, ReadFailed, UnusableAnswer, missing_fields, strict_schema,
                           without_nulls)

# A small rating-plate schema. Note that "items" here is the JSON-schema keyword for an array's members.
SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "outlets": {"type": "array", "items": {"type": "object", "properties": {"volts": {"type": "number"}},
                                               "required": ["volts"]}},
    },
    "required": ["brand", "outlets"],
}


def stream(*pieces, finish="stop"):
    """An OpenAI-style server-sent event stream that sends the answer in ``pieces``."""
    events = [{"choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in pieces]
    events.append({"choices": [{"delta": {}, "finish_reason": finish}]})
    events.append({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": len(pieces)}})
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


class FakeOllama:
    """Answers chat requests from a script, one reply per request, and records what was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "muse-glimmer:30b-mlx", "digest": "sha256:abc"}]})
        self.requests.append(json.loads(request.content))
        return self.replies.pop(0)


def glimmer(tmp_path, fake):
    return LocalGlimmer(ResponseCache(tmp_path), transport=httpx.MockTransport(fake))


def test_a_good_answer_is_returned_and_cached(tmp_path):
    fake = FakeOllama(stream('{"brand": "Champion", ', '"outlets": [{"volts": 120}]}'))
    model = glimmer(tmp_path, fake)
    answer = model.ask_json("read the rating plate", SCHEMA)
    assert answer == {"brand": "Champion", "outlets": [{"volts": 120}]}
    assert model.ask_json("read the rating plate", SCHEMA)["brand"] == "Champion"
    assert len(fake.requests) == 1
    assert fake.requests[0]["response_format"]["type"] == "json_schema"


def test_a_whitespace_stall_stops_early_and_the_json_attempt_rescues_it(tmp_path):
    stalled = stream('{"brand": "Honda", "outlets": [{"volts": 120}', *([" " * 50] * 10))
    fake = FakeOllama(stalled, stream('{"brand": "Honda", ', '"outlets": [', *([" "] * 20)),
                      stream('{"brand": "Honda", "outlets": []}'))
    model = glimmer(tmp_path, fake)
    assert model.ask_json("read the rating plate", SCHEMA) == {"brand": "Honda", "outlets": []}
    modes = [r["response_format"]["type"] for r in fake.requests]
    efforts = [r["reasoning_effort"] for r in fake.requests]
    assert modes == ["json_schema", "json_schema", "json_object"] and efforts == ["low", "medium", "low"]
    assert "Answer with JSON matching this schema" in fake.requests[2]["messages"][0]["content"][0]["text"]


def test_every_attempt_failing_raises_with_the_reasons(tmp_path):
    fake = FakeOllama(stream('{"brand": "x"}'), stream('{"brand": "x", "outlets"', finish="length"),
                      stream("not json"))
    with pytest.raises(UnusableAnswer) as error:
        glimmer(tmp_path, fake).ask_json("q", SCHEMA)
    message = str(error.value)
    assert "missing outlets" in message and "max_tokens" in message and "not JSON" in message
    assert not list(tmp_path.rglob("*.json"))  # nothing unusable was cached


def test_missing_fields_walks_objects_and_arrays():
    assert missing_fields({"brand": "x", "outlets": [{"volts": 120}, {}]}, SCHEMA) == ["outlets.1.volts"]
    assert missing_fields([], SCHEMA) == ["(top level)"]
    assert missing_fields({"brand": "x", "outlets": "four"}, SCHEMA) == ["outlets"]


def test_glimmer_unreachable_is_a_failed_read(tmp_path):
    def down(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ReadFailed, match="Ollama"):
        LocalGlimmer(ResponseCache(tmp_path), transport=httpx.MockTransport(down)).ask_json("q", SCHEMA)


def responses(*replies):
    """A fake Meta Responses API: one reply per request (a dict is a 200's JSON), and the requests it got."""
    replies, seen = list(replies), []

    def answer(request):
        seen.append(json.loads(request.content))
        reply = replies.pop(0)
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    return httpx.Client(base_url=API, transport=httpx.MockTransport(answer)), seen


def response(text, status="completed", reason=None):
    message = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}
    return {"status": status, "incomplete_details": {"reason": reason} if reason else None,
            "output": [{"type": "reasoning", "encrypted_content": "..."}, message],
            "usage": {"input_tokens": 555, "output_tokens": 220, "output_tokens_details": {"reasoning_tokens": 188}}}


def test_spark_asks_with_the_schema_keeps_nothing_at_meta_and_caches(tmp_path):
    client, seen = responses(response('{"brand": "Champion", "outlets": [{"volts": 120}]}'))
    spark = MuseSpark(ResponseCache(tmp_path), client=client)
    assert spark.ask_json("read the rating plate", SCHEMA) == {"brand": "Champion", "outlets": [{"volts": 120}]}
    assert spark.ask_json("read the rating plate", SCHEMA)["brand"] == "Champion" and len(seen) == 1
    body = seen[0]
    assert body["model"] == "muse-spark-1.3" and body["store"] is False and body["reasoning"] == {"effort": "minimal"}
    assert body["text"]["format"] == {"type": "json_schema", "name": "answer", "schema": strict_schema(SCHEMA),
                                      "strict": True}
    assert body["input"][0]["content"] == [{"type": "input_text", "text": "read the rating plate"}]


def test_spark_gets_photos_without_their_metadata(tmp_path):
    photo = tmp_path / "plate.jpg"
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (27.0, 57.0, 1.0)}  # where it was taken
    Image.new("RGB", (4032, 3024), "white").save(photo, exif=exif)
    client, seen = responses(response('{"brand": "", "outlets": []}'))
    MuseSpark(ResponseCache(tmp_path / "cache"), client=client).ask_json("read it", SCHEMA, [photo])
    image = seen[0]["input"][0]["content"][1]
    assert image["type"] == "input_image" and image["image_url"].startswith("data:image/jpeg;base64,")
    with Image.open(io.BytesIO(base64.b64decode(image["image_url"].split(",", 1)[1]))) as sent:
        assert not sent.getexif() and max(sent.size) == 2048


def test_spark_tries_more_effort_when_an_answer_is_unusable_and_says_why_when_all_are(tmp_path):
    client, seen = responses(response("", status="incomplete", reason="max_output_tokens"),
                             response('{"brand": "Honda", "outlets": []}'))
    assert MuseSpark(ResponseCache(tmp_path), client=client).ask_json("q", SCHEMA)["brand"] == "Honda"
    assert [body["reasoning"]["effort"] for body in seen] == ["minimal", "low"]
    client, _ = responses(response('{"brand": "x"}'), response("not json"), httpx.Response(200, text="<html>"))
    with pytest.raises(UnusableAnswer) as error:
        MuseSpark(ResponseCache(tmp_path / "other"), efforts=("minimal", "low", "medium"),
                  client=client).ask_json("q", SCHEMA)
    message = str(error.value)
    assert "minimal: missing outlets" in message and "low: not JSON" in message and "medium: the API's reply" in message
    assert not list((tmp_path / "other").rglob("*.json"))  # nothing unusable was cached


def test_spark_waits_out_a_busy_api_and_a_refused_request_is_a_failed_read(tmp_path, monkeypatch):
    monkeypatch.setattr("aftermath.meta_api.time.sleep", lambda seconds: None)
    client, seen = responses(httpx.Response(429), response('{"brand": "Honda", "outlets": []}'))
    assert MuseSpark(ResponseCache(tmp_path), client=client).ask_json("q", SCHEMA)["brand"] == "Honda"
    assert len(seen) == 2
    client, seen = responses(httpx.Response(400, json={"error": {"message": "bad schema"}}))
    with pytest.raises(ReadFailed, match="Meta API"):
        MuseSpark(ResponseCache(tmp_path / "other"), client=client).ask_json("q", SCHEMA)
    assert len(seen) == 1  # not tried again with more effort


# The conversation's kind of schema: a few fields always there, the facts only when stated.
FACTS = {"type": "object", "required": ["language"],
         "properties": {"language": {"type": "string", "enum": ["hi", "en"]}, "co_alarm": {"type": "string",
                                                                                         "enum": ["yes", "no"]},
                        "door_height_in": {"type": "number"},
                        "burning": {"type": "array", "items": {"type": "string"}, "maxItems": 4}}}


def test_a_strict_schema_requires_every_field_and_lets_the_optional_ones_be_null():
    strict = strict_schema(FACTS)
    assert strict["required"] == ["language", "co_alarm", "door_height_in", "burning"]
    assert strict["additionalProperties"] is False
    assert strict["properties"]["language"] == FACTS["properties"]["language"]  # required: as it was
    assert strict["properties"]["co_alarm"] == {"type": ["string", "null"], "enum": ["yes", "no", None]}
    assert strict["properties"]["door_height_in"] == {"type": ["number", "null"]}
    assert strict["properties"]["burning"]["type"] == ["array", "null"]
    nested = strict_schema(SCHEMA)["properties"]["outlets"]["items"]
    assert nested["required"] == ["volts"] and nested["additionalProperties"] is False


def test_spark_answers_come_back_without_the_nulls_that_stand_for_not_stated(tmp_path):
    assert without_nulls({"language": "hi", "co_alarm": None, "door_height_in": None, "burning": None}, FACTS) == {
        "language": "hi"}
    client, _ = responses(response('{"language": "hi", "co_alarm": "yes", "door_height_in": null, "burning": null}'))
    assert MuseSpark(ResponseCache(tmp_path), client=client).ask_json("q", FACTS) == {"language": "hi",
                                                                                     "co_alarm": "yes"}
