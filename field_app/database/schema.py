"""SQLite schema definitions and migrations for offline field storage."""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS device_state (
    device_id TEXT PRIMARY KEY,
    current_sequence INTEGER NOT NULL DEFAULT 0,
    registered_at TEXT NOT NULL,
    device_name TEXT
);

CREATE TABLE IF NOT EXISTS offline_reports (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    disaster_id TEXT NOT NULL,
    source_identity TEXT,
    language_code TEXT,
    client_created_at TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    sync_status TEXT NOT NULL DEFAULT 'locally_saved',
    batch_id TEXT,
    synced_at TEXT,
    error_message TEXT,
    UNIQUE (device_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_offline_reports_sync_status
    ON offline_reports(sync_status, sequence ASC);

CREATE INDEX IF NOT EXISTS idx_offline_reports_device_seq
    ON offline_reports(device_id, sequence);

CREATE INDEX IF NOT EXISTS idx_offline_reports_idempotency
    ON offline_reports(idempotency_key);
"""


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Execute DDL statements to set up SQLite tables and indexes."""
    with conn:
        conn.executescript(CREATE_TABLES_SQL)
        cursor = conn.execute("SELECT version FROM schema_version LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?);",
                (SCHEMA_VERSION,),
            )

