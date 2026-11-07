"""SQLite database connection and lifecycle manager."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union

from .schema import initialize_schema


class DatabaseManager:
    """Manages SQLite database connection, PRAGMA settings, and transactions."""

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # In-memory connections need to stay open to retain schema and data across calls
        self._shared_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._shared_conn = self._create_connection()
            initialize_schema(self._shared_conn)
        else:
            with self.connection() as conn:
                initialize_schema(conn)

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,
            check_same_thread=False,
            isolation_level=None,  # Explicit transaction management
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a configured SQLite connection."""
        if self._shared_conn is not None:
            yield self._shared_conn
        else:
            conn = self._create_connection()
            try:
                yield conn
            finally:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Execute a block within an atomic SQLite transaction (IMMEDIATE)."""
        with self._lock:
            with self.connection() as conn:
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    yield conn
                    conn.execute("COMMIT;")
                except Exception:
                    conn.execute("ROLLBACK;")
                    raise

    def close(self) -> None:
        """Close shared connection if open."""
        if self._shared_conn is not None:
            self._shared_conn.close()
            self._shared_conn = None

