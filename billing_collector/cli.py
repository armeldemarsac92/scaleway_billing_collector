from __future__ import annotations

import argparse

from billing_collector import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="billing-collector")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main() -> int:
    build_parser().parse_args()
    return 0

