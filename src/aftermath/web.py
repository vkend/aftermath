"""The phone page and its API: talk, photograph the door and the rating plate, and see what the rules say and why.

`aftermath serve` runs it over HTTPS with the local certificate (scripts/make_certs.sh), because a phone's browser
only allows the microphone on a secure page. Each browser tab gets its own conversation, kept in memory. The models
run one request at a time behind a lock. Photos and recordings are read and dropped, unless ``keep`` names a folder
(``serve --keep``, for testing with real voices and photos), where each is saved with a line in log.jsonl saying
what the app heard and said. With the local models nothing a person sends leaves the laptop; in API mode
(``--listen muse``, ``--think spark``) the recording, the words heard and a rating plate's photo (without its
metadata) go to the Meta Model API. Door photos never do.
"""

import base64
import hashlib
import io
import json
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .checkin import Record, calendar, summary
from .conversation import Conversation
from .door import ERROR, DoorReading, measure, overlay, readable
from .guidance import SOURCES
from .phrases import PAGE, door_note, plate_read, read_back, say
from .plate import Plate, read_plate
from .rules import Situation, assess

STATIC = Path(__file__).parent / "static"
LIMIT = 25 * 1024 * 1024  # bytes: the largest photo or recording accepted
HEIC = (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc")  # bytes 4–12 of an iPhone photo kept as HEIC
MOMENT = {"es": "Un momento.", "en": "One moment.", "hi": "एक पल।"}
VOICED = 256  # spoken lines kept in memory
LANGUAGES = ("hi", "en", "es")


@dataclass
class Models:
    """Everything that thinks or speaks, built on first use (tests pass their own)."""

    listener: object  # .transcribe(wav, language) -> str
    voice: object  # .speak(text, language) -> samples; .rate(language) -> int
    reader: object  # .ask_json(prompt, schema, images) -> dict  (Muse Glimmer, or Muse Spark)
    segmenter: object  # .segment(image, phrases) -> {phrase: [Instance]}  (SAM 3.1)


def local_models(cache_dir: Path, listen: str = "mms", think: str = "glimmer") -> Models:
    """The models on this laptop; with ``listen="muse"``, speech is heard by Muse Voice Transcribe on the Meta Model
    API instead of MMS, and with ``think="spark"``, turns and plates are read by Muse Spark there instead of Glimmer
    (the key in MODEL_API_KEY). The door is always measured here, and the voice is always this laptop's."""
    from .cache import ResponseCache
    from .segment import LocalSam31
    from .speech import Listener, MuseListener, Voice
    from .vlm import LocalGlimmer, MuseSpark

    cache = ResponseCache(cache_dir)
    listener = MuseListener(cache) if listen == "muse" else Listener(cache)
    reader = MuseSpark(cache) if think == "spark" else LocalGlimmer(cache, max_tokens=600)
    return Models(listener=listener, voice=Voice(), reader=reader, segmenter=LocalSam31(cache))


@dataclass
class Session:
    talk: Conversation  # the check-in's, once one has begun
    door: DoorReading | None = None
    plate: Plate | None = None
    log: list[dict] = field(default_factory=list)
    measured_at: float | None = None  # when the door was photographed (epoch seconds, like the times below)
    due: float | None = None  # when the overnight check-in is planned for
    checked_at: float | None = None  # when the latest check-in began
    before: Situation | None = None  # the situation it began from
    lost: bool = False  # it began from nothing: the conversation it came from was gone


def create_app(models: Models | Callable[[], Models], keep: Path | None = None,
               speech: Path | None = None, link: str | None = None) -> FastAPI:
    """The app. ``keep`` saves what people send (for testing with real voices); ``speech`` keeps the coach's fixed
    lines as spoken WAVs, so they're synthesised once (``serve`` puts them in data/cache/speech/). ``link`` is the
    address the check-in reminder links to, such as ``https://<laptop-ip>:8443``: ``serve`` gives the laptop's
    network address, because its .local name often carries its owner's name."""
    app = FastAPI(title="Aftermath")
    sessions: dict[str, Session] = {}
    lock = threading.Lock()
    loaded: list[Models] = []
    kept: list[int] = [0]

    def keeping(kind: str, sid: str, record: dict, data: bytes | None = None, suffix: str = "") -> None:
        """With ``keep``, a line in its log.jsonl, and the upload saved beside it; otherwise nothing."""
        if keep is None:
            return
        keep.mkdir(parents=True, exist_ok=True)
        kept[0] += 1
        name = f"{time.strftime('%Y%m%d-%H%M%S')}-{kept[0]:03d}-{kind}{suffix}" if data is not None else None
        if name:
            (keep / name).write_bytes(data)
        line = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "file": name, "session": sid, **record}
        with (keep / "log.jsonl").open("a") as log:
            log.write(json.dumps(line, ensure_ascii=False) + "\n")

    def get_models() -> Models:
        if not loaded:
            loaded.append(models() if callable(models) else models)
        return loaded[0]

    def session(sid: str) -> Session:
        if sid not in sessions:
            raise HTTPException(404, "no such conversation; start again")
        return sessions[sid]

    voiced: OrderedDict[tuple[str, str], str] = OrderedDict()  # the latest lines spoken, at most VOICED

    def spoken(text: str, language: str) -> str:
        """The text as a WAV data URL, in the conversation's language. The coach's questions, dangers and other fixed
        lines come round again, so each is synthesised once and kept: on disk in ``speech``, and the latest in
        memory."""
        from .speakable import chunks
        from .speech import VOICES, write_wav

        if (language, text) in voiced:
            voiced.move_to_end((language, text))
            return voiced[(language, text)]
        name = hashlib.sha256(json.dumps([VOICES.get(language), chunks(text, language)]).encode()).hexdigest()
        file = speech / name[:2] / f"{name}.wav" if speech is not None else None
        if file is not None and file.exists():
            data = file.read_bytes()
        else:
            voice = get_models().voice
            audio = voice.speak(text, language) if text else np.zeros(1)
            buffer = io.BytesIO()
            write_wav(buffer, audio, voice.rate(language))
            data = buffer.getvalue()
        url = "data:audio/wav;base64," + base64.b64encode(data).decode()
        voiced[(language, text)] = url
        if len(voiced) > VOICED:
            voiced.popitem(last=False)
        if file is not None and not file.exists():
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        return url

    def state(s: Session) -> dict:
        """What the page shows besides the reply: the verdict on placement, the measurement, and the sources. The
        distance is the conversation's, which follows the door height the person gives."""
        talk, language = s.talk, s.talk.language
        result, feet = assess(talk.situation), talk.situation.measured_ft
        door = None
        if s.door is not None and feet is not None:
            height = door_note("door-height-given" if talk.door_checked else "door-height-assumed", language,
                               inches=talk.door_in)
            door = {"feet": round(feet, 1), "lowest": round(talk.situation.lowest_ft, 1),
                    "highest": round(feet / (1 - ERROR), 1), "error": ERROR, "door_in": talk.door_in,
                    "limits": f"{height} {door_note('error-limits', language, error=ERROR)}",
                    "warnings": [door_note(w, language, tilt=s.door.values.get("tilt_deg", 0))
                                 for w in s.door.warnings]}
        return {"placement": result.placement, "verdict": say(result.headline, language),
                "level": result.headline.level.name.lower(), "door": door, "language": language,
                "checkin": bool(talk.checkin), "due": s.due,
                "advice": [{"rule": a.rule, "level": a.level.name.lower(), "text": say(a, language),
                            "sources": [{"publisher": SOURCES[i].publisher, "url": SOURCES[i].url,
                                         "quote": SOURCES[i].quote, "language": SOURCES[i].language}
                                        for i in a.sources if SOURCES[i].language in ("en", language)]}
                           for a in result.advice]}

    async def body(request: Request) -> bytes:
        data = await request.body()
        if not data:
            raise HTTPException(400, "empty upload")
        if len(data) > LIMIT:
            raise HTTPException(413, "too large")
        return data

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.post("/api/start")
    def start(language: str = "hi") -> JSONResponse:
        if language not in LANGUAGES:
            raise HTTPException(400, "language must be hi, en or es")
        with lock:
            talk = Conversation(get_models().reader, language=language)
            sid = uuid.uuid4().hex
            s = sessions[sid] = Session(talk)
            text = talk.opening()
            s.log.append({"coach": text})
            return JSONResponse({"session": sid, "text": text, "audio": spoken(text, language), **state(s)})

    @app.post("/api/talk")
    async def talk(request: Request, session_id: str) -> JSONResponse:
        """A spoken turn, first part: what was heard, and what needs no model (an emergency, a dangerous place, or
        the whole reply to a short answer). ``more`` says the page should ask /api/talk/more for the rest."""
        data = await body(request)
        s = session(session_id)
        with lock, tempfile.TemporaryDirectory() as tmp:
            from .speech import to_wav16k

            raw = Path(tmp) / "said"
            raw.write_bytes(data)
            heard = get_models().listener.transcribe(to_wav16k(raw, Path(tmp) / "said.wav"), s.talk.language)
            reply = s.talk.quick(heard)
            s.log.append({"person": heard})
            if reply.text:
                s.log.append({"coach": reply.text})
            audio = spoken(reply.text, s.talk.language) if reply.text else None
            kind = (request.headers.get("content-type") or "").split(";")[0]
            suffix = {"audio/mp4": ".m4a", "audio/webm": ".webm", "audio/wav": ".wav"}.get(kind, ".audio")
            keeping("talk", session_id, {"language": s.talk.language, "heard": heard, "text": reply.text,
                                         "said": reply.said, "more": reply.pending}, data, suffix)
            return JSONResponse({"heard": heard, "text": reply.text, "said": reply.said, "audio": audio,
                                 "more": reply.pending, **state(s)})

    @app.post("/api/talk/more")
    def more(session_id: str) -> JSONResponse:
        """A spoken turn, second part: the model reads what the person said, and the reply goes on from there."""
        s = session(session_id)
        with lock:
            reply = s.talk.finish()
            if reply.text:
                s.log.append({"coach": reply.text})
            audio = spoken(reply.text, s.talk.language) if reply.text else None
            keeping("talk-more", session_id, {"read": reply.heard, "text": reply.text, "said": reply.said})
            return JSONResponse({"text": reply.text, "said": reply.said, "audio": audio, "more": False, **state(s)})

    @app.post("/api/door")
    async def door(request: Request, session_id: str, leaf_height_in: float | None = None) -> JSONResponse:
        """A photo of the door from where the generator stands. The door's height is the one the person gave, or
        ``leaf_height_in``, or a regular door's; while it's assumed, the coach asks about it."""
        data = await body(request)
        s = session(session_id)
        language = s.talk.language
        if leaf_height_in is not None:
            s.talk.door_height(leaf_height_in)
        with lock, tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / ("door.heic" if data[4:12] in HEIC else "door.jpg")
            photo.write_bytes(data)
            reading = measure(photo, get_models().segmenter, s.talk.door_in)
            picture = overlay(photo, reading, Path(tmp), label=False).read_bytes()
            outline = "data:image/jpeg;base64," + base64.b64encode(picture).decode()
            if reading.refused:
                text = door_note(reading.refused, language)
                s.talk.photo_refused()  # a "sí" to "take it again" answers nothing asked before
            else:
                s.door, s.measured_at = reading, time.time()
                text = s.talk.reply("", door=(reading.feet, reading.lowest_ft),
                                    lens_assumed=bool(reading.values.get("lens_assumed"))).text
            audio = spoken(text, language)
            keeping("door", session_id, {"feet": reading.feet, "lowest_ft": reading.lowest_ft,
                                         "refused": reading.refused, "warnings": reading.warnings,
                                         "door_in": s.talk.door_in, "focal": reading.values.get("focal_source"),
                                         "lens_assumed": reading.values.get("lens_assumed"),
                                         "camera": reading.values.get("camera"), "text": text}, data, photo.suffix)
        s.log.append({"coach": text})
        return JSONResponse({"text": text, "audio": audio, "outline": outline, "refused": reading.refused,
                             **state(s)})

    @app.post("/api/plate")
    async def plate(request: Request, session_id: str) -> JSONResponse:
        data = await body(request)
        s = session(session_id)
        with lock, tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / ("plate.heic" if data[4:12] in HEIC else "plate.jpg")
            photo.write_bytes(data)
            s.plate = read_plate(get_models().reader, readable(photo, Path(tmp)))  # a HEIC as a JPEG
            language = s.talk.language
            text = read_back(s.plate, language)
            # The next "sí" is about the plate, not the question before; with nothing read, nothing is asked.
            s.talk.plate_read_back(s.plate.visible and bool(plate_read(s.plate, language)))
            audio = spoken(text, language)
            plate = {k: getattr(s.plate, k) for k in ("brand", "model", "running_watts", "starting_watts", "volts",
                                                       "fuel", "problems")}
            keeping("plate", session_id, {"plate": plate, "text": text}, data,
                    ".heic" if data[4:12] in HEIC else ".jpg")
        s.log.append({"coach": text})
        fields = {k: getattr(s.plate, k) for k in ("brand", "model", "running_watts", "starting_watts", "volts",
                                                    "fuel", "co_shutoff", "problems")}
        return JSONResponse({"text": text, "audio": audio, "plate": fields, **state(s)})

    @app.get("/api/checkin.ics")
    def reminder(request: Request, session_id: str, at: str) -> Response:
        """The reminder for the phone's calendar: an event at ``at`` (an ISO time with its offset) whose link reopens
        this page for the check-in. Opening it plans the check-in for then (a plain link, because a phone opens a
        calendar file only from a tap). It holds the page's address and nothing about the person."""
        s = session(session_id)
        try:
            due = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "at must be an ISO time") from None
        if due.tzinfo is None:
            raise HTTPException(400, "at needs its offset from UTC")
        s.due = due.timestamp()
        language = s.talk.language
        url = f"{(link or str(request.base_url)).rstrip('/')}/?checkin={session_id}&language={language}"
        text = calendar(url, datetime.fromtimestamp(s.due, UTC), language, f"{session_id}-{s.due:.0f}@aftermath",
                        datetime.now(UTC))
        return Response(text, media_type="text/calendar",
                        headers={"Content-Disposition": 'inline; filename="check-in.ics"'})

    @app.post("/api/checkin/start")
    def check_in(session_id: str | None = None, language: str = "hi") -> JSONResponse:
        """The check-in, carrying on from the conversation, now ("check in now") or from the reminder. If the
        conversation is gone (the laptop restarted), it begins from nothing, in the reminder's language."""
        if session_id not in sessions and language not in LANGUAGES:
            raise HTTPException(400, "language must be hi, en or es")
        with lock:
            if session_id in sessions:
                s = sessions[session_id]
                s.before, s.talk = s.talk.situation, s.talk.check_in()
            else:
                session_id = uuid.uuid4().hex
                s = sessions[session_id] = Session(Conversation(get_models().reader, language=language).check_in(),
                                                   lost=True)
            s.checked_at = time.time()
            text = s.talk.opening()
            s.log.append({"coach": text})
            return JSONResponse({"session": session_id, "text": text, "audio": spoken(text, s.talk.language),
                                 **state(s)})

    @app.get("/api/summary")
    def family_summary(session_id: str, tz: str = "UTC") -> JSONResponse:
        """The summary for the family, in plain English, with times in the phone's zone ``tz``."""
        s = session(session_id)
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            zone = UTC

        def at(t: float | None) -> datetime | None:
            return datetime.fromtimestamp(t, zone) if t is not None else None

        record = Record(talk=s.talk, before=s.before, measured_at=at(s.measured_at), due=at(s.due),
                        checked_at=at(s.checked_at), lost=s.lost)
        return JSONResponse({"text": summary(record, datetime.now(zone))})

    moments: dict[str, str] = {}

    @app.get("/api/moment")
    def moment(language: str = "es") -> JSONResponse:
        """A short "one moment", spoken right after the person stops talking, while the reply is worked out."""
        if language not in MOMENT:
            raise HTTPException(400, "language must be hi, en or es")
        if language not in moments:
            with lock:
                moments[language] = spoken(MOMENT[language], language)
        return JSONResponse({"text": MOMENT[language], "audio": moments[language]})

    @app.get("/api/text")
    def page_text() -> dict:
        """The page's own words, in every language."""
        return PAGE

    @app.get("/api/sources")
    def sources() -> list[dict]:
        return [vars(s) for s in SOURCES.values()]

    return app

