import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from bridge_monitor.config import load_config
from bridge_monitor.storage import Storage
from bridge_monitor.checker import run_daemon, probe_target

logger = logging.getLogger("bridge_monitor")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # mute noisy hpack / httpcore logs when probing every few seconds
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bridge-monitor",
        description="Lightweight HTTP bridge probe & sqlite latency tracker",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config file (default: config.toml)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Start daemon monitoring loop")

    check_cmd = sub.add_parser("check", help="Run one-off probe against all targets")
    check_cmd.add_argument(
        "-t", "--target", help="Filter by target name (optional)"
    )

    sub.add_parser("status", help="Show summary table from sqlite DB")

    return parser.parse_args(argv)


def _format_table(rows: list[dict]) -> str:
    if not rows:
        return "No recorded target runs found in DB."

    headers = ["Target", "Last Status", "Latency (ms)", "Last Checked", "Fail Count"]
    # calculate fixed widths
    col_w = [len(h) for h in headers]
    for r in rows:
        col_w[0] = max(col_w[0], len(r["name"]))
        col_w[1] = max(col_w[1], len(str(r.get("status") or "ERR")))
        col_w[2] = max(col_w[2], len(f"{r.get('latency_ms', 0):.1f}"))
        col_w[3] = max(col_w[3], len(r.get("last_seen") or "never"))
        col_w[4] = max(col_w[4], len(str(r.get("fail_count", 0))))

    def row_fmt(items: list[str]) -> str:
        return "  ".join(s.ljust(w) for s, w in zip(items, col_w))

    lines = [
        row_fmt(headers),
        "  ".join("-" * w for w in col_w),
    ]
    for r in rows:
        st = str(r.get("status") or "ERR")
        lat = f"{r.get('latency_ms', 0.0):.1f}"
        lines.append(row_fmt([
            r["name"],
            st,
            lat,
            r.get("last_seen") or "never",
            str(r.get("fail_count", 0)),
        ]))
    return "\n".join(lines)


def _run_single_check(cfg, target_filter: str | None) -> int:
    targets = cfg.targets
    if target_filter:
        targets = [t for t in targets if t.name == target_filter]
        if not targets:
            sys.stderr.write(f"unknown target: '{target_filter}'\n")
            return 2

    storage = Storage(cfg.db_path)
    storage.init_db()

    failed = 0
    for target in targets:
        result = probe_target(target)
        storage.save_probe(result)
        # print(f"DEBUG: {result}")
        if not result.ok:
            failed += 1
            print(f"[FAIL] {target.name} -> {result.error or result.status_code} ({result.latency_ms:.1f}ms)")
        else:
            print(f"[ OK ] {target.name} -> {result.status_code} ({result.latency_ms:.1f}ms)")

    return 1 if failed > 0 else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if not args.config.exists():
        sys.stderr.write(f"error: config not found at {args.config}\n")
        return 1

    try:
        cfg = load_config(args.config)
    except Exception as e:
        sys.stderr.write(f"failed to parse config: {e}\n")
        return 1

    if args.command == "run":
        try:
            asyncio.run(run_daemon(cfg))
        except KeyboardInterrupt:
            logger.info("interrupted by user, shutting down")
            return 0
    elif args.command == "check":
        return _run_single_check(cfg, args.target)
    elif args.command == "status":
        storage = Storage(cfg.db_path)
        if not Path(cfg.db_path).exists():
            print(f"db file does not exist yet: {cfg.db_path}")
            return 0
        rows = storage.get_targets_summary()
        print(_format_table(rows))

    return 0
