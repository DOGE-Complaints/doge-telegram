# doge-telegram-channel

Python service: **Telegram transport only** (messages, buttons, delivery, event idempotency).

| Item | Value |
|------|--------|
| Git | https://github.com/DOGE-Complaints/doge-telegram.git |
| Branch | `dev` |
| Builder profile | `telegram` (focus: `doge-telegram/`) |
| Stack | Python 3.11+ |
| Package | `src/doge_telegram_channel/` |
| Production entry | `python -m doge_telegram_channel` → `doge_telegram_channel.runtime:main` |

## Boundary

Talks **only** to [doge-ai-bridge](../doge-ai-bridge/) channel façade:

- `POST /v1/channel/turns`
- `POST /v1/channel/actions`

(Channel Bearer auth; envelopes per bridge runtime docs. Mapping lands in STORY-02+.)

Replaces n8n for Telegram. Changing this channel adapter must **not** break interview methodology inside the bridge.

**This service does not:** hold model keys, run interview/roles/providers, or call gateway directly.

## Run (local)

```bash
cd doge-telegram
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp example.env .env   # fill TELEGRAM_BOT_TOKEN, BRIDGE_BASE_URL, CHANNEL_BEARER, SQLITE_PATH
python -m doge_telegram_channel --health-port 8080
```

Health: `GET /healthz` · Ready: `GET /readyz` (fail-closed). Details: [`docs/runtime/production-entry.md`](docs/runtime/production-entry.md).

## Tests

```bash
cd doge-telegram && python3 -m pytest -q
```

## Out of scope (v1)

- Sense brief / poster worker
- Admin UI for agents
- WhatsApp and other channels
- Interview / FSM / provider logic (owned by doge-ai-bridge)
- Exact Railway service name (deferred)

## Builder Queue

From DOGEstonia workspace root:

```bash
python3 docs/methodology/Zeya888-builder-queue/cli/builder_resolve_queue.py --project telegram --verify
```

Runtime plan: `.cursor/plans/Telegram_builder.plan.md`  
Contract: `docs/methodology/Zeya888-builder-queue/contracts/telegram-operator-contract.md`
