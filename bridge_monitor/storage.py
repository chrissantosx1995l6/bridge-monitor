import sqlite3
import time
from pathlib import Path
from bridge_monitor.models import ProbeResult, StateTransition


class Storage:
    """Thread-safe SQLite helper for storing probe history and alert transitions."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # wal mode so readers won't block the probe loop writes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS probes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    status_code INTEGER,
                    latency_ms REAL NOT NULL,
                    error TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_probes_target_ts
                ON probes (target_name, timestamp);

                CREATE TABLE IF NOT EXISTS state_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_name TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    reason TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_state_changes_ts
                ON state_changes (timestamp);
            """)

    def record_probe(self, r: ProbeResult):
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO probes (target_name, success, status_code, latency_ms, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (r.target_name, int(r.success), r.status_code, r.latency_ms, r.error, r.timestamp),
            )

    def record_probes_bulk(self, results: list[ProbeResult]):
        if not results:
            return
        with self._get_conn() as conn:
            conn.executemany(
                """
                INSERT INTO probes (target_name, success, status_code, latency_ms, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (r.target_name, int(r.success), r.status_code, r.latency_ms, r.error, r.timestamp)
                    for r in results
                ],
            )

    def record_transition(self, tr: StateTransition):
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO state_changes (target_name, from_state, to_state, reason, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tr.target_name, tr.from_state, tr.to_state, tr.reason, tr.timestamp),
            )

    def get_recent_probes(self, target_name: str, limit: int = 50) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT target_name, success, status_code, latency_ms, error, timestamp
                FROM probes
                WHERE target_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (target_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def prune_old_metrics(self, retention_days: int) -> int:
        cutoff = time.time() - (retention_days * 86400)
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM probes WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
        return deleted
