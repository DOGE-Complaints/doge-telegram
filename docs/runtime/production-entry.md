# Production entry — doge-telegram-channel

**As-of:** STORY-TELEGRAM-04 idempotency + stub harness  
**Arch:** [`telegram-channel/01-runtime-and-packaging.md`](../architecture/telegram-channel/01-runtime-and-packaging.md) §2 · §4

## Canonical entry (packaging SSOT)

| Form | Command |
|------|---------|
| Module | `python -m doge_telegram_channel` |
| Console script | `doge-telegram-channel` (after `pip install -e .`) |
| Code | `doge_telegram_channel.runtime:main` |

One process starts:

1. **Health HTTP** — `/healthz` (liveness), `/readyz` (fail-closed ready)  
2. **Long-poll loop** — messages → turns; callbacks → actions + SQLite outbox; **seen-event** dedup on Volume before side effects.

## Stub harness (same classes — not a second packaging binary)

| Form | Command |
|------|---------|
| Module | `python -m doge_telegram_channel.harness` |
| Proof | Synthetic duplicate `update_id` → single stub turns call (AC-TG-01-04) |
| Stub peer | `BRIDGE_STUB=1` → in-process peer (AC-TG-01-05; no live model provider) |
| Optional | `--with-production-entry` briefly runs `runtime.main` with stub |

**Defense in depth:** doge-ai-bridge channel idempotency tests are a **second belt**, not a substitute for transport `seen_events` (AC-TG-01-04). Peer path: `doge-ai-bridge/tests/integration/test_idempotency_concurrency.py`.

## Env

See committed [`example.env`](../../example.env). Required: `TELEGRAM_BOT_TOKEN`, `BRIDGE_BASE_URL`, `CHANNEL_BEARER`, `SQLITE_PATH`.

Optional: `HEALTH_HOST`, `HEALTH_PORT`, `LOG_LEVEL`, `BRIDGE_STUB=1`.

## Notes

- Railway **service name** is deferred (Unknown) — do not invent here.  
- Peer only: doge-ai-bridge `POST /v1/channel/turns` and `POST /v1/channel/actions`.  
- No model API keys; no gateway submit client in this service (AC-TG-01-02).
