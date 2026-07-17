from dataclasses import dataclass, field
from pathlib import Path
import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class TargetConfig:
    name: str
    type: str = "http"
    url: str = ""
    host: str = ""
    port: int = 0
    method: str = "GET"
    timeout: float = 5.0
    expected_status: int = 200
    verify_ssl: bool = True
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = False


@dataclass
class MonitorConfig:
    check_interval: int = 30
    db_path: str = "bridge_monitor.db"
    retention_days: int = 14
    flapping_threshold: int = 4
    flapping_window: int = 300
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    targets: list[TargetConfig] = field(default_factory=list)


def load_config(path: str | Path) -> MonitorConfig:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"config file not found at {cfg_path}")

    with open(cfg_path, "rb") as f:
        raw = tomllib.load(f)

    general = raw.get("monitor", {})
    tg_raw = raw.get("telegram", {})
    
    # token can come from env if we don't want it sitting on disk
    tg_token = tg_raw.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = str(tg_raw.get("chat_id", "")) or os.environ.get("TELEGRAM_CHAT_ID", "")
    
    telegram = TelegramConfig(
        bot_token=tg_token,
        chat_id=tg_chat,
        enabled=tg_raw.get("enabled", bool(tg_token and tg_chat)),
    )

    targets = []
    seen_names = set()
    for item in raw.get("targets", []):
        name = item.get("name")
        if not name:
            raise ValueError("every target requires a non-empty 'name'")
        if name in seen_names:
            raise ValueError(f"duplicate target name found: '{name}'")
        seen_names.add(name)
        
        t_type = item.get("type", "http").lower()
        if t_type == "http":
            if not item.get("url"):
                raise ValueError(f"http target '{name}' requires 'url'")
        elif t_type == "tcp":
            if not item.get("host") or not item.get("port"):
                raise ValueError(f"tcp target '{name}' requires 'host' and 'port'")
        else:
            raise ValueError(f"target '{name}' has unsupported type: {t_type}")

        targets.append(TargetConfig(
            name=name,
            type=t_type,
            url=item.get("url", ""),
            host=item.get("host", ""),
            port=int(item.get("port", 0)),
            method=item.get("method", "GET").upper(),
            timeout=float(item.get("timeout", 5.0)),
            expected_status=int(item.get("expected_status", 200)),
            verify_ssl=item.get("verify_ssl", True),
            headers=item.get("headers", {}),
        ))

    return MonitorConfig(
        check_interval=max(5, int(general.get("check_interval", 30))),
        db_path=general.get("db_path", "bridge_monitor.db"),
        retention_days=max(1, int(general.get("retention_days", 14))),
        flapping_threshold=max(2, int(general.get("flapping_threshold", 4))),
        flapping_window=max(30, int(general.get("flapping_window", 300))),
        telegram=telegram,
        targets=targets,
    )
