import pytest
import time
import sqlite3
from bridge_monitor.storage import Storage
from bridge_monitor.models import ProbeResult


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_monitor.db"
    storage = Storage(db_path=str(db_path))
    yield storage
    storage.close()


def test_schema_created(temp_db):
    with temp_db._get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='check_history'")
        assert cursor.fetchone() is not None


def test_insert_and_fetch_recent(temp_db):
    now = time.time()
    res1 = ProbeResult(target_name="auth-bridge", is_up=True, latency_ms=45.2, status_code=200, timestamp=now - 10)
    res2 = ProbeResult(target_name="auth-bridge", is_up=False, latency_ms=0.0, status_code=500, error="Internal error", timestamp=now)

    temp_db.save_result(res1)
    temp_db.save_result(res2)

    history = temp_db.get_recent("auth-bridge", limit=5)
    assert len(history) == 2
    # Latest record first
    assert history[0]["is_up"] == 0
    assert history[0]["error"] == "Internal error"
    assert history[1]["is_up"] == 1


def test_prune_old_records(temp_db):
    old_time = time.time() - (86400 * 10)  # 10 days ago
    recent_time = time.time()

    old_res = ProbeResult(target_name="api", is_up=True, latency_ms=12.0, status_code=200, timestamp=old_time)
    recent_res = ProbeResult(target_name="api", is_up=True, latency_ms=14.0, status_code=200, timestamp=recent_time)

    temp_db.save_result(old_res)
    temp_db.save_result(recent_res)

    deleted = temp_db.prune_older_than(days=7)
    assert deleted == 1

    remaining = temp_db.get_recent("api", limit=10)
    assert len(remaining) == 1
    assert remaining[0]["timestamp"] == recent_time
