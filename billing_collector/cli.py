from __future__ import annotations

import argparse
from dataclasses import asdict

from billing_collector import __version__
from billing_collector.app import Application
from billing_collector.config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="billing-collector")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("collect-once", help="Fetch Scaleway billing data and store daily deltas")
    seed = subparsers.add_parser(
        "seed-history",
        help="Backfill closed historical billing periods as month-level deltas",
    )
    seed.add_argument("--start-period", help="Oldest billing period to seed, formatted YYYY-MM")
    seed.add_argument("--end-period", help="Newest billing period to seed, formatted YYYY-MM")
    seed.add_argument(
        "--empty-stop-months",
        type=int,
        help="Stop auto-discovery after this many consecutive empty months",
    )
    seed.add_argument(
        "--force",
        action="store_true",
        help="Run even if the database is already marked as history-seeded",
    )
    subparsers.add_parser("serve", help="Serve /metrics, /healthz, and /readyz")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = Application.from_settings(Settings.from_env())
    if args.command == "collect-once":
        app.collect_once()
        return 0
    if args.command == "seed-history":
        result = app.seed_history(
            start_period=args.start_period,
            end_period=args.end_period,
            empty_stop_months=args.empty_stop_months,
            force=args.force,
        )
        for key, value in asdict(result).items():
            print(f"{key}={value}")
        return 0
    if args.command == "serve":
        app.serve()
        return 0
    return 0
