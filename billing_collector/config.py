from __future__ import annotations

import os
from dataclasses import dataclass


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


DEFAULT_SCW_API_URL = "https://api.scaleway.com"
DEFAULT_DATABASE_PATH = "/data/billing-collector.sqlite3"
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_BIND_PORT = 9503
DEFAULT_PREVIOUS_PERIOD_BACKFILL_DAYS = 7
DEFAULT_COLLECTION_INTERVAL_SECONDS = 86_400
DEFAULT_HISTORY_EMPTY_STOP_MONTHS = 12


@dataclass(frozen=True, slots=True)
class Settings:
    scw_secret_key: str
    scw_organization_id: str
    scw_api_url: str = DEFAULT_SCW_API_URL
    database_path: str = DEFAULT_DATABASE_PATH
    bind_host: str = DEFAULT_BIND_HOST
    bind_port: int = DEFAULT_BIND_PORT
    project_ids: tuple[str, ...] = ()
    category_names: tuple[str, ...] = ()
    previous_period_backfill_days: int = DEFAULT_PREVIOUS_PERIOD_BACKFILL_DAYS
    collection_interval_seconds: int = DEFAULT_COLLECTION_INTERVAL_SECONDS
    collect_on_start: bool = True
    history_start_period: str | None = None
    history_end_period: str | None = None
    history_empty_stop_months: int = DEFAULT_HISTORY_EMPTY_STOP_MONTHS

    @classmethod
    def from_env(cls) -> "Settings":
        secret_key = os.getenv("SCW_SECRET_KEY")
        organization_id = os.getenv("SCW_ORGANIZATION_ID")
        missing = [
            name
            for name, value in {
                "SCW_SECRET_KEY": secret_key,
                "SCW_ORGANIZATION_ID": organization_id,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"missing required environment variables: {', '.join(missing)}")

        return cls(
            scw_secret_key=secret_key or "",
            scw_organization_id=organization_id or "",
            scw_api_url=os.getenv("SCW_API_URL", DEFAULT_SCW_API_URL),
            database_path=os.getenv("BILLING_COLLECTOR_DATABASE_PATH", DEFAULT_DATABASE_PATH),
            bind_host=os.getenv("BILLING_COLLECTOR_BIND_HOST", DEFAULT_BIND_HOST),
            bind_port=int(os.getenv("BILLING_COLLECTOR_BIND_PORT", str(DEFAULT_BIND_PORT))),
            project_ids=_split_csv(os.getenv("BILLING_COLLECTOR_PROJECT_IDS")),
            category_names=_split_csv(os.getenv("BILLING_COLLECTOR_CATEGORY_NAMES")),
            previous_period_backfill_days=int(
                os.getenv(
                    "BILLING_COLLECTOR_PREVIOUS_PERIOD_BACKFILL_DAYS",
                    str(DEFAULT_PREVIOUS_PERIOD_BACKFILL_DAYS),
                )
            ),
            collection_interval_seconds=int(
                os.getenv(
                    "BILLING_COLLECTOR_COLLECTION_INTERVAL_SECONDS",
                    str(DEFAULT_COLLECTION_INTERVAL_SECONDS),
                )
            ),
            collect_on_start=os.getenv("BILLING_COLLECTOR_COLLECT_ON_START", "true").lower()
            in {"1", "true", "yes", "on"},
            history_start_period=os.getenv("BILLING_COLLECTOR_HISTORY_START_PERIOD") or None,
            history_end_period=os.getenv("BILLING_COLLECTOR_HISTORY_END_PERIOD") or None,
            history_empty_stop_months=int(
                os.getenv(
                    "BILLING_COLLECTOR_HISTORY_EMPTY_STOP_MONTHS",
                    str(DEFAULT_HISTORY_EMPTY_STOP_MONTHS),
                )
            ),
        )
