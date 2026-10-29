"""Aftermath: a phone coach for the days after a hurricane cuts the power."""

import argparse
from importlib.metadata import version


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="aftermath", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('aftermath')}")
    parser.parse_args(argv)
    parser.print_help()
