"""Word and character error rates of the app's speech recognition on real voices: read speech from Google FLEURS.

FLEURS (Conneau et al. 2022, CC BY 4.0) is sentences from Wikipedia-like text read aloud by native speakers, several
speakers for each sentence. This takes the test split in Hindi (hi_in) and English (en_us) at a pinned revision of
google/fleurs on Hugging Face, walks it in the dataset's order (rows by file name, as its parquet files and
test.tar.gz hold them) and keeps each sentence's first recording until it has 50 sentences. It downloads test.tsv,
and test.tar.gz only as far as the last clip it keeps (the dataset viewer's rows API can't serve FLEURS: each parquet
file is one row group, past the viewer's scan limit). Each clip becomes the app's 16 kHz mono WAV (speech.to_wav16k)
and is heard by the app's listener: MMS-1B-all on this machine (speech.Listener) or, with --listener muse, Muse Voice
Transcribe through the Meta Model API as the app sends it (speech.MuseListener: the language as a hint, half a second
of silence on each side; it needs a key in MODEL_API_KEY).

Both the reference (FLEURS' normalised "transcription") and what was heard are normalised the same way: Unicode NFC,
lower case, zero-width characters dropped, apostrophes dropped ("don't" is "dont"), other punctuation and symbols (the
danda । and ॥, hyphens, quotes, $, %) as spaces, whitespace collapsed. WER is word edits (substitutions, insertions
and deletions) over reference words, and CER character edits over reference characters (code points, spaces not
counted), each summed over a language's clips. Hindi is also scored after the app's own folding (conversation.normal:
chandrabindu as anusvara, no nukta), as the conversation compares words. FLEURS writes numbers as digits ("70
किलोमीटर") where speakers say words, and MMS can write either (its Hindi and English vocabularies have digits), so
every score is given on all clips and on those whose reference has no numerals.

    uv run --offline python scripts/eval_fleurs.py
    uv run --offline python scripts/eval_fleurs.py --listener muse      # Voice Transcribe, on the same WAVs

Downloads go to data/eval/fleurs/<config>/ (git-ignored) with a manifest of the revision, the rule and the clips kept,
so a re-run reuses them. Results go to data/eval/fleurs/results.json (results-muse.json for Voice Transcribe).
Transcripts are cached in data/cache/ like the app's: a re-run replays them with the time measured when they ran, and
"fresh" marks those run this time. The real-time factor is transcription time over audio length, on this machine.
These are long sentences read on decent microphones, and FLEURS' train split is among the data MMS-1B-all was
fine-tuned on: a best case next to short answers said into a phone outdoors.
"""

import argparse
import io
import json
import platform
import re
import statistics
import subprocess
import tarfile
import time
import unicodedata
import wave
from pathlib import Path

import httpx
import numpy as np

from aftermath.cache import ResponseCache, file_digest
from aftermath.conversation import normal
from aftermath.speech import Listener, MuseListener, to_wav16k

DATASET, REVISION = "google/fleurs", "70bb2e84b976b7e960aa89f1c648e09c59f894dd"  # main since May 15, 2026
FILES = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/data"
CONFIGS = {"hi": "hi_in", "en": "en_us"}
RULE = ("test split in the dataset's order (rows by file name, as its parquet files and test.tar.gz hold them), each "
        "sentence's first recording, until {count} sentences")
RATE = 16000
FULL_SCALE = 32767 / 32768
LARGEST_CLIP = 64 << 20  # bytes; FLEURS clips are under 2 MB
PRICE_PER_SECOND = 0.18 / 3600  # Voice Transcribe


class Download(io.RawIOBase):
    """An HTTP response body as a file, so that tarfile reads an archive as it arrives and can stop early."""

    def __init__(self, response: httpx.Response) -> None:
        self.chunks, self.rest = response.iter_bytes(1 << 16), b""

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if not self.rest:
            self.rest = next(self.chunks, b"")
        n = min(len(buffer), len(self.rest))
        buffer[:n], self.rest = self.rest[:n], self.rest[n:]
        return n


def rows_of(tsv: bytes) -> list[dict]:
    """test.tsv's rows in the dataset's order. Its columns: sentence id, file name, raw transcription,
    transcription (normalised by FLEURS), the transcription's characters, number of samples, speaker's gender."""
    rows = []
    for line in tsv.decode("utf-8").splitlines():
        sentence, file, raw, transcription, _, samples, gender = line.split("\t")
        if not re.fullmatch(r"[0-9]+\.wav", file):
            raise ValueError(f"unexpected file name in test.tsv: {file!r}")
        rows.append({"id": file.removesuffix(".wav"), "sentence": int(sentence), "file": file, "gender": gender.lower(),
                     "samples": int(samples), "reference": transcription, "raw": raw})
    return sorted(rows, key=lambda row: row["file"])


def fetch(config: str, count: int, folder: Path) -> dict:
    """The clips kept from a config's test split, downloaded once and listed in ``folder``/manifest.json."""
    manifest = folder / "manifest.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if (saved["revision"], saved["count"]) == (REVISION, count) and all(
                (folder / "audio" / u["file"]).is_file() and file_digest(folder / "audio" / u["file"]) == u["sha256"]
                for u in saved["utterances"]):
            return saved
    (folder / "audio").mkdir(parents=True, exist_ok=True)
    tsv_url, archive_url = f"{FILES}/{config}/test.tsv", f"{FILES}/{config}/audio/test.tar.gz"
    response = httpx.get(tsv_url, follow_redirects=True, timeout=60)
    (folder / "test.tsv").write_bytes(response.raise_for_status().content)
    kept, skipped, sentences = [], [], set()
    for row in rows_of(response.content):
        if len(kept) == count:
            break
        if row["sentence"] in sentences:
            skipped.append(row["id"])  # another speaker's recording of a sentence already kept
        else:
            sentences.add(row["sentence"])
            kept.append(row)
    wanted = {row["file"]: row for row in kept}
    with httpx.stream("GET", archive_url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        with tarfile.open(fileobj=io.BufferedReader(Download(response)), mode="r|gz") as archive:
            for member in archive:  # nothing is extracted as the archive names it: kept clips' bytes, by TSV name
                name = member.name.rsplit("/", 1)[-1]
                if member.isfile() and name in wanted and "sha256" not in wanted[name]:
                    if member.size > LARGEST_CLIP:
                        raise ValueError(f"{config}: {name} is {member.size} bytes")
                    (folder / "audio" / name).write_bytes(archive.extractfile(member).read())
                    wanted[name]["sha256"] = file_digest(folder / "audio" / name)
                    if all("sha256" in row for row in kept):
                        break
    if missing := [row["file"] for row in kept if "sha256" not in row]:
        raise SystemExit(f"{config}: test.tar.gz lacks {missing}")
    saved = {"dataset": DATASET, "revision": REVISION, "config": config, "split": "test", "count": count,
             "rule": RULE.format(count=count), "tsv": {"url": tsv_url, "sha256": file_digest(folder / "test.tsv")},
             "archive": archive_url, "skipped": skipped, "utterances": kept}
    manifest.write_text(json.dumps(saved, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return saved


def wav16k(folder: Path, utterance: dict) -> Path:
    """The clip as the app's 16 kHz mono WAV, made once: every listener hears this file."""
    out = folder / "wav16k" / f"{utterance['id']}.wav"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        part = to_wav16k(folder / "audio" / utterance["file"], out.with_suffix(".part.wav"))
        part.replace(out)
    return out


def samples(wav: Path) -> np.ndarray:
    with wave.open(str(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, RATE), wav
        return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768


def words(text: str, fold: bool = False) -> list[str]:
    """The words compared (see the module's docstring); with ``fold``, after the app's own folding."""
    text = unicodedata.normalize("NFC", (normal(text) if fold else text).lower())
    kept = []
    for c in text:
        kind = unicodedata.category(c)
        if kind != "Cf" and c not in "'’":
            kept.append(" " if kind[0] in "PS" else c)
    return "".join(kept).split()


def edits(a, b) -> int:
    """Levenshtein distance between two sequences, of words or of characters."""
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row, last = [i], row
        for j, y in enumerate(b, 1):
            row.append(min(last[j] + 1, row[j - 1] + 1, last[j - 1] + (x != y)))
    return row[-1]


def scored(reference: str, heard: str, fold: bool = False) -> dict:
    said, got = words(reference, fold), words(heard, fold)
    return {"words": len(said), "word_errors": edits(said, got), "characters": len("".join(said)),
            "character_errors": edits("".join(said), "".join(got))}


def numerals(text: str) -> bool:
    return any(c.isnumeric() for c in text)  # digits in any script, and fractions such as ½


def totals(rows: list[dict], fold: bool = False) -> dict | None:
    """A group's WER and CER (edits over reference words and characters, summed over its clips), clip lengths and
    real-time factor."""
    if not rows:
        return None
    n = {k: sum((r["folded"] if fold else r)[k] for r in rows)
         for k in ("words", "word_errors", "characters", "character_errors")}
    audio, spent = sum(r["audio_s"] for r in rows), sum(r["transcription_s"] for r in rows)
    return {"utterances": len(rows), **n, "wer": round(n["word_errors"] / n["words"], 4),
            "cer": round(n["character_errors"] / n["characters"], 4), "audio_s": round(audio, 2),
            "median_audio_s": round(statistics.median(r["audio_s"] for r in rows), 2),
            "transcription_s": round(spent, 3),
            "median_transcription_s": round(statistics.median(r["transcription_s"] for r in rows), 3),
            "rtf": round(spent / audio, 4), "fresh": sum(r["fresh"] for r in rows)}


def summary(languages: dict, listener: str) -> str:
    out = [f"| Language ({listener}) | Clips | Words | WER | CER | Folded WER | Folded CER | Median clip | Median time "
           "| RTF |", "|---|---|---|---|---|---|---|---|---|---|"]
    for language, block in languages.items():
        for group, name in (("all", "all"), ("no_numerals", "no numerals")):
            t, f = block[group], (block.get("folded") or {}).get(group)
            if t is None:
                continue
            folded = f"{f['wer']:.1%} | {f['cer']:.1%}" if f else "– | –"
            out.append(f"| {language}, {name} | {t['utterances']} | {t['words']} | {t['wer']:.1%} | {t['cer']:.1%} | "
                       f"{folded} | {t['median_audio_s']:.1f} s | {t['median_transcription_s']:.2f} s | "
                       f"{t['rtf']:.3f} |")
    out.append("")
    for language, block in languages.items():
        notes = block["notes"]
        out.append(f"{language}: {block['all']['fresh']} of {block['all']['utterances']} transcribed this run; "
                   f"{notes['empty']} empty; {notes['numerals_heard']} heard with numerals; {notes['clipped']} with "
                   f"samples at full scale; {len(block['skipped'])} repeat recordings passed over.")
    return "\n".join(out) + "\n"


def machine() -> str:
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    return chip or platform.machine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--listener", choices=("mms", "muse"), default="mms")
    parser.add_argument("--languages", default="hi,en", help="any of " + ", ".join(CONFIGS))
    parser.add_argument("--count", type=int, default=50, help="sentences per language")
    parser.add_argument("--out", type=Path, default=Path("data/eval/fleurs"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    args = parser.parse_args()
    started = time.perf_counter()
    cache = ResponseCache(args.cache)
    listener = Listener(cache) if args.listener == "mms" else MuseListener(cache)
    rows, languages, warm = [], {}, set()
    for language in args.languages.split(","):
        config = CONFIGS[language]
        manifest = fetch(config, args.count, args.out / config)
        group = []
        for utterance in manifest["utterances"]:
            wav = wav16k(args.out / config, utterance)
            request = listener.request(wav, language)
            if language not in warm and cache.get(request) is None:  # what loads once isn't counted as its time
                if args.listener == "mms":
                    listener._decode(wav, language)  # the model and the language's adapter, run once
                elif not warm:
                    listener._http().get("/models").raise_for_status()  # opens the connection; sends no audio
                warm.add(language)
            misses = cache.misses
            heard = listener.transcribe(wav, language)
            audio = samples(wav)
            row = {"id": utterance["id"], "sentence": utterance["sentence"], "language": language,
                   "reference": utterance["reference"], "hypothesis": heard, **scored(utterance["reference"], heard),
                   "audio_s": round(len(audio) / RATE, 2),
                   "transcription_s": cache.get(request)["elapsed_s"],  # the listener's time when it ran
                   "fresh": cache.misses > misses, "numerals": numerals(utterance["reference"]),
                   "peak": round(float(np.abs(audio).max()), 4),
                   "clipped": round(float(np.mean(np.abs(audio) >= FULL_SCALE)), 5)}
            if language == "hi":
                row["folded"] = scored(utterance["reference"], heard, fold=True)
            group.append(row)
            print(f"{language} {row['id']:>20} {row['audio_s']:5.1f} s {row['transcription_s']:6.2f} s"
                  f"{' ' if row['fresh'] else '*'} {row['word_errors']:3}/{row['words']:<3} words wrong  "
                  f"heard {heard[:60]!r}", flush=True)
        plain = [r for r in group if not r["numerals"]]
        block = {"config": config, "listener": {k: v for k, v in request.items() if k != "audio"},
                 "skipped": manifest["skipped"], "all": totals(group), "no_numerals": totals(plain)}
        if language == "hi":
            block["folded"] = {"all": totals(group, True), "no_numerals": totals(plain, True)}
        block["notes"] = {"empty": sum(not r["hypothesis"].strip() for r in group),
                          "numerals_heard": sum(numerals(r["hypothesis"]) for r in group),
                          "clipped": sum(r["clipped"] > 0 for r in group)}
        languages[language], rows = block, rows + group
    report = summary(languages, args.listener)
    if args.listener == "muse":
        sent = sum(r["audio_s"] + 2 * listener.pad_s for r in rows if r["fresh"])
        report += f"Voice Transcribe heard {sent:.0f} s of audio this run (about ${sent * PRICE_PER_SECOND:.3f}).\n"
    elapsed = time.perf_counter() - started
    results = {"listener": args.listener, "machine": machine(), "run_s": round(elapsed, 1),
               "source": {"dataset": DATASET, "revision": REVISION, "split": "test", "license": "CC BY 4.0",
                          "rule": RULE.format(count=args.count), "files": FILES},
               "normalisation": __doc__.split("\n\n")[2].replace("\n", " "), "languages": languages, "utterances": rows}
    name = "results.json" if args.listener == "mms" else f"results-{args.listener}.json"
    (args.out / name).write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n" + report + f"\nWrote {args.out / name} in {elapsed:.0f} s (* replayed from the cache).")


if __name__ == "__main__":
    main()
