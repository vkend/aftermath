"""Aftermath: a phone coach for the days after a hurricane cuts the power."""

import argparse
from importlib.metadata import version
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="aftermath", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('aftermath')}")
    commands = parser.add_subparsers(dest="command")
    door = commands.add_parser("door", help="how far the generator is from a door, from photos taken where it stands")
    door.add_argument("photos", type=Path, nargs="+")
    door.add_argument("--leaf-height-in", type=float, default=80.0, help="the door's height (default 80 in)")
    door.add_argument("--sensor-width-mm", type=float, help="only if the photo lacks a 35 mm-equivalent focal length")
    door.add_argument("--truth-ft", help="tape-measured distances, one per photo in order, e.g. 10,15,20,25,30")
    door.add_argument("--language", choices=["en", "hi", "es"], default="en")
    door.add_argument("--cache", type=Path, default=Path("data/cache"))
    door.add_argument("--out", type=Path, default=Path("data/runs/doors"), help="where to save checked outlines")
    args = parser.parse_args(argv)
    if args.command == "door":
        doors(args)
    else:
        parser.print_help()


def doors(args: argparse.Namespace) -> None:
    from . import segment
    from .cache import ResponseCache
    from .door import ERROR, LEAF_IN, measure, overlay
    from .phrases import door_note, say
    from .rules import Situation, assess

    truths = [float(t) for t in args.truth_ft.split(",")] if args.truth_ft else [None] * len(args.photos)
    if len(truths) != len(args.photos):
        raise SystemExit("give one --truth-ft distance per photo")
    sam, language, within = segment.LocalSam31(ResponseCache(args.cache)), args.language, []
    for photo, truth in zip(args.photos, truths):
        reading = measure(photo, sam, args.leaf_height_in, args.sensor_width_mm)
        overlay(photo, reading, args.out)
        if reading.refused:
            print(f"{reading.photo}: not measured. {door_note(reading.refused, language)}")
            continue
        v = reading.values
        result = assess(Situation(location="outdoors", measured_ft=reading.feet, lowest_ft=reading.lowest_ft,
                                  lens_assumed=bool(v.get("lens_assumed"))))
        line = (f"{reading.photo}: {reading.feet:.1f} ft, range {reading.lowest_ft:.1f}–{reading.highest_ft:.1f} ft: "
                f"{result.placement}. Door {v['door_px']:.0f} px tall (assumed {v['leaf_height_in']:g} in), focal "
                f"{v['focal_px']:.0f} px from {v['focal_source']}, {v['camera']}, SAM 3.1 {v['sam_score']:.2f}, "
                f"tilt {v['tilt_deg']:+.1f}°")
        if truth is not None:
            error = reading.feet / truth - 1
            within.append(abs(error) <= 0.10)
            line += f". Tape {truth:g} ft: {error:+.1%}"
        print(line)
        print(f"   {say(result.headline, language)}")
        for warning in reading.warnings:
            print(f"   ! {door_note(warning, language, tilt=v['tilt_deg'])}")
    if within:
        print(f"\n{sum(within)} of {len(within)} within ±10% of the tape: " + ("PASS" if all(within) else "FAIL"))
    print("\n" + door_note("error-limits", language, error=ERROR))
    if args.leaf_height_in == LEAF_IN:
        print(door_note("ask-door-height", language))
    print(f"Outlines: {args.out}/")
