"""The rating-plate reader on real generator labels: each field right, wrong or left unread, and the read-back.

    uv run --offline python scripts/eval_plates.py                  # Muse Glimmer on this laptop (Ollama)
    uv run --offline python scripts/eval_plates.py --think spark    # Muse Spark (MODEL_API_KEY)

The photos and their truth are in data/evals/plates (CPSC recall photos and eBay sellers' photos: copyrighted, so
they're used here only and never committed). truth.csv has each generator's values; SOURCES.md says where each came
from: printed on the label in the photo, or only in the manual. Only 4 of the 15 print their starting watts.

So a field counts two ways. Printed in the photo, it should be read right. Not in the photo, it should be left
unread: the prompt says not to guess, and a value "read" from nowhere is a guess, even when it happens to be right.
Each reading also goes through the app's checks (plate.check) and its read-back (phrases.read_back), which must say
only what was read.
"""

import argparse
import csv
import json
import re
from pathlib import Path

from aftermath.cache import ResponseCache
from aftermath.phrases import read_back
from aftermath.plate import read_plate

DATA = Path("data/evals/plates")
FIELDS = ("brand", "model", "running", "starting", "volts", "fuel")
# What each photo shows, from SOURCES.md: the fields printed on the label or unit in that photo.
PRINTED = {
    "01": {"brand", "model", "running", "volts", "fuel"}, "02": {"brand", "model", "running", "starting", "volts"},
    "03": {"brand", "model", "running", "volts"}, "04": {"brand", "model"},
    "05": {"model", "running", "volts"}, "06": {"model", "running", "volts"},
    "07": {"model", "running", "volts"}, "08": {"brand", "model", "running", "volts", "fuel"},
    "09": {"brand", "model", "running", "volts"}, "10": {"brand", "model", "running", "volts", "fuel"},
    "11": {"model", "running", "starting", "volts", "fuel"}, "12": {"brand", "model", "volts"},
    "13": {"brand", "model", "running", "volts"},
    "14": {"brand", "model", "running", "starting", "volts", "fuel"},
    "15": {"brand", "model", "running", "starting", "volts"},
}


def letters(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


def outcome(field: str, truth: dict, plate) -> str | None:
    """right, wrong or unread; None when the truth has no value for it."""
    expected = {"brand": truth["brand"], "model": truth["model"], "running": truth["running_w"],
                "starting": truth["starting_w"], "volts": truth["volts"], "fuel": truth["fuel"]}[field]
    read = {"brand": plate.brand, "model": plate.model, "running": plate.running_watts,
            "starting": plate.starting_watts, "volts": plate.volts, "fuel": plate.fuel}[field]
    if not expected:
        return None
    if read in (None, ""):
        return "unread"
    if field in ("running", "starting"):
        return "right" if abs(float(read) - float(expected)) <= 0.01 * float(expected) else "wrong"
    if field in ("brand", "model"):  # "Predator (Harbor Freight)", "G0081530 (GP6500EDF)": any one name will do
        names = [letters(n) for n in re.split(r"[()]", expected) if letters(n)]
        return "right" if any(n in letters(read) or letters(read) in n for n in names) else "wrong"
    if field == "volts":
        return "right" if read.replace(" ", "") == expected.replace(" ", "") else "wrong"
    return "right" if ("dual" in read) == (expected == "dual") and ("gas" in read or "dual" in read) else "wrong"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--think", choices=["glimmer", "spark"], default="glimmer")
    args = parser.parse_args()
    from aftermath.vlm import LocalGlimmer, MuseSpark

    cache = ResponseCache(Path("data/cache"))
    reader = MuseSpark(cache) if args.think == "spark" else LocalGlimmer(cache, max_tokens=600)
    rows, tally = [], {}
    for truth in csv.DictReader((DATA / "truth.csv").open()):
        key = truth["file"][:2]
        plate = read_plate(reader, DATA / truth["file"])
        text = read_back(plate, "en")
        result = {"file": truth["file"], "visible": plate.visible, "problems": plate.problems, "read_back": text,
                  "read": {"brand": plate.brand, "model": plate.model, "running": plate.running_watts,
                           "starting": plate.starting_watts, "volts": plate.volts, "fuel": plate.fuel}}
        for field in FIELDS:
            got = outcome(field, truth, plate)
            if got is None:
                continue
            kind = "printed" if field in PRINTED[key] else "not in the photo"
            result[field] = f"{got} ({kind})"
            tally.setdefault((field, kind), {}).setdefault(got, 0)
            tally[(field, kind)][got] += 1
        result["read_back_says_none"] = "None" in text or "unknown" in text.lower()
        rows.append(result)
        print(f"{truth['file']:34} " + " ".join(f"{f}={result.get(f, '-').split(' ')[0]}" for f in FIELDS)
              + f"  problems={plate.problems or '-'}", flush=True)
    out = DATA / f"results-{args.think}.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"\n{args.think}, {len(rows)} photos:")
    for field in FIELDS:
        for kind in ("printed", "not in the photo"):
            counts = tally.get((field, kind))
            if counts:
                total = sum(counts.values())
                print(f"  {field:8} {kind:17} {total:2}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"  read-backs that say None or unknown: {sum(r['read_back_says_none'] for r in rows)}; "
          f"photos read as no plate: {sum(not r['visible'] for r in rows)}")


if __name__ == "__main__":
    main()
