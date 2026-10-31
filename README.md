# doge-telegram-channel

Python service: **Telegram transport only** (messages, buttons, delivery, event idempotency).

| Item | Value |
|------|--------|
| Git | https://github.com/DOGE-Complaints/doge-telegram.git |
| Branch | `dev` |
| Builder profile | `telegram` (focus: `doge-telegram/`) |
| Stack | Python (scaffold deferred) |

## Boundary

Talks **only** to [doge-ai-bridge](../doge-ai-bridge/) channel façade:

- `POST /v1/channel/turns`
- `POST /v1/channel/actions`

(Channel Bearer auth; envelopes per bridge runtime docs.)

Replaces n8n for Telegram. Changing this channel adapter must **not** break interview methodology inside the bridge.

**This service does not:** hold model keys, run interview/roles/providers, or call gateway directly.

## Out of scope (v1)

- Sense brief / poster worker
- Admin UI for agents
- WhatsApp and other channels
- Interview / FSM / provider logic (owned by doge-ai-bridge)

## Builder Queue

From DOGEstonia workspace root:

```bash
python3 docs/methodology/Zeya888-builder-queue/cli/builder_resolve_queue.py --project telegram --verify
```

Runtime plan: `.cursor/plans/Telegram_builder.plan.md`  
Contract: `docs/methodology/Zeya888-builder-queue/contracts/telegram-operator-contract.md`

## App code

Product FastAPI/bot implementation is **not** in this bootstrap. Next: author `STORY-TELEGRAM-*` → P1.3.
