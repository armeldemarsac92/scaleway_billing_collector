from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectionSettings:
    organization_id: str
    project_ids: tuple[str, ...] = ()
    category_names: tuple[str, ...] = ()
    previous_period_backfill_days: int = 7
    source: str = "scaleway"


@dataclass(frozen=True, slots=True)
class ConsumptionCollectionSummary:
    snapshots_saved: int = 0
    deltas_saved: int = 0


@dataclass(frozen=True, slots=True)
class TaxCollectionSummary:
    snapshots_saved: int = 0
    deltas_saved: int = 0


@dataclass(frozen=True, slots=True)
class CollectionResult:
    projects_seen: int = 0
    snapshots_saved: int = 0
    deltas_saved: int = 0
    tax_snapshots_saved: int = 0
    tax_deltas_saved: int = 0


@dataclass(frozen=True, slots=True)
class HistorySeedSettings:
    organization_id: str
    project_ids: tuple[str, ...] = ()
    category_names: tuple[str, ...] = ()
    start_period: str | None = None
    end_period: str | None = None
    empty_stop_months: int = 12
    source: str = "scaleway-rest-history"
    force: bool = False


@dataclass(frozen=True, slots=True)
class HistorySeedResult:
    skipped: bool = False
    projects_seen: int = 0
    periods_checked: int = 0
    periods_seeded: int = 0
    snapshots_saved: int = 0
    deltas_saved: int = 0
    tax_snapshots_saved: int = 0
    tax_deltas_saved: int = 0
    first_seeded_period: str | None = None
    last_seeded_period: str | None = None
