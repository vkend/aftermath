import os
import shutil
import subprocess

import numpy as np
import pytest

from aftermath.cache import ResponseCache
from aftermath.speech import (API, Listener, MuseListener, Voice, bare_wav, ctc_greedy, to_wav16k, without_repeats,
                              write_wav)


def test_ctc_merges_repeats_once_and_keeps_double_letters_split_by_blanks():
    vocab = {0: "<pad>", 1: "l", 2: "a", 3: "m", 4: "r", 5: "|", 6: "<s>"}
    # "llamar": the two l's are separated by a blank, so they stay two letters.
    ids = [6, 1, 1, 0, 1, 2, 2, 3, 2, 0, 4, 5, 0]
    assert ctc_greedy(ids, vocab) == "llamar"


def test_wav_round_trip(tmp_path):
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(16000) / 16000)
    path = write_wav(tmp_path / "tone.wav", tone, 16000)
    out = to_wav16k(path, tmp_path / "again.wav")
    assert out.stat().st_size > 30000


@pytest.mark.skipif(not os.environ.get("AFTERMATH_MODELS") or shutil.which("say") is None,
                    reason="loads MMS models; set AFTERMATH_MODELS=1 on a Mac")
def test_a_spanish_question_round_trip(tmp_path):
    subprocess.run(["say", "-v", "Paulina", "-o", str(tmp_path / "q.aiff"),
                    "¿Puedo poner el generador en el garaje?"], check=True)
    heard = Listener().transcribe(to_wav16k(tmp_path / "q.aiff", tmp_path / "q.wav"), "es")
    assert "generador" in heard and "garaje" in heard
    voice = Voice()
    audio = voice.speak("No. Nunca en el garaje.", "es")
    assert voice.rate("es") == 16000 and len(audio) > 8000


def transcribed(tmp_path, *responses):
    """A Voice Transcribe client whose API answers with ``responses`` in turn, and the requests it got."""
    import httpx

    seen, answers = [], list(responses)

    def answer(request):
        seen.append(request)
        status, body = answers.pop(0)
        return httpx.Response(status, json=body)

    return httpx.Client(base_url=API, transport=httpx.MockTransport(answer)), seen


def test_voice_transcribe_gets_a_bare_wav_with_the_language_and_its_answer_is_cached(tmp_path):
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(8000) / 16000)
    wav = to_wav16k(write_wav(tmp_path / "said.wav", tone, 16000), tmp_path / "said16.wav")
    assert b"LIST" in wav.read_bytes()[:200]  # ffmpeg's metadata, which the API needn't see
    client, seen = transcribed(tmp_path, (200, {"sessionId": "s", "transcript": " Sí. ", "audioDurationMs": 500,
                                                "turns": []}))
    listener = MuseListener(ResponseCache(tmp_path / "cache"), client=client)
    assert listener.transcribe(wav, "es") == "Sí." and listener.transcribe(wav, "es") == "Sí."  # once, then cached
    assert len(seen) == 1 and seen[0].url.path == "/v1/asr/transcribe"
    body = seen[0].content
    assert b'"languageBias": ["Spanish"]' in body and b'"model": "muse-voice-transcribe-1.0"' in body
    assert b'"mode": "PUSH_TO_TALK"' in body and b"LIST" not in body and b"RIFF" in body


def test_voice_transcribe_backs_off_when_busy_and_never_caches_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("aftermath.meta_api.time.sleep", lambda seconds: None)
    wav = write_wav(tmp_path / "said.wav", np.zeros(1600), 16000)
    client, seen = transcribed(tmp_path, (429, {}), (200, {"transcript": "No."}), (400, {"error": "bad wav"}))
    cache = ResponseCache(tmp_path / "cache")
    assert MuseListener(cache, client=client).transcribe(wav, "es") == "No." and len(seen) == 2
    with pytest.raises(Exception):
        MuseListener(cache, hint=False, client=client).transcribe(wav, "es")  # another request: no hint
    assert b"languageBias" not in seen[-1].content and cache.misses == 2 and len(list(cache.root.glob("*/*"))) == 1


def test_voice_transcribe_needs_a_key_and_a_wav_it_takes(tmp_path, monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MODEL_API_KEY"):
        MuseListener().transcribe(write_wav(tmp_path / "said.wav", np.zeros(1600), 16000), "es")
    with pytest.raises(ValueError, match="16 or 24 kHz"):
        bare_wav(write_wav(tmp_path / "phone.wav", np.zeros(4800), 48000))


def test_voice_transcribe_hears_each_recording_with_half_a_second_of_silence_on_each_side(tmp_path):
    wav = write_wav(tmp_path / "si.wav", 0.3 * np.sin(np.arange(6400) / 3), 16000)  # 0.4 s, as short as a lone "Sí."
    assert len(bare_wav(wav, 0.5)) == len(bare_wav(wav)) + 2 * 2 * 8000  # 16-bit samples, 8000 a side
    client, seen = transcribed(tmp_path, (200, {"transcript": "Sí."}))
    listener = MuseListener(ResponseCache(tmp_path / "cache"), client=client)
    assert listener.pad_s == 0.5 and listener.request(wav, "es")["pad_s"] == 0.5
    listener.transcribe(wav, "es")
    assert len(seen[0].content) > len(bare_wav(wav, 0.5))  # the padded clip went up


@pytest.mark.parametrize("heard,meant", [
    ("घर से से दूर", "घर से दूर"), ("नॉर्मलनॉर्मल है।", "नॉर्मल है।"),
    ("पेट्रोल का का एक टैंक कितनी देर चलता चलता है?", "पेट्रोल का एक टैंक कितनी देर चलता है?"),
    ("पेट्रोलपेट्रोल का एक टैंक", "पेट्रोल का एक टैंक"), ("नहीं, नहीं।", "नहीं,"), ("Sí, sí.", "Sí,"),
    ("मेरे दादा जी", "मेरे दादा जी"), ("मामा और चाचा", "मामा और चाचा"), ("हाँ, अब बाहर है।", "हाँ, अब बाहर है।"),
])
def test_voice_transcribes_repeated_words_are_kept_once(heard, meant):
    assert without_repeats(heard) == meant
