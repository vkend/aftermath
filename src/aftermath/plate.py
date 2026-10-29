"""The generator's rating plate, read by a vision model: fixed fields, sanity checks, and a read-back to confirm.

The plate tells what the generator can power at once and what fuel it takes. The carbon monoxide advice never
depends on it: a misread plate can change the load plan, never where the generator may run. So the model only fills
in fixed fields; the numbers are parsed and checked here (starting watts above running watts, sizes a portable
generator has, amps times volts close to the watts), and the reading is read back for the person to confirm.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

SCHEMA = {
    "type": "object",
    "properties": {
        "plate_visible": {"type": "boolean"},
        "brand": {"type": "string"},
        "model": {"type": "string"},
        "running_watts": {"type": "string"},
        "starting_watts": {"type": "string"},
        "volts": {"type": "string"},
        "hertz": {"type": "string"},
        "amps": {"type": "string"},
        "fuel": {"type": "string"},
        "co_shutoff": {"type": "string"},
    },
    "required": ["plate_visible", "brand", "model", "running_watts", "starting_watts", "volts", "hertz", "amps",
                 "fuel", "co_shutoff"],
}
PROMPT = ("This photo should show the rating plate or label of a portable generator. Copy what it says into the "
          "fields, exactly as printed; use an empty string for anything you can't read clearly, and don't guess. "
          "running_watts: the rated, continuous or running AC output in watts. starting_watts: the starting, surge, "
          "peak or maximum watts. volts: as printed, such as 120/240. hertz: the frequency. amps: the rated amps at "
          "the highest voltage. fuel: gasoline, propane, dual fuel or diesel, if printed. co_shutoff: \"yes\" if the "
          "label mentions a carbon monoxide shutoff or sensor (such as CO Shield, CO-MINDER or CO Guard), else \"\". "
          "Set plate_visible to false if no rating plate or label is readable.")


class Reader(Protocol):
    def ask_json(self, prompt: str, schema: dict, images: list[str | Path] = ()) -> dict: ...


def ac_volts(text: str) -> str:
    """The AC voltages as printed, numbers only, so a read-back adds its own word for volts: "120/240 V",
    "120V/240V" and "120/240 VAC, 12 VDC" are all "120/240"."""
    group = re.search(r"\d+(?:\.\d+)?(?:\s*v)?(?:\s*[/–-]\s*\d+(?:\.\d+)?(?:\s*v)?)*", text or "", re.I)
    return "/".join(re.findall(r"\d+(?:\.\d+)?", group.group())) if group else ""


def number(text: str) -> float | None:
    """The first number in a field ("3,500 W" → 3500); None when there's none."""
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text or "")
    return float(match.group().replace(",", "")) if match else None


@dataclass
class Plate:
    visible: bool
    brand: str = ""
    model: str = ""
    running_watts: float | None = None
    starting_watts: float | None = None
    volts: str = ""
    hertz: float | None = None
    amps: float | None = None
    fuel: str = ""
    co_shutoff: bool = False
    problems: list[str] = field(default_factory=list)  # keys in phrases.PLATE_NOTES

    @property
    def usable_watts(self) -> float | None:
        """Running watts the load plan may use: none when the reading failed its checks."""
        return None if {"swapped-watts", "watts-out-of-range"} & set(self.problems) else self.running_watts


def check(plate: Plate) -> Plate:
    """Flag readings a real portable generator's plate can't have."""
    run, start = plate.running_watts, plate.starting_watts
    if run is None:
        plate.problems.append("no-running-watts")
    elif not 400 <= run <= 20000:
        plate.problems.append("watts-out-of-range")
    if run is not None and start is not None and start < run:
        plate.problems.append("swapped-watts")
    if plate.hertz is not None and plate.hertz not in (50, 60):
        plate.problems.append("odd-hertz")
    # The AC voltage is the highest number printed ("120/240 VAC, 12 VDC" → 240).
    highest_volts = max((float(v) for v in re.findall(r"\d+(?:\.\d+)?", plate.volts)), default=None)
    if highest_volts is not None and not 100 <= highest_volts <= 250:
        plate.problems.append("odd-volts")
    if run and plate.amps and highest_volts and not 0.6 <= plate.amps * highest_volts / run <= 1.5:
        plate.problems.append("amps-dont-match")
    return plate


def read_plate(reader: Reader, photo: str | Path) -> Plate:
    """Read a rating plate photo into checked fields. When the model fails, or the Meta API can't be reached, the
    plate counts as unread, and the person is asked for another photo."""
    try:
        answer = reader.ask_json(PROMPT, SCHEMA, [photo])
    except RuntimeError as error:  # vlm.ReadFailed
        logging.getLogger("aftermath").warning("reading the plate failed: %s", error)
        answer = {}
    if not answer.get("plate_visible"):
        return Plate(visible=False, problems=["no-plate"])
    plate = Plate(visible=True, brand=answer.get("brand", "").strip(), model=answer.get("model", "").strip(),
                  running_watts=number(answer.get("running_watts", "")),
                  starting_watts=number(answer.get("starting_watts", "")), volts=ac_volts(answer.get("volts", "")),
                  hertz=number(answer.get("hertz", "")), amps=number(answer.get("amps", "")),
                  fuel=answer.get("fuel", "").strip().lower(),
                  co_shutoff=answer.get("co_shutoff", "").strip().lower() in ("yes", "true", "sí", "si"))
    return check(plate)
