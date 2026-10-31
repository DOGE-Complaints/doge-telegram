# Production entry — doge-telegram-channel

**As-of:** STORY-TELEGRAM-01 scaffold  
**Arch:** [`telegram-channel/01-runtime-and-packaging.md`](../architecture/telegram-channel/01-runtime-and-packaging.md) §2

## Canonical entry (packaging SSOT)

| Form | Command |
|------|---------|
| Module | `python -m doge_telegram_channel` |
| Console script | `doge-telegram-channel` (after `pip install -e .`) |
| Code | `doge_telegram_channel.runtime:main` |

One process starts:

1. **Health HTTP** — `/healthz` (liveness), `/readyz` (fail-closed ready)  
2. **Poller placeholder** — idle loop until STORY-02 maps `getUpdates` → bridge

## Env

See committed [`example.env`](../../example.env). Required: `TELEGRAM_BOT_TOKEN`, `BRIDGE_BASE_URL`, `CHANNEL_BEARER`, `SQLITE_PATH`.

Optional: `HEALTH_HOST` (default `127.0.0.1`), `HEALTH_PORT` (default `8080`), `LOG_LEVEL`.

## Notes

- Railway **service name** is deferred (Unknown) — do not invent here.  
- Peer only: doge-ai-bridge `POST /v1/channel/turns` and `POST /v1/channel/actions` (wired in later stories).  
- No model API keys; no gateway submit client in this service (AC-TG-01-02).
