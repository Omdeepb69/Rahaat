"""Unit tests for field app SQLite database manager and schema initialization."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from field_app.database import SCHEMA_VERSION, DatabaseManager


def test_schema_initialization_in_memory() -> None:
    db = DatabaseManager(":memory:")
    with db.connection() as conn:
        cursor = conn.execute("SELECT version FROM schema_version;")
        row = cursor.fetchone()
        assert row is not None
        assert row["version"] == SCHEMA_VERSION

        # Verify tables exist
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "schema_version" in tables
        assert "device_state" in tables
        assert "offline_reports" in tables


def test_database_manager_transaction_commit_and_rollback() -> None:
    db = DatabaseManager(":memory:")

    # Successful transaction
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO device_state (device_id, current_sequence, registered_at) VALUES (?, 0, ?);",
            ("dev-1", "2026-11-07T12:00:00Z"),
        )

    with db.connection() as conn:
        cursor = conn.execute("SELECT current_sequence FROM device_state WHERE device_id = 'dev-1';")
        assert cursor.fetchone()["current_sequence"] == 0

    # Failed transaction rolls back
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO device_state (device_id, current_sequence, registered_at) VALUES (?, 0, ?);",
                ("dev-2", "2026-11-07T12:00:00Z"),
            )
            raise RuntimeError("Forced abort")

    with db.connection() as conn:
        cursor = conn.execute("SELECT * FROM device_state WHERE device_id = 'dev-2';")
        assert cursor.fetchone() is None


def test_file_based_sqlite_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "field_test.db"

        # Initialize and write
        db1 = DatabaseManager(db_file)
        with db1.transaction() as conn:
            conn.execute(
                "INSERT INTO device_state (device_id, current_sequence, registered_at) VALUES (?, 42, ?);",
                ("persistent-device", "2026-11-07T12:00:00Z"),
            )
        db1.close()

        # Reopen file and verify persistence
        db2 = DatabaseManager(db_file)
        with db2.connection() as conn:
            cursor = conn.execute(
                "SELECT current_sequence FROM device_state WHERE device_id = 'persistent-device';"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row["current_sequence"] == 42
        db2.close()

