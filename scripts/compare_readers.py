"""Muse Spark against Muse Glimmer as the conversation's reader, on Hindi turns and a few English ones.

Both readers get the app's own prompt and schema for each turn (Conversation.prompt, conversation.SCHEMA): the
question the coach just asked, and what the person said. What they read is scored by what it would do:

- Unclear and unsure answers, the test suite's UNCLEAR_HI, to each question whose answer can take a danger off the
  list. A reader should read nothing that would. The conversation holds such readings back whatever the reader
  says (tests/test_conversation.py checks that with a reader that always reads the worst); here the conversation
  runs on each one again, with each real reader.
- Plain answers, the suite's CLEARING_HI, which the conversation reads without a model.
- Longer turns, which need the model, each with the facts it states.

"right": the facts stated, and no others; "extra": those, and others that take nothing off the list; "missed": a
stated fact left out (the coach asks again); "wrong": a stated fact read with another value that takes nothing off
the list; "clears a danger": a fact that takes a danger off the list and wasn't stated.

Latency is the reader's time for the turn, retries included. Answers are cached in data/cache/ like the app's, so a
re-run replays them with the time measured when they ran. Spark's tokens are priced at $1.25 a million in ($0.15
cached) and $4.25 out.

    uv run --offline python scripts/compare_readers.py --readers glimmer
    uv run --offline python scripts/compare_readers.py      # both: Spark needs a Meta Model API key in MODEL_API_KEY
    uv run --offline python scripts/compare_readers.py --readers spark-low       # Spark with more reasoning

Results go to data/runs/readers/ (git-ignored).
"""

import argparse
import json
import statistics
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))  # the test suite's own cases
from test_conversation import BEFORE, CLEARING, CLEARING_HI, UNCLEAR_HI  # noqa: E402

from aftermath.cache import ResponseCache  # noqa: E402
from aftermath.conversation import SAFE, SCHEMA, Conversation, clearing, facts_of, normal  # noqa: E402
from aftermath.vlm import LocalGlimmer, MuseSpark, ReadFailed  # noqa: E402

PRICE = {"input": 1.25e-6, "cached": 0.15e-6, "output": 4.25e-6}  # Muse Spark 1.3, dollars a token
READERS = {  # as the app runs them, and Spark with more reasoning
    "glimmer": lambda cache: LocalGlimmer(cache, max_tokens=600),
    "spark": lambda cache: MuseSpark(cache),
    "spark-low": lambda cache: MuseSpark(cache, efforts=("low", "medium")),
}


@dataclass
class Case:
    kind: str  # "unclear", "plain" or "longer"
    language: str
    rule: str  # the question the coach has just asked
    heard: str
    expect: dict = field(default_factory=dict)  # the facts stated (a tuple: any of these values)
    optional: tuple[str, ...] = ()  # facts that may be read or left out
    question: bool = False  # they asked a question of their own


LONGER = [
    Case("longer", "hi", "measure-distance", "मेरा जनरेटर गैराज में चल रहा है, दरवाज़ा खुला है।",
         {"generator_location": "garage"}),
    Case("longer", "hi", "ask-moved-outside", "हाँ, मैंने उसे बाहर निकाल दिया है, घर से काफ़ी दूर।",
         {"generator_location": "outdoors"}),
    Case("longer", "hi", "measure-distance", "वो बरामदे में है, छत के नीचे।",
         {"generator_location": ("porch", "under_eaves")}),
    Case("longer", "hi", "measure-distance", "जनरेटर अभी garage में है।", {"generator_location": "garage"}),
    Case("longer", "hi", "measure-distance", "बाहर रखा है, लेकिन बारिश हो रही है।",
         {"generator_location": "outdoors", "raining": "yes"}),
    Case("longer", "hi", "ask-door-height", "दरवाज़ा साढ़े छह फीट ऊँचा है।", {"door_height_in": 78}),
    Case("longer", "hi", "ask-door-height", "सात फुट का है।", {"door_height_in": 84}),
    Case("longer", "hi", "ask-exhaust", "धुआँ खिड़की की तरफ़ जा रहा है।", {"exhaust_toward_house": "yes"}),
    Case("longer", "hi", "ask-exhaust", "धुआँ घर से दूर, सड़क की तरफ़ जा रहा है।", {"exhaust_toward_house": "no"}),
    Case("longer", "hi", "ask-co-alarm", "अलार्म तो है, पर उसकी बैटरी खत्म हो गई है।", {"co_alarm": "no"}),
    Case("longer", "hi", "ask-co-alarm", "हाँ, बैटरी वाला अलार्म है, अभी टेस्ट किया, बज रहा है।", {"co_alarm": "yes"}),
    Case("longer", "hi", "ask-co-alarm", "CO alarm नहीं है हमारे पास।", {"co_alarm": "no"}),
    Case("longer", "hi", "ask-heat-and-cooking", "हम खाना अंदर रसोई में अंगीठी पर बना रहे हैं।",
         {"burning_indoors": ["charcoal_grill"]}),
    Case("longer", "hi", "ask-heat-and-cooking", "ठंड की वजह से गैस का ओवन खोलकर रखा है।",
         {"burning_indoors": ["gas_oven"]}, optional=("extreme_cold",)),
    Case("longer", "hi", "ask-downed-lines", "हाँ, सड़क के उस पार एक तार गिरा पड़ा है।", {"downed_line": "yes"}),
    Case("longer", "hi", "ask-downed-lines", "नहीं, कोई तार नहीं गिरा।", {"downed_line": "no"}),
    Case("longer", "hi", "ask-downed-lines", "पता नहीं, अंधेरे में कुछ दिख नहीं रहा।"),
    Case("longer", "hi", "ask-co-alarm", "पेट्रोल का एक टैंक कितनी देर चलता है?", question=True),
    Case("longer", "hi", "ask-exhaust", "मुझे चक्कर आ रहे हैं और सिर में दर्द है।", {"symptoms": "yes"}),
    Case("longer", "hi", "ask-co-alarm", "फ्रिज में मेरी माँ की इंसुलिन रखी है।", {"medical_needs": "yes"}),
    Case("longer", "hi", "ask-exhaust", "मैंने जनरेटर को दीवार के सॉकेट में लगा दिया है।", {"backfeeding": "yes"}),
    Case("longer", "hi", "ask-co-alarm", "अभी जनरेटर में पेट्रोल डाल रहा हूँ।", {"refuelling": "yes"}),
    Case("longer", "en", "measure-distance", "It's running in the garage with the door open.",
         {"generator_location": "garage"}),
    Case("longer", "en", "ask-co-alarm", "We have one, but the battery's dead.", {"co_alarm": "no"}),
    Case("longer", "en", "ask-downed-lines", "I can't really tell, it's too dark out there."),
    Case("longer", "en", "ask-heat-and-cooking", "We've been cooking on the charcoal grill in the garage.",
         {"burning_indoors": ["charcoal_grill"]}),
    Case("longer", "en", "ask-door-height", "It's about seven feet tall.", {"door_height_in": 84}),
    Case("longer", "en", "ask-co-alarm", "How long will a tank of gas last?", question=True),
]
PLAIN = [Case("plain", "hi", rule, said, facts_of(CLEARING[rule][1]),
              optional=("door_height_in",) if rule == "ask-door-height" else ())  # «नॉर्मल है»: 80 in, or nothing
         for rule, said in sorted(CLEARING_HI.items())]
UNCLEAR = [Case("unclear", "hi", rule, said) for rule in sorted(CLEARING) for said in UNCLEAR_HI]
CASES = UNCLEAR + PLAIN + LONGER


class Recording(ResponseCache):
    """The app's cache, noting each record a call fetched and whether it was replayed."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fetched: list[tuple[dict, bool]] = []

    def fetch(self, request, compute):
        hits = self.hits
        record = super().fetch(request, compute)
        self.fetched.append((record, self.hits > hits))
        return record


class Counting:
    """A reader that counts its calls."""

    def __init__(self, reader) -> None:
        self.reader, self.calls = reader, 0

    def ask_json(self, prompt, schema, images=()):
        self.calls += 1
        return self.reader.ask_json(prompt, schema, images)


def asking(rule: str, language: str, reader) -> Conversation:
    """A conversation that has just asked ``rule``."""
    talk = Conversation(reader, language=language, situation=BEFORE[rule], door_checked=rule != "ask-door-height")
    talk.reply("")
    assert talk.asked == rule, (rule, talk.asked)
    return talk


def read(reader, cache: Recording, prompt: str) -> dict:
    cache.fetched.clear()
    start = time.perf_counter()
    try:
        reading, error = reader.ask_json(prompt, SCHEMA), None
    except ReadFailed as failed:
        reading, error = {}, str(failed)
    took = time.perf_counter() - start
    replayed = [record for record, hit in cache.fetched if hit]
    return {"reading": reading, "error": error, "replayed": bool(replayed),
            "seconds": round(took + sum(r["elapsed_s"] for r in replayed), 3),  # a replay: when it ran
            "usage": [record["result"].get("usage") for record, _ in cache.fetched]}


def same(value, wanted) -> bool:
    options = wanted if isinstance(wanted, tuple) else (wanted,)
    for option in options:
        if isinstance(option, list) and isinstance(value, list) and set(value) == set(option):
            return True
        if isinstance(option, (int, float)) and isinstance(value, (int, float)) and abs(value - option) <= 1:
            return True
        if value == option:
            return True
    return False


def verdict(case: Case, reading: dict) -> tuple[str, dict]:
    facts = facts_of(reading)
    situation = BEFORE[case.rule]
    unstated = {n: v for n, v in facts.items() if not (n in case.expect and same(v, case.expect[n]))}
    clears = {n: v for n, v in unstated.items() if clearing(situation, n, v)}
    missed = [n for n in case.expect if n not in facts and n not in case.optional]
    wrong = {n: facts[n] for n in case.expect if n in facts and not same(facts[n], case.expect[n])}
    extra = {n: v for n, v in unstated.items() if n not in case.expect and n not in case.optional}
    if case.question and not (reading.get("question") or "").strip():
        missed.append("question")
    found = {"clears": clears, "missed": missed, "wrong": wrong, "extra": extra}
    if clears:
        return "clears a danger", found
    if wrong:
        return "wrong", found
    if missed:
        return "missed", found
    return ("extra" if extra else "right"), found


def devanagari_share(text: str) -> float:
    letters = [c for c in text if unicodedata.category(c)[0] in "LM"]
    return sum("ऀ" <= c <= "ॿ" for c in letters) / len(letters) if letters else 0.0


def cost(usages: list[dict]) -> float:
    total = 0.0
    for usage in usages:
        if usage and "input_tokens" in usage:
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
            total += (PRICE["input"] * (usage["input_tokens"] - cached) + PRICE["cached"] * cached
                      + PRICE["output"] * usage["output_tokens"])
    return total


def run(name: str, reader, cache: Recording, out: Path) -> list[dict]:
    if isinstance(reader, LocalGlimmer):  # loaded into memory first, so no turn's time includes loading it
        reader.http.post("/api/generate", json={"model": reader.model, "keep_alive": "30m"}, timeout=600)
    rows = []
    with (out / f"results-{name}.jsonl").open("w", encoding="utf-8") as log:
        for n, case in enumerate(CASES, 1):
            talk = asking(case.rule, case.language, reader)
            row = {"reader": name, **asdict(case), **read(reader, cache, talk.prompt(case.heard))}
            row["verdict"], row["found"] = verdict(case, row["reading"])
            answer = (row["reading"].get("answer") or "").strip()
            row["answer_devanagari"] = round(devanagari_share(answer), 2) if answer else None
            row["answer_says_safe"] = bool(answer and SAFE.search(normal(answer)))
            if case.kind == "unclear":  # and what the conversation itself does with it
                counted = Counting(reader)
                talk = asking(case.rule, case.language, counted)
                talk.reply(case.heard)
                row["conversation_cleared"] = CLEARING[case.rule][2](talk)
                row["conversation_model_calls"] = counted.calls
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            print(f"{name} {n}/{len(CASES)} {case.kind} {case.rule} {case.heard!r}: {row['verdict']} "
                  f"({row['seconds']:.2f} s{', replayed' if row['replayed'] else ''})", flush=True)
    return rows


def spread(seconds: list[float]) -> str:
    if not seconds:
        return "–"
    s = sorted(seconds)
    return f"{statistics.median(s):.2f} / {s[min(len(s) - 1, int(0.9 * len(s)))]:.2f} / {s[-1]:.2f} s"


def summary(results: dict[str, list[dict]]) -> str:
    names = list(results)
    lines = ["# Muse Spark against Muse Glimmer as the conversation's reader", "",
             "Generated by scripts/compare_readers.py. Glimmer: muse-glimmer:30b-mlx in Ollama on this laptop, as "
             "the app runs it (efforts low, medium, then low without the grammar; 600 tokens). Spark: "
             "muse-spark-1.3 on the Meta Model API, store false, as the app runs it (efforts minimal, then low) and "
             "with more reasoning (spark-low: low, then medium).", "",
             "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]

    def row(label, values):
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    def counts(rows):
        tally = Counter(r["verdict"] for r in rows)
        order = ["right", "extra", "missed", "wrong", "clears a danger"]
        return ", ".join(f"{tally[k]} {k}" for k in order if tally[k]) or "–"

    for kind, language, label in (("unclear", "hi", "Unclear Hindi answers: 15, to each of 8 questions"),
                                  ("plain", "hi", "Plain Hindi answers"), ("longer", "hi", "Longer Hindi turns"),
                                  ("longer", "en", "Longer English turns")):
        group = {n: [r for r in results[n] if r["kind"] == kind and r["language"] == language] for n in names}
        row(f"{label} ({len(group[names[0]])})", [counts(group[n]) for n in names])
    unclear = {n: [r for r in results[n] if r["kind"] == "unclear"] for n in names}
    row("Unclear: the conversation took a danger off the list",
        [f"{sum(r['conversation_cleared'] for r in unclear[n])} of {len(unclear[n])}" for n in names])
    row("Unclear: turns the conversation sent to the model",
        [f"{sum(r['conversation_model_calls'] > 0 for r in unclear[n])} of {len(unclear[n])}" for n in names])
    row("Read the language right", [f"{sum(r['reading'].get('language') == r['language'] for r in results[n])} of "
                                    f"{len(results[n])}" for n in names])
    row("Failed reads (the coach asks again)", [str(sum(bool(r["error"]) for r in results[n])) for n in names])
    longer_hi = {n: [r["seconds"] for r in results[n] if r["kind"] == "longer" and r["language"] == "hi"]
                 for n in names}
    row("Time per longer Hindi turn, median / p90 / max", [spread(longer_hi[n]) for n in names])
    row("Time per turn, all, median / p90 / max", [spread([r["seconds"] for r in results[n]]) for n in names])
    usages = {n: [u for r in results[n] for u in r["usage"] if u and "input_tokens" in u] for n in names}
    if any(usages.values()):
        def tokens(group):
            if not group:
                return "–"
            reasoning = sum((u.get("output_tokens_details") or {}).get("reasoning_tokens", 0) for u in group)
            return (f"{sum(u['input_tokens'] for u in group):,} / {sum(u['output_tokens'] for u in group):,} "
                    f"({reasoning:,})")

        row("Spark tokens (in / out, of which reasoning)", [tokens(usages[n]) for n in names])
        row("Spark cost", [f"${cost(usages[n]):.3f} for {len(usages[n])} answers" if usages[n] else "–"
                           for n in names])

    lines += ["", "## Longer turns, reading by reading", "",
              "| Asked | Said | Should read | " + " | ".join(names) + " |", "|---|---|---|" + "---|" * len(names)]
    by_case = {n: {(r["rule"], r["heard"]): r for r in results[n] if r["kind"] in ("longer", "plain")} for n in names}
    for case in LONGER + PLAIN:
        cells = []
        for n in names:
            r = by_case[n].get((case.rule, case.heard))
            if r is None:  # that reader's run hasn't got this far
                cells.append("–")
                continue
            facts = facts_of(r["reading"])
            shown = ", ".join(f"{k}={v}" for k, v in facts.items()) or "nothing"
            if case.question:
                shown += f"; question: {r['reading'].get('question', '')!r}; answer: {r['reading'].get('answer', '')!r}"
            cells.append(f"{r['verdict']}: {shown} ({r['seconds']:.1f} s)")
        expected = ", ".join(f"{k}={v}" for k, v in case.expect.items()) or ("a question" if case.question
                                                                           else "nothing")
        lines.append(f"| {case.rule} | {case.heard} | {expected} | " + " | ".join(cells) + " |")

    lines += ["", "## Unclear answers a reader read as taking a danger off the list", ""]
    for n in names:
        bad = [r for r in unclear[n] if r["verdict"] == "clears a danger"]
        lines.append(f"- **{n}** ({len(bad)}): " + ("; ".join(
            f"{r['rule']} «{r['heard']}» → {', '.join(f'{k}={v}' for k, v in r['found']['clears'].items())}"
            for r in bad) or "none"))
    answers = [(n, r) for n in names for r in results[n] if r["question"]]
    if answers:
        lines += ["", "## Answers to the person's own question", ""]
        for n, r in answers:
            lines.append(f"- **{n}**, «{r['heard']}»: {r['reading'].get('answer', '')!r} (Devanagari share "
                         f"{r['answer_devanagari']}, says safe: {r['answer_says_safe']})")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--readers", nargs="*", choices=list(READERS), default=["glimmer", "spark"],
                        help="the readers to run (the others' last results are kept); none: only the summary")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache")
    parser.add_argument("--out", type=Path, default=ROOT / "data/runs/readers")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cache = Recording(args.cache)
    results = {}
    for name in READERS:
        path = args.out / f"results-{name}.jsonl"
        if name in args.readers:
            results[name] = run(name, READERS[name](cache), cache, args.out)
        elif path.exists():  # an earlier run, for the side-by-side
            results[name] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    (args.out / "summary.md").write_text(summary(results), encoding="utf-8")
    print(f"Wrote {args.out / 'summary.md'}")


if __name__ == "__main__":
    main()
