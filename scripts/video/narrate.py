"""The v2 narration: script v17b's lines voiced by macOS `say` in the system's own voice (the Siri voice set in System
Settings > Accessibility > Spoken Content), polished the way the podcast studio polishes its own lines
(audio/voices.ts there): 48 kHz, a little warmth at 220 Hz, gentle compression, ends trimmed and faded, a line said
faster than 195 words a minute slowed to 195 (by at most 12%) and then sped up 6% (chapter 04's lines are left at the
voice's own speed), and each line at -20 dBFS active RMS with its peaks under -1.5 dBFS. Each line is voiced in one
breath, in a single `say` call, so the voice's own phrasing carries it from one sentence to the next (voiced sentence by
sentence, its intonation started over at every one, and sounded jerky). Where the film plays another voice inside a
line (c1a's «Sí»), the line leaves a silence for it. Then Whisper finds when each word is said, so the edit can key a
reveal to its word without cutting the line.

    uv run python scripts/video/narrate.py      # data/video/v2/vo/<line>.wav and lines.json

The user asked for the Mac's own voice for the narration, and then for its Siri voice over Samantha, which sounded
robotic to them (Nov 4). The narrator speaks of the builder in the third person, and doesn't name them. The app's voices
stay MMS-TTS.
"""

import difflib
import hashlib
import json
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "video" / "v2" / "vo"
CACHE = OUT / "cache"  # each line's polished take, by what was said; and the word times of each final line
SR = 48000
VOICE = None  # the system voice; a name here (say -v) picks another
WHISPER = "mlx-community/whisper-large-v3-turbo-asr-fp16"  # finds the words' times (mlx-audio, on this machine)
TARGET_RMS_DB, PEAK_DB = -20.0, -1.5
FASTEST = 195  # words a minute: a line said faster than this is slowed to it, by at most 12%
SPEED = 1.06  # then a line a touch quicker, so the film fits in 3:00 (at most 1.06)
CALM = {"s04-language"}  # chapter 04's lines keep the voice's own speed (atempo 1.0), so it never sounds rushed
SLOT = 1.25  # seconds of silence c1a leaves for the stand-in's «Sí»

# Script v18b (Nov 4), trimmed to fit 3:00 (h4's and c1a's second sentences cut, w1 shorter): the demo in Spanish
# (the user's call: it speaks to more of its audience), judged against the
# hackathon's rubric, for how it reads aloud and fact-checked against the README, by scene. What `say` reads differs
# only where it would misread the text; {pause} is where the stand-in's lone «Sí» plays.
SCENES = {
    "s01-hook": [
        ("h1", "That's how most generator deaths happen. Someone runs the generator in the garage with the door open, "
               "because it feels like there's plenty of air."),
        ("h2", "The person you just heard is in that spot, and the app told them in Spanish it can't stay there. The "
               "harder part is where it goes instead."),
        ("h3", "Their phone measures about ten feet from the door, which is far too close."),
        ("h4", "Thirty feet looks like plenty, but the app still calls it borderline."),
    ],
    "s02-why": [
        ("w1", "The CPSC counted at least thirteen hundred generator carbon monoxide deaths in the US from 2004 to "
               "2021, mostly indoors or in a garage."),
        ("w2", "The CDC says to keep it more than twenty feet from any door or window, which is hard to judge in the "
               "dark, and the warning doesn't always come in your own language. Spanish is the most spoken language in "
               "American homes after English, so the app speaks it, using the CDC's own Spanish."),
    ],
    "s03-how": [
        ("d1", "To measure, you stand where the generator is and take one photo of the nearest door."),
        ("d2", "Meta's SAM 3.1 finds the door, and since most doors are about six foot eight, its height in the photo "
               "and the phone's lens give the distance. Garage doors are taller, so the app asks."),
        ("m2", "The conversation runs on Meta's models too, on the laptop with no internet, or through Meta's API when "
               "there's a signal."),
    ],
    "s04-language": [
        ("c1", "That's the first problem, where to put it. The second is being understood. On short Spanish answers, "
               "the laptop's speech model got seventeen of thirty right, and Meta's API twenty-six."),
        ("c1a", "In one test, Meta's API heard nothing at all from a quick, lone sí, {pause} and sent back an empty "
                "transcript."),
        ("c1b", "If a misheard answer were ever taken as a yes, a warning could quietly disappear."),
        ("c1c", "So the app follows one rule. If it isn't sure what it heard, an answer can add a warning but never "
                "clear one, and it asks again."),
        ("c1d", "Across two hundred and forty test transcripts in three languages, not one made the app drop a "
                "warning."),
        ("c2", "If someone mentions a headache or feeling dizzy, the app tells them to get outside and call 911, "
               "before the language model even runs."),
        ("m3", "The model never gives the safety advice itself. That comes from a rulebook written straight from the "
               "CDC's guidance."),
    ],
    "s05-proof": [
        ("p1", "Against a tape measure and public laser scans of real doors, it came within about three percent."),
        ("p2", "Across thirty-one door views, it never called a door under twenty feet far enough."),
        ("p3", "It doesn't replace a carbon monoxide alarm. The code and its evaluations are open on GitHub."),
    ],
}
SAY_AS = [("SAM 3.1", "Sam three point one"), ("911", "nine one one"),
          ("2004 to 2021", "two thousand four to twenty twenty-one"), (" US ", " U.S. "),
          ("sí", "see"), ("{pause}", f"[[slnc {round(SLOT * 1000)}]]")]  # what MMS heard, spelled out


def builder() -> dict:
    """Who built it: kept out of the repository in data/video/v2/builder.json. The narration no longer names them (the
    user's call, Nov 4); without the file, the first name git commits under."""
    file = ROOT / "data" / "video" / "v2" / "builder.json"
    if file.exists():
        return json.loads(file.read_text())
    name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.split()[0]
    return {"name": name, "say": name, "card": f"{name} · built for the Meta hackathon"}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]


def spoken(text: str) -> str:
    for written, said in SAY_AS:
        text = text.replace(written, said)
    return text


def shown(line: str) -> str:
    """The line as written, without the marks for the voice."""
    return re.sub(r"\s*\{pause\}", "", line)


def synthesize(text: str, folder: Path) -> Path:
    """Two takes; if they differ (a neural voice needn't say a line the same way twice), a third, and the take whose
    length is the median, as the podcast studio picks a neural voice's takes."""
    voice = ["-v", VOICE] if VOICE else []
    takes = []
    for i in range(3):
        file = folder / f"take{i}.aiff"
        subprocess.run(["say", *voice, "-o", str(file), text], check=True)
        takes.append((file, hashlib.sha256(file.read_bytes()).hexdigest()))
        if i == 1 and takes[0][1] == takes[1][1]:
            return takes[0][0]
    lengths = sorted(takes, key=lambda t: t[0].stat().st_size)
    return lengths[1][0]


TRIM = "silenceremove=start_periods=1:start_threshold=-50dB:start_duration=0.01:detection=peak"
FADE = "asetpts=N/SR/TB,afade=t=in:d=0.06"
CHAIN = ",".join([f"aresample={SR}", "highpass=f=70", "lowpass=f=10500", "equalizer=f=220:t=q:w=1:g=1.5",
                  "acompressor=threshold=-24dB:ratio=2.5:attack=8:release=160:makeup=2",
                  TRIM, "areverse", TRIM, "areverse", "adelay=delays=45:all=1", "apad=pad_dur=0.04",
                  FADE, "areverse", FADE, "areverse"])


def polish(aiff: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(aiff), "-af", CHAIN, "-ac", "1", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def take(said: str, tmp: Path) -> np.ndarray:
    key = CACHE / (hashlib.sha256(f"{VOICE or 'system voice'}|{CHAIN}|{said}".encode()).hexdigest()[:16] + ".npy")
    if not key.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        np.save(key, polish(synthesize(said, tmp)))
    return np.load(key)


def level(x: np.ndarray) -> tuple[np.ndarray, float]:
    """At -20 dBFS active RMS (10 ms frames within 40 dB of the loudest), peaks held under -1.5 dBFS."""
    win = SR // 100
    n = len(x) // win
    power = (x[: n * win].reshape(n, win) ** 2).mean(axis=1)
    active = power[power > power.max() * 10 ** -4]
    gain = 10 ** (TARGET_RMS_DB / 20) / np.sqrt(active.mean())
    peak = np.abs(x).max() * gain
    if peak > 10 ** (PEAK_DB / 20):
        gain *= 10 ** (PEAK_DB / 20) / peak
    return (x * gain).astype(np.float32), 20 * np.log10(np.sqrt(active.mean()) * gain)


def retimed(x: np.ndarray, tempo: float) -> np.ndarray:
    """Faster (tempo above 1) or slower, at the same pitch."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                          "-af", f"atempo={tempo:.4f}", "-f", "f32le", "-"],
                         input=x.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def write(path: Path, x: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def plain(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def heard_words(path: Path, ears) -> list[tuple[str, float, float]]:
    """Whisper's words in a line's take, with their times; kept by the take's hash."""
    key = CACHE / f"words-{hashlib.sha256(path.read_bytes()).hexdigest()[:16]}.json"
    if not key.exists():
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "16k.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", str(wav)],
                           check=True)
            done = ears().generate(str(wav), language="en", word_timestamps=True)
        key.write_text(json.dumps([(w["word"].strip(), round(w["start"], 3), round(w["end"], 3))
                                   for s in done.segments for w in s.get("words", [])]))
    return [tuple(w) for w in json.loads(key.read_text())]


def word_times(text: str, heard: list[tuple[str, float, float]], seconds: float) -> list[list]:
    """Each written word's start and end: the words Whisper heard as written keep their times; a run of written words
    heard otherwise ("F H C C" as "FHCC", "911" as "nine one one") shares the time of what was heard in its place, by
    letters; a written word nothing was heard for sits in the gap between its neighbours."""
    written = text.split()
    a, b = [plain(w) for w in written], [plain(w) for w, _, _ in heard]
    times: list[list[float] | None] = [None] * len(written)

    def spread(i1: int, i2: int, start: float, end: float) -> None:
        letters = [max(1, len(w)) for w in written[i1:i2]]
        t = start
        for k, n in zip(range(i1, i2), letters):
            d = (end - start) * n / sum(letters)
            times[k] = [round(t, 3), round(t + d, 3)]
            t += d

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = [heard[j1 + k][1], heard[j1 + k][2]]
        elif op == "replace":
            spread(i1, i2, heard[j1][1], heard[j2 - 1][2])
    for k in range(len(written)):  # words nothing was heard for
        if times[k] is None:
            e = k
            while e < len(written) and times[e] is None:
                e += 1
            start = times[k - 1][1] if k else 0.0
            end = times[e][0] if e < len(written) else seconds
            spread(k, e, start, max(start, end))
    return [[w, *t] for w, t in zip(written, times)]


def main() -> None:
    from mlx_audio.stt.utils import load_model

    OUT.mkdir(parents=True, exist_ok=True)
    report, model = {}, []

    def ears():
        if not model:
            model.append(load_model(WHISPER))
        return model[0]

    for scene, lines in SCENES.items():
        for name, line in lines:
            text, said = shown(line), spoken(line)
            with tempfile.TemporaryDirectory() as tmp:
                audio = take(said, Path(tmp))
            words = len(text.split())
            rate = words / (len(audio) / SR - (SLOT if "{pause}" in line else 0)) * 60
            tempo = 1.0 if scene in CALM else (max(0.88, FASTEST / rate) if rate > FASTEST else 1.0) * SPEED
            if tempo != 1.0:
                audio = retimed(audio, tempo)
            audio, rms = level(audio)
            write(OUT / f"{name}.wav", audio)
            seconds = len(audio) / SR
            timed = word_times(text, heard_words(OUT / f"{name}.wav", ears), seconds)
            parts, k = sentences(text), 0
            starts, ends = [], []
            for sentence in parts:
                n = len(sentence.split())
                starts.append(timed[k][1])
                ends.append(timed[k + n - 1][2])
                k += n
            report[name] = {"scene": scene, "text": text, "said": said, "seconds": round(seconds, 3),
                            "sentences": parts, "starts": starts, "ends": ends, "words": timed,
                            "wpm": round(words / seconds * 60), "rms_db": round(float(rms), 1),
                            "tempo": round(tempo, 3)}
            print(f"{name}: {seconds:5.2f} s, {report[name]['wpm']} wpm, tempo {tempo:.3f}, {rms:.1f} dBFS", flush=True)
    (OUT / "lines.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"total {sum(r['seconds'] for r in report.values()):.1f} s of narration")


if __name__ == "__main__":
    main()
