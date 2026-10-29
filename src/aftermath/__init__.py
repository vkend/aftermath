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
    serve = commands.add_parser("serve", help="the phone page, over HTTPS on this laptop's network")
    serve.add_argument("--host", default="0.0.0.0", help="0.0.0.0 lets phones on the same Wi-Fi reach it")
    serve.add_argument("--port", type=int, default=8443)
    serve.add_argument("--certs", type=Path, default=Path("data/certs"), help="made by scripts/make_certs.sh")
    serve.add_argument("--cache", type=Path, default=Path("data/cache"))
    serve.add_argument("--keep", type=Path, help="save every recording and photo sent, with a log, in this folder "
                                                 "(for testing with real voices; keep it under data/)")
    serve.add_argument("--listen", choices=["mms", "muse"], default="mms",
                       help="mms: speech recognition on this laptop (default); muse: Muse Voice Transcribe through "
                            "the Meta Model API, with the key in MODEL_API_KEY")
    serve.add_argument("--think", choices=["glimmer", "spark"], default="glimmer",
                       help="what reads each turn and the rating plate: glimmer, Muse Glimmer on this laptop "
                            "(default); spark, Muse Spark through the Meta Model API (the key in MODEL_API_KEY)")
    args = parser.parse_args(argv)
    if args.command == "door":
        doors(args)
    elif args.command == "serve":
        serving(args)
    else:
        parser.print_help()


def serving(args: argparse.Namespace) -> None:
    import subprocess
    from functools import partial

    import uvicorn

    from . import meta_api
    from .web import create_app, local_models

    cert, key = args.certs / "server.crt", args.certs / "server.key"
    if not (cert.exists() and key.exists()):
        raise SystemExit(f"no certificate in {args.certs}: run scripts/make_certs.sh first")
    if (args.listen == "muse" or args.think == "spark") and not meta_api.key():
        raise SystemExit("--listen muse and --think spark need a Meta Model API key in MODEL_API_KEY")
    address = subprocess.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True).stdout.strip()
    host = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True).stdout.strip()
    print(f"On a phone on the same Wi-Fi, open https://{address or 'this-laptop'}:{args.port}/ "
          f"or https://{host}.local:{args.port}/", flush=True)
    if args.keep:
        print(f"Keeping every recording and photo sent, and what the app heard, in {args.keep}/", flush=True)
    models = partial(local_models, args.cache, args.listen, args.think)  # loaded on the first request
    link = f"https://{address}:{args.port}" if address else None  # the check-in reminder's link: no name in it
    uvicorn.run(create_app(models, keep=args.keep, speech=args.cache / "speech", link=link), host=args.host,
                port=args.port, ssl_certfile=str(cert), ssl_keyfile=str(key), log_level="warning")


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
