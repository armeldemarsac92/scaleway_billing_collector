from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_period TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT,
    category_name TEXT,
    source TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_scope
ON snapshots (
    billing_period,
    scope_type,
    organization_id,
    project_id,
    category_name,
    id
);

CREATE TABLE IF NOT EXISTS snapshot_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    billing_period TEXT NOT NULL,
    project_id TEXT NOT NULL,
    project_name TEXT,
    consumer_id TEXT NOT NULL,
    category_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    unit TEXT NOT NULL,
    currency TEXT NOT NULL,
    value_euros TEXT NOT NULL,
    billed_quantity TEXT,
    line_fingerprint TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshot_lines_snapshot
ON snapshot_lines (snapshot_id);

CREATE TABLE IF NOT EXISTS daily_deltas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_day TEXT NOT NULL,
    billing_period TEXT NOT NULL,
    project_id TEXT NOT NULL,
    project_name TEXT,
    consumer_id TEXT NOT NULL,
    category_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    unit TEXT NOT NULL,
    currency TEXT NOT NULL,
    delta_euros TEXT NOT NULL,
    delta_quantity TEXT,
    kind TEXT NOT NULL,
    line_fingerprint TEXT NOT NULL,
    current_snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    previous_snapshot_id INTEGER REFERENCES snapshots(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (billing_day, billing_period, line_fingerprint, kind)
);

CREATE INDEX IF NOT EXISTS idx_daily_deltas_counter
ON daily_deltas (
    kind,
    project_id,
    category_name,
    product_name,
    resource_name,
    sku,
    unit,
    currency
);

CREATE TABLE IF NOT EXISTS tax_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_period TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tax_snapshots_scope
ON tax_snapshots (billing_period, organization_id, id);

CREATE TABLE IF NOT EXISTS tax_snapshot_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_snapshot_id INTEGER NOT NULL REFERENCES tax_snapshots(id) ON DELETE CASCADE,
    billing_period TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    description TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate TEXT,
    total_tax_value TEXT NOT NULL,
    line_fingerprint TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tax_snapshot_lines_snapshot
ON tax_snapshot_lines (tax_snapshot_id);

CREATE TABLE IF NOT EXISTS tax_daily_deltas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_day TEXT NOT NULL,
    billing_period TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    description TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate TEXT,
    delta_euros TEXT NOT NULL,
    kind TEXT NOT NULL,
    line_fingerprint TEXT NOT NULL,
    current_tax_snapshot_id INTEGER NOT NULL REFERENCES tax_snapshots(id),
    previous_tax_snapshot_id INTEGER REFERENCES tax_snapshots(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (billing_day, billing_period, line_fingerprint, kind)
);

CREATE INDEX IF NOT EXISTS idx_tax_daily_deltas_counter
ON tax_daily_deltas (kind, organization_id, description, currency, rate);
"""
