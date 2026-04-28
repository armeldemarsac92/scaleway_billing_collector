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
        )
