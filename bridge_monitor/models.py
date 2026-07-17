from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Target:
    name: str
    url: str
    method: str = "GET"
    interval_sec: int = 30
    timeout_sec: float = 5.0
    expected_status: int = 200
    expected_body: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    retries: int = 2
    tags: list[str] = field(default_factory=list)

    # FIXME: old bridges occasionally need explicit HTTP/1.0 or keep-alive disabled
    insecure_tls: bool = False


@dataclass
class ProbeResult:
    """Single HTTP check outcome recorded into sqlite."""
    target_name: str
    status_code: Optional[int]
    latency_ms: float
    ok: bool
    response_bytes: int = 0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass
class AlertEvent:
    target_name: str
    state: str  # 'down', 'up', 'flapping'
    message: str
    timestamp: datetime = field(default_factory=_utc_now)
    consecutive_failures: int = 1
    resolved: bool = False
