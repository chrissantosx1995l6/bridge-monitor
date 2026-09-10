# bridge-monitor

I run this on a $4 Hetzner VPS to ping a bunch of webhook receivers, old internal tools, and payment callback endpoints. If anything starts returning 5xx or drops TCP connections, it pings my Telegram group.

All probe results get dumped into a local SQLite file so I can inspect latency spikes whenever clients complain about timeouts.

## Setup

```bash
git clone https://github.com/example/bridge-monitor.git
cd bridge-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy `config.example.toml` to `config.toml` and edit the endpoints:

```bash
cp config.example.toml config.toml
$EDITOR config.toml
```

## Running

```bash
# run one-off check to verify everything works
bridge-monitor --config config.toml --once

# run daemon loop
bridge-monitor --config config.toml
```

## Systemd unit

Put this in `/etc/systemd/system/bridge-monitor.service`:

```ini
[Unit]
Description=Bridge Monitor Daemon
After=network.target

[Service]
Type=simple
User=alex
WorkingDirectory=/opt/bridge-monitor
ExecStart=/opt/bridge-monitor/.venv/bin/bridge-monitor --config /etc/bridge-monitor/config.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Notes

- The SQLite DB creates an index on `(target_id, timestamp)`. If you leave it running for months, purge rows older than 30 days or set `retention_days = 30` in the config.
- Telegram alerts debounce flapping targets so your phone doesn't buzz every 30 seconds if a gateway is restarting.

<!-- checked: 2026-09-10 -->
