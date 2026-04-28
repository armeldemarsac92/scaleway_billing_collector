from __future__ import annotations

import argparse

from billing_collector import __version__
from billing_collector.app import Application
from billing_collector.config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="billing-collector")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("collect-once", help="Fetch Scaleway billing data and store daily deltas")
    subparsers.add_parser("serve", help="Serve /metrics, /healthz, and /readyz")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = Application.from_settings(Settings.from_env())
    if args.command == "collect-once":
        app.collect_once()
        return 0
    if args.command == "serve":
        app.serve()
        return 0
    return 0
