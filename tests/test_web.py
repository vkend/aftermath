import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_door import FakeSam, door_photo

from aftermath.phrases import NOT_CAUGHT, PHRASES
from aftermath.speech import write_wav
from aftermath.web import Models, create_app


class FakeListener:
    def __init__(self, heard):
        self.heard = heard

    def transcribe(self, wav, language):
        assert wav.suffix == ".wav" and wav.stat().st_size > 44
        return self.heard


class FakeVoice:
    def speak(self, text, language):
        return np.zeros(1600)

    def rate(self, language):
        return 16000


class FakeGlimmer:
    """Reads a conversation turn or a rating plate, depending on what it's asked for."""

    def ask_json(self, prompt, schema, images=()):
        if "plate_visible" in schema["properties"]:
            return {"plate_visible": True, "brand": "Champion", "model": "201183", "running_watts": "3500",
                    "starting_watts": "4375", "volts": "120/240", "hertz": "60", "amps": "14.6", "fuel": "gasoline",
                    "co_shutoff": ""}
        return {"language": "es", "question": "", "answer": "", "generator_location": "garage"}


@pytest.fixture
def client(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 14)
    models = Models(listener=FakeListener("Está en el garaje."), voice=FakeVoice(), reader=FakeGlimmer(),
                    segmenter=FakeSam(mask))
    return TestClient(create_app(models)), photo.read_bytes()


def test_the_page_and_its_files_are_served(client):
    web, _ = client
    assert "Aftermath" in web.get("/").text
    assert web.get("/static/app.js").status_code == 200 and web.get("/static/style.css").status_code == 200


def test_a_conversation_from_start_to_a_door_photo(client, tmp_path):
    web, door = client
    start = web.post("/api/start?language=es").json()
    assert start["text"].startswith("Hola.") and start["audio"].startswith("data:audio/wav;base64,")
    assert start["placement"] == "not measured" and start["level"] == "check"

    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    turn = web.post(f"/api/talk?session_id={start['session']}", content=recording).json()
    assert turn["heard"] == "Está en el garaje." and turn["said"] == ["move-outside-now"]
    assert turn["more"] is False  # a short phrase with a place word needs no model
    assert turn["placement"] == "never indoors" and turn["level"] == "danger"
    sources = turn["advice"][0]["sources"]
    assert {s["publisher"] for s in sources} >= {"CDC", "CPSC"}
    assert all(s["url"].startswith("https://") for s in sources)

    measured = web.post(f"/api/door?session_id={start['session']}", content=door).json()
    assert measured["door"]["feet"] == pytest.approx(14, abs=0.2) and measured["refused"] is None
    assert measured["placement"] == "never indoors"  # a garage generator stays "never indoors" whatever the door says
    assert measured["outline"].startswith("data:image/jpeg;base64,") and "6%" in measured["door"]["limits"]
    assert measured["text"].endswith("Si es así, tome otra foto de la puerta desde donde quedó.")


def test_after_a_door_photo_yes_answers_the_door_question(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 26)
    models = Models(listener=FakeListener("Sí."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam(mask))
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=es").json()["session"]
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    assert web.post(f"/api/talk?session_id={sid}", content=recording).json()["placement"] == "not measured"
    measured = web.post(f"/api/door?session_id={sid}", content=photo.read_bytes()).json()
    assert measured["placement"] == "meets the guidance" and "dígame cuánto mide" in measured["text"]
    assert "supuesta" in measured["door"]["limits"]
    turn = web.post(f"/api/talk?session_id={sid}", content=recording).json()  # "Sí." again
    assert turn["more"] is False and "como me dijo" in turn["door"]["limits"]
    assert "ask-co-alarm" in [a["rule"] for a in turn["advice"]]  # the "sí" was about the door, not the alarm


def test_a_longer_turn_comes_in_two_parts(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 14)
    heard = "El generador está en el garaje y tengo una pregunta sobre la gasolina."
    models = Models(listener=FakeListener(heard), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam(mask))
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=es").json()["session"]
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    first = web.post(f"/api/talk?session_id={sid}", content=recording).json()
    assert first["more"] is True and first["said"] == ["move-outside-now"] and first["audio"]
    rest = web.post(f"/api/talk/more?session_id={sid}").json()
    assert rest["more"] is False and "move-outside-now" not in rest["said"] and rest["text"]


def test_the_rating_plate_is_read_back(client):
    web, _ = client
    sid = web.post("/api/start?language=en").json()["session"]
    plate = web.post(f"/api/plate?session_id={sid}", content=b"\xff\xd8 a photo").json()
    assert plate["text"].startswith("I read: Champion 201183, 3,500 running watts and 4,375 starting watts")
    assert plate["plate"]["running_watts"] == 3500


def test_mistakes_get_clear_errors(client):
    web, _ = client
    assert web.post("/api/talk?session_id=nope", content=b"x").status_code == 404
    sid = web.post("/api/start?language=es").json()["session"]
    assert web.post(f"/api/door?session_id={sid}", content=b"").status_code == 400
    assert web.post("/api/start?language=fr").status_code == 400
    assert {"cdc-distance", "nist-25ft"} <= {s["id"] for s in web.get("/api/sources").json()}


def test_one_moment_is_ready_in_every_language(client):
    web, _ = client
    moment = web.get("/api/moment?language=en").json()
    assert moment["text"] == "One moment." and moment["audio"].startswith("data:audio/wav;base64,")
    assert web.get("/api/moment?language=hi").json()["text"] == "एक पल।"
    assert web.get("/api/moment?language=fr").status_code == 400


def test_a_hindi_conversation_starts_in_hindi_and_shows_hindi_sources_beside_english_ones(client):
    web, _ = client
    start = web.post("/api/start").json()  # Hindi unless the page asks for another language
    assert start["language"] == "hi" and start["text"].startswith("नमस्ते।")
    sources = [s for a in start["advice"] for s in a["sources"]]
    assert {s["language"] for s in sources} == {"en", "hi"}
    assert any(s["quote"].startswith("घर के अंदर कभी भी जनरेटर का इस्तेमाल न करें") for s in sources)
    english = web.post("/api/start?language=en").json()
    assert {s["language"] for a in english["advice"] for s in a["sources"]} == {"en"}


def test_with_keep_every_recording_and_photo_is_saved_with_what_the_app_heard(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 26)
    models = Models(listener=FakeListener("Sí."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam(mask))
    keep = tmp_path / "kept"
    web = TestClient(create_app(models, keep=keep))
    sid = web.post("/api/start?language=es").json()["session"]
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    web.post(f"/api/talk?session_id={sid}", content=recording, headers={"content-type": "audio/mp4"})
    web.post(f"/api/door?session_id={sid}", content=photo.read_bytes())
    web.post(f"/api/plate?session_id={sid}", content=b"\xff\xd8 a photo")
    log = [json.loads(line) for line in (keep / "log.jsonl").read_text().splitlines()]
    assert [entry["kind"] for entry in log] == ["talk", "door", "plate"]
    assert log[0]["heard"] == "Sí." and log[0]["file"].endswith("-talk.m4a")
    assert log[1]["feet"] == pytest.approx(26, abs=0.3) and log[1]["refused"] is None
    assert all((keep / entry["file"]).exists() for entry in log)


def test_without_keep_nothing_is_saved(client, tmp_path):
    web, door = client
    sid = web.post("/api/start?language=es").json()["session"]
    web.post(f"/api/door?session_id={sid}", content=door)
    assert not list(tmp_path.glob("**/log.jsonl"))


def test_after_the_plate_is_read_back_a_yes_is_about_the_plate_not_the_question_before(tmp_path):
    models = Models(listener=FakeListener("Sí."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam())
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=es").json()["session"]  # it asks whether the generator is outside
    plate = web.post(f"/api/plate?session_id={sid}", content=b"\xff\xd8 a photo").json()
    assert plate["text"].endswith("¿Es correcto?")
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    turn = web.post(f"/api/talk?session_id={sid}", content=recording).json()
    assert turn["more"] is False  # a plain answer about the plate: no model needed
    assert turn["text"].endswith(PHRASES["measure-distance"]["es"])  # still asked: the "sí" wasn't "it's outside"


def test_after_a_refused_door_photo_a_yes_is_not_taken_as_an_answer(tmp_path):
    photo, _ = door_photo(tmp_path / "door.jpg", 26)
    models = Models(listener=FakeListener("Sí."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam())
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=es").json()["session"]
    refused = web.post(f"/api/door?session_id={sid}", content=photo.read_bytes()).json()
    assert refused["refused"] == "no-door"  # no door in it
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    turn = web.post(f"/api/talk?session_id={sid}", content=recording).json()
    assert turn["more"] is True and turn["text"] == ""  # not "yes, it's outside": the model reads it, guarded


def test_a_door_photo_with_no_lens_data_counts_only_once_the_person_says_it_was_1x(tmp_path):
    photo, mask = door_photo(tmp_path / "door.jpg", 26, focal=False)  # iPhone Safari's own camera leaves it out
    models = Models(listener=FakeListener("Sí."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam(mask))
    web = TestClient(create_app(models, keep=tmp_path / "kept"))
    sid = web.post("/api/start?language=es").json()["session"]
    first = web.post(f"/api/door?session_id={sid}", content=photo.read_bytes()).json()
    assert first["refused"] is None and first["placement"] == "if at 1x"
    assert first["text"].startswith(PHRASES["if-1x"]["es"].split(".")[0])
    assert first["text"].endswith(PHRASES["confirm-1x"]["es"])
    assert "lens-assumed" not in first["door"]["warnings"] and first["door"]["warnings"][0].startswith("Esta foto no")
    assert first["door"]["feet"] == pytest.approx(26 * 23 / 24, abs=0.1)  # read through 23 mm, not the 24 it was
    kept = json.loads((tmp_path / "kept" / "log.jsonl").read_text().splitlines()[-1])
    assert kept["lens_assumed"] is True and kept["focal"].startswith("assumed 23 mm")
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    turn = web.post(f"/api/talk?session_id={sid}", content=recording).json()  # "Sí."
    assert turn["more"] is False and turn["placement"] == "if outside"  # at 1×: now only "is it outside?"


def test_the_laptop_listens_with_mms_or_with_voice_transcribe(tmp_path, monkeypatch):
    from aftermath.speech import Listener, MuseListener
    from aftermath.web import local_models

    monkeypatch.setattr("aftermath.segment.LocalSam31", lambda cache: None)
    monkeypatch.setattr("aftermath.vlm.LocalGlimmer", lambda cache, max_tokens: None)
    assert isinstance(local_models(tmp_path).listener, Listener)
    assert isinstance(local_models(tmp_path, "muse").listener, MuseListener)


class CountingVoice(FakeVoice):
    def __init__(self):
        self.said = []

    def speak(self, text, language):
        self.said.append(text)
        return super().speak(text, language)


def test_the_coachs_fixed_lines_are_spoken_once_and_kept(tmp_path):
    voice, speech = CountingVoice(), tmp_path / "speech"
    models = Models(listener=FakeListener("Sí."), voice=voice, reader=FakeGlimmer(), segmenter=FakeSam())
    web = TestClient(create_app(models, speech=speech))
    first, again = (web.post("/api/start?language=hi").json() for _ in range(2))
    assert first["audio"] == again["audio"] and voice.said.count(first["text"]) == 1  # the opening, once
    assert len(list(speech.glob("*/*.wav"))) == 1
    later = TestClient(create_app(Models(listener=None, voice=CountingVoice(), reader=FakeGlimmer(),
                                         segmenter=FakeSam()), speech=speech))
    assert later.post("/api/start?language=hi").json()["audio"] == first["audio"]  # from disk, after a restart


def test_a_heic_plate_photo_is_read_as_a_jpeg(client, monkeypatch):
    web, _ = client
    converted = []

    def readable(path, workdir):
        converted.append(path.suffix)
        jpeg = workdir / "plate-converted.jpg"
        jpeg.write_bytes(b"\xff\xd8 a photo")
        return jpeg

    monkeypatch.setattr("aftermath.web.readable", readable)
    sid = web.post("/api/start?language=en").json()["session"]
    plate = web.post(f"/api/plate?session_id={sid}", content=b"\x00\x00\x00\x18ftypheic a photo").json()
    assert converted == [".heic"] and plate["plate"]["running_watts"] == 3500


def test_when_the_reader_cant_be_reached_the_coach_asks_again_instead_of_failing(tmp_path):
    from test_conversation import Unreachable

    models = Models(listener=FakeListener("My brother set it up last night."), voice=FakeVoice(),
                    reader=Unreachable(), segmenter=FakeSam())
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=en").json()["session"]
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    assert web.post(f"/api/talk?session_id={sid}", content=recording).json()["more"] is True
    rest = web.post(f"/api/talk/more?session_id={sid}")
    assert rest.status_code == 200 and rest.json()["text"].startswith(NOT_CAUGHT["en"])
    plate = web.post(f"/api/plate?session_id={sid}", content=b"\xff\xd8 a photo")
    assert plate.status_code == 200 and plate.json()["text"].startswith("I can't read a rating plate")


def test_the_reminder_plans_the_check_in_and_links_back_to_it(client):
    web, _ = client
    sid = web.post("/api/start?language=en").json()["session"]
    assert web.get(f"/api/summary?session_id={sid}&tz=America/New_York").json()["text"].startswith(
        "Generator check-in summary,")
    reminder = web.get(f"/api/checkin.ics?session_id={sid}&at=2099-10-30T06:00:00Z")
    assert reminder.status_code == 200 and reminder.headers["content-type"].startswith("text/calendar")
    unfolded = reminder.text.replace("\r\n ", "")
    assert f"URL:http://testserver/?checkin={sid}&language=en\r\n" in unfolded
    assert "DTSTART:20991030T060000Z" in unfolded and "SUMMARY:Generator check-in" in unfolded
    text = web.get(f"/api/summary?session_id={sid}&tz=America/New_York").json()["text"]
    assert "Check-in planned for 2:00 AM." in text
    web.get(f"/api/checkin.ics?session_id={sid}&at=2020-10-30T06:00:00Z")  # one whose time has passed
    text = web.get(f"/api/summary?session_id={sid}&tz=America/New_York").json()["text"]
    assert "No answer at the 2:00 AM check-in." in text
    assert web.get(f"/api/checkin.ics?session_id={sid}&at=tonight").status_code == 400
    assert web.get(f"/api/checkin.ics?session_id={sid}&at=2026-10-30T02:00:00").status_code == 400  # no offset
    assert web.get(f"/api/summary?session_id={sid}&tz=Not/A_Zone").status_code == 200  # falls back to UTC


def test_the_reminder_links_to_the_address_it_is_given_not_the_laptops_name():
    models = Models(listener=FakeListener("No."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam())
    web = TestClient(create_app(models, link="https://192.0.2.10:8443"), base_url="https://someones-mac.local:8443")
    sid = web.post("/api/start?language=hi").json()["session"]
    text = web.get(f"/api/checkin.ics?session_id={sid}&at=2099-10-30T06:00:00Z").text.replace("\r\n ", "")
    assert f"URL:https://192.0.2.10:8443/?checkin={sid}&language=hi" in text and "someones" not in text


def test_checking_in_now_asks_the_check_in_questions_and_the_summary_reports_them(tmp_path):
    from aftermath.phrases import CHECKIN_ASK, CHECKIN_HELLO

    models = Models(listener=FakeListener("No."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam())
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=en").json()["session"]
    start = web.post(f"/api/checkin/start?session_id={sid}").json()
    assert start["session"] == sid and start["checkin"] is True
    assert start["text"] == f"{CHECKIN_HELLO['en']} {CHECKIN_ASK['checkin-symptoms']['en']}" and start["audio"]
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    turn = web.post(f"/api/talk?session_id={sid}", content=recording).json()  # "No.": nobody feels sick
    assert turn["more"] is False and turn["text"] == CHECKIN_ASK["checkin-outside"]["now"]["en"]
    text = web.get(f"/api/summary?session_id={sid}").json()["text"]
    assert "- Anyone with a headache, dizziness, weakness or nausea: no." in text
    assert "- Generator outside: no answer." in text


def test_a_check_in_for_a_conversation_that_is_gone_starts_from_nothing():
    from aftermath.phrases import CHECKIN_HELLO

    models = Models(listener=FakeListener("No."), voice=FakeVoice(), reader=FakeGlimmer(), segmenter=FakeSam())
    web = TestClient(create_app(models))
    start = web.post("/api/checkin/start?session_id=gone&language=hi").json()
    assert start["session"] != "gone" and start["text"].startswith(CHECKIN_HELLO["hi"])
    assert start["placement"] == "not measured" and start["checkin"] is True
    text = web.get(f"/api/summary?session_id={start['session']}").json()["text"]
    assert "The conversation before this check-in wasn't on record (the laptop restarted)" in text
    assert web.post("/api/checkin/start?session_id=gone&language=fr").status_code == 400



# The page starts in Hindi before its script runs: those words must be the reviewed ones in phrases.PAGE.
STARTS_IN_HINDI = {"subtitle": "subtitle", "welcome-text": "welcome", "begin": "begin", "talk": "talk",
                   "door-label": "door", "plate-label": "plate", "advice-title": "adviceTitle", "not-911": "notNine11",
                   "checkin-banner": "checkinBanner", "tonight-title": "tonight", "time-label": "checkinTime",
                   "add-calendar": "addCalendar", "check-now": "checkNow", "note-label": "note", "share": "share",
                   "preview-label": "preview", "listen": "listen"}


def test_the_page_gets_its_words_from_phrases_and_starts_with_the_same_hindi(client):
    import re

    from aftermath.phrases import PAGE
    from aftermath.web import STATIC

    web, _ = client
    assert web.get("/api/text").json() == PAGE and PAGE["hi"].keys() == PAGE["en"].keys() == PAGE["es"].keys()
    html = (STATIC / "index.html").read_text()
    for element, name in STARTS_IN_HINDI.items():
        shown = re.search(rf'id="{element}"[^>]*>([^<]*)<', html).group(1).strip()
        assert shown == PAGE["hi"][name], element


def test_a_near_photo_then_a_far_one_with_its_lens_and_a_retake_end_on_the_verdict(tmp_path):
    near, near_mask = door_photo(tmp_path / "near.jpg", 8.5, focal=False)  # Take Photo leaves the lens out
    far, far_mask = door_photo(tmp_path / "far.jpg", 30)  # a Camera-app photo from Photo Library keeps it
    models = Models(listener=FakeListener("हाँ, बाहर है"), voice=FakeVoice(), reader=FakeGlimmer(),
                    segmenter=FakeSam(near_mask))
    web = TestClient(create_app(models))
    sid = web.post("/api/start?language=hi").json()["session"]
    first = web.post(f"/api/door?session_id={sid}", content=near.read_bytes()).json()
    assert first["placement"] == "too close" and first["text"].endswith(PHRASES["confirm-outside"]["hi"])
    models.segmenter = FakeSam(far_mask)
    for _ in range(2):  # the second is a retake
        second = web.post(f"/api/door?session_id={sid}", content=far.read_bytes()).json()
        assert second["placement"] == "if outside" and second["text"].endswith(PHRASES["confirm-outside"]["hi"])
    recording = write_wav(tmp_path / "said.wav", 0.1 * np.sin(np.arange(16000) / 5), 16000).read_bytes()
    turn = web.post(f"/api/talk?session_id={sid}", content=recording).json()
    assert turn["more"] is False and turn["placement"] == "meets the guidance"
    assert turn["door"]["feet"] == pytest.approx(30, abs=0.3)
