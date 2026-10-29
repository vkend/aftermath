"""Muse Voice Transcribe against MMS on short answers, in Spanish, English and Hindi.

macOS voices (and the app's own MMS voices) say each answer, and both listeners hear the same 16 kHz WAV: MMS-1B
with the language's adapter on this machine, and Voice Transcribe through the Meta Model API with the language as
a hint. Each transcript is scored word for word, and by what the conversation does with it at once
(conversation.py), next to what it does with the answer itself: "same"; "safe miss" (nothing wrong is taken as
said: the person is asked again, or the model reads it); "wrong, cautious" (a wrong answer that adds a danger);
"clears a danger" (a wrong answer that takes one off the list, the failure that matters).

MMS loads its models from the Hugging Face cache, so it runs first; the second run replays MMS from the cache and
adds Voice Transcribe, with a Meta Model API key in MODEL_API_KEY:

    uv run --offline python scripts/compare_listeners.py --engines mms
    uv run --offline python scripts/compare_listeners.py

Clips and results go to data/runs/listeners/ (git-ignored). Answers are cached in data/cache/, so a re-run replays
them, with the latency measured when they ran. Voice Transcribe bills whole seconds of audio, at $0.18 an hour.
These are synthetic voices on clean audio: real phone recordings come later.
"""

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import time
import unicodedata
import wave
from dataclasses import asdict
from pathlib import Path

import numpy as np

from aftermath.cache import ResponseCache
from aftermath.conversation import Conversation
from aftermath.rules import Level, Situation, assess
from aftermath.speech import Listener, MuseListener, Voice, to_wav16k, write_wav

RATE = 16000
LANGUAGES = {  # the voices, and each answer with the coach's question it answers
    "es": (["Paulina", "Mónica", "Eddy (Spanish (Mexico))", "Flo (Spanish (Mexico))", "Grandpa (Spanish (Mexico))",
            "MMS-TTS"],
           [("Sí.", "ask-co-alarm"), ("No.", "ask-downed-lines"), ("No sé.", "ask-downed-lines"),
            ("Sí, tengo.", "ask-co-alarm"), ("Creo que sí.", "ask-co-alarm")]),
    "en": (["Samantha", "Reed (English (US))", "Eddy (English (US))", "Grandpa (English (US))"],
           [("Yes.", "ask-co-alarm"), ("No.", "ask-downed-lines"), ("I don't know.", "ask-downed-lines"),
            ("Yes, I have one.", "ask-co-alarm"), ("I think so.", "ask-co-alarm")]),
    "hi": (["Lekha", "MMS-TTS"],
           [("हाँ", "ask-co-alarm"), ("नहीं", "ask-downed-lines"), ("पता नहीं", "ask-downed-lines"),
            ("हाँ, बाहर है", "ask-moved-outside"), ("नहीं है", "ask-co-alarm")]),
}
ENGINES = ("mms", "muse")
CONDITIONS = ("raw", "padded")  # the clip as the voice said it, and with PAD_S of silence on each side
PAD_S = 0.5
PRICE_PER_SECOND = 0.18 / 3600

# A situation in which each question comes next (as in tests/test_conversation.py).
OUT = {"location": "outdoors", "measured_ft": 30.0, "lowest_ft": 28.3}
BEFORE = {
    "ask-moved-outside": Situation(location="garage"),
    "ask-co-alarm": Situation(**OUT, exhaust_toward_house=False),
    "ask-downed-lines": Situation(**OUT, exhaust_toward_house=False, co_alarm=True, burning_indoors=frozenset()),
}
# The values that take a danger off the list.
REASSURING = {"location": "outdoors", "co_alarm": True, "downed_line": False}


class NoModel:
    """Glimmer's stand-in. What counts here is what the conversation does before the model reads anything."""

    def ask_json(self, prompt, schema, images=()):
        raise AssertionError("the quick part of a turn never calls the model")


def handled(heard: str, rule: str, language: str) -> dict:
    """What the conversation does at once with these words, said in answer to ``rule``."""
    talk = Conversation(NoModel(), language=language, situation=BEFORE[rule], door_checked=True)
    talk.reply("")
    assert talk.asked == rule, (rule, talk.asked)
    before = asdict(talk.situation)
    reply = talk.quick(heard)
    changed = {k: v for k, v in asdict(talk.situation).items() if v != before[k]}
    levels = {a.rule: a.level for a in assess(talk.situation).advice}
    dangers = sorted(r for r in reply.said if levels.get(r) in (Level.EMERGENCY, Level.DANGER))
    return {"changed": changed, "dangers": dangers, "model": reply.pending, "unanswered": talk.unanswered}


def describe(outcome: dict) -> str:
    parts = [f"{k}={v}" for k, v in outcome["changed"].items()] + [f"says {d}" for d in outcome["dangers"]]
    if outcome["unanswered"]:
        parts.append({"unclear": "asked again", "unsure": "left for later"}[outcome["unanswered"]])
    if outcome["model"]:
        parts.append("the model reads it")
    return ", ".join(parts) or "nothing"


def verdict(heard: dict, said: dict) -> str:
    if heard == said:
        return "same"
    wrong = {k: v for k, v in heard["changed"].items() if said["changed"].get(k, object()) != v}
    if any(REASSURING.get(k) == v for k, v in wrong.items()):
        return "clears a danger"
    if wrong or set(heard["dangers"]) - set(said["dangers"]):
        return "wrong, cautious"
    return "safe miss"


def words(text: str) -> list[str]:
    """Lower case, without punctuation or symbols (Devanagari's vowel signs are marks, which \\w would drop); in
    Hindi, chandrabindu as anusvara and no nukta, since spellings vary."""
    text = unicodedata.normalize("NFC", text.lower()).replace("ँ", "ं").replace("़", "")
    return "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text).split()


def folded(text: str) -> list[str]:
    return [unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode() or w for w in words(text)]


def edits(a: list[str], b: list[str]) -> int:
    """Word-level edit distance."""
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row, last = [i], row
        for j, y in enumerate(b, 1):
            row.append(min(last[j] + 1, row[j - 1] + 1, last[j - 1] + (x != y)))
    return row[-1]


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "x" + hashlib.sha256(text.encode()).hexdigest()[:12]


def samples(wav: Path) -> np.ndarray:
    with wave.open(str(wav)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768


def render(phrase: str, voice: str, language: str, folder: Path, tts: dict) -> Path:
    """The phrase in this voice, as the app's 16 kHz mono WAV (made once; `say` and MMS-TTS are deterministic)."""
    wav = folder / f"{language}--{slug(voice)}--{slug(phrase)}.wav"
    if not wav.exists():
        if voice == "MMS-TTS":
            tts.setdefault("voice", Voice())
            source = write_wav(wav.with_suffix(".src.wav"), tts["voice"].speak(phrase, language),
                               tts["voice"].rate(language))
        else:
            source = wav.with_suffix(".aiff")
            subprocess.run(["say", "-v", voice, "-o", str(source), phrase], check=True)
        to_wav16k(source, wav)
        source.unlink()
    return wav


def padded(wav: Path) -> Path:
    """The clip with PAD_S of silence on each side, as a push-to-talk recording has (made once)."""
    out = wav.with_name(f"{wav.stem}--pad.wav")
    if not out.exists():
        silence = np.zeros(round(PAD_S * RATE))
        write_wav(out, np.concatenate([silence, samples(wav), silence]), RATE)
    return out


def latency(group: list[dict]) -> str:
    ms = sorted(1000 * r["seconds"] for r in group)
    return f"{statistics.median(ms):.0f} / {ms[min(len(ms) - 1, int(0.9 * len(ms)))]:.0f} / {ms[-1]:.0f} ms"


def summary(rows: list[dict]) -> str:
    out = ["## By language", "",
           "| Language | Audio | Listener | Clips | Words exact (ignoring accents) | Meaning kept | Safe miss | "
           "Wrong, cautious | **Clears a danger** | Latency p50 / p90 / max |", "|---|---|---|---|---|---|---|---|---|---|"]
    for language in LANGUAGES:
        for condition in CONDITIONS:
            for engine in ENGINES:
                group = [r for r in rows if (r["language"], r["condition"], r["engine"]) == (language, condition,
                                                                                              engine)]
                if not group:
                    continue
                count = {v: sum(r["verdict"] == v for r in group) for v in
                         ("same", "safe miss", "wrong, cautious", "clears a danger")}
                out.append(f"| {language} | {condition} | {engine} | {len(group)} | {sum(r['exact'] for r in group)} "
                           f"| {count['same']} | {count['safe miss']} | {count['wrong, cautious']} | "
                           f"**{count['clears a danger']}** | {latency(group)} |")
    out += ["", "## Every clip", "", "| Language | Audio | Voice | Said | MMS heard | MMS outcome | Voice Transcribe "
            "heard | Voice Transcribe outcome |", "|---|---|---|---|---|---|---|---|"]
    clips = {}
    for r in rows:
        clips.setdefault((r["language"], r["condition"], r["voice"], r["said"]), {})[r["engine"]] = r
    for (language, condition, voice, said), by in clips.items():
        cells = [f"{by[e]['heard']!r} | {by[e]['verdict']}" if e in by else "– | –" for e in ENGINES]
        out.append(f"| {language} | {condition} | {voice} | {said} | {cells[0]} | {cells[1]} |")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--engines", default="mms,muse", help="mms, muse or both")
    parser.add_argument("--languages", default="es,en,hi")
    parser.add_argument("--out", type=Path, default=Path("data/runs/listeners"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--smoke", action="store_true", help="one clip per listener: check the API answers")
    args = parser.parse_args()
    engines, languages = args.engines.split(","), args.languages.split(",")
    cache = ResponseCache(args.cache)
    listeners = {"mms": Listener(cache), "muse": MuseListener(cache, pad_s=0.0)}  # the clips carry any padding
    clips_dir = args.out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    installed = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    tts, jobs = {}, []
    for language in languages:
        voices, cases = LANGUAGES[language]
        for voice in voices:
            if voice != "MMS-TTS" and not re.search(rf"^{re.escape(voice)}\s", installed, re.M):
                raise SystemExit(f"macOS voice {voice!r} isn't installed")
        for phrase, rule in cases:
            for voice in voices:
                raw = render(phrase, voice, language, clips_dir, tts)
                jobs += [(language, voice, phrase, rule, "raw", raw), (language, voice, phrase, rule, "padded",
                                                                       padded(raw))]
    if args.smoke:
        jobs = jobs[:2]
    billed = 0
    for engine in engines:
        listener, warm, rows = listeners[engine], set(), []
        for language, voice, phrase, rule, condition, wav in jobs:
            if language not in warm:
                warm.add(language)
                if engine == "mms":  # the language's adapter loaded and run once, so that isn't counted as latency
                    listener._decode(wav, language)
                elif len(warm) == 1:  # the first request opens the connection; a model list (no audio) does that
                    listener._http().get("/models").raise_for_status()
            misses = cache.misses
            heard = listener.transcribe(wav, language)
            ran = cache.misses > misses
            if engine == "mms":  # timed again here, warm, since a cached time may be a cold start from another run
                started = time.perf_counter()
                listener._decode(wav, language)
                seconds = time.perf_counter() - started
            else:  # the time the request took when it ran
                seconds = cache.get(listener.request(wav, language))["elapsed_s"]
            if ran and engine == "muse":
                billed += int(len(samples(wav)) / RATE)
            row = {"language": language, "engine": engine, "condition": condition, "voice": voice, "said": phrase,
                   "rule": rule, "heard": heard, "seconds": seconds, "ran": ran, "clip": wav.name,
                   "audio_s": round(len(samples(wav)) / RATE, 2), "exact": folded(heard) == folded(phrase),
                   "word_errors": edits(words(phrase), words(heard)), "words_said": len(words(phrase))}
            outcome = handled(heard, rule, language)
            row["did"], row["verdict"] = describe(outcome), verdict(outcome, handled(phrase, rule, language))
            rows.append(row)
            print(f"{language} {engine:4} {condition:6} {voice[:24]:25} {phrase!r:20} heard {heard!r:28} "
                  f"{1000 * seconds:5.0f} ms  {row['verdict']}", flush=True)
        if not args.smoke:
            (args.out / f"results-{engine}.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    rows = [json.loads(line) for engine in ENGINES if (args.out / f"results-{engine}.jsonl").exists()
            for line in (args.out / f"results-{engine}.jsonl").read_text().splitlines()]
    report = summary(rows) + (f"\nVoice Transcribe audio sent this run: {billed} billable seconds (about "
                              f"${billed * PRICE_PER_SECOND:.4f}).\n")
    (args.out / "summary.md").write_text(report)
    print("\n" + report)


if __name__ == "__main__":
    main()
