# Runtime, packaging, verify, env

**Parent:** [00-overview.md](./00-overview.md)  
**REQ:** [REQ-01](../../requirements/REQ-01-REQ15-TELEGRAM-CHANNEL-TRANSPORT.md)  
**As-of:** `2026-10-31T19:54:24Z`

---

## 1. Runtime topology

| Item | Lock (interview) |
|------|------------------|
| Ingress | **Long-poll** (`getUpdates`) only for v1 |
| Webhook | Not v1 default; later only by explicit override (not dual-by-default) |
| Process model | **Single** process: poll loop + minimal health HTTP |
| Peer | Outbound HTTP to Present `/v1/channel/turns` and `/v1/channel/actions` only |

Health HTTP is an **ops probe**, not Telegram ingress. Do not conflate with webhook mode.

---

## 2. Packaging seam (Git ≠ image)

| Concern | Target |
|---------|--------|
| Git | Application source + docs under `doge-telegram/` |
| Image / platform start | Runs the **same** production entry class (poller+health) |
| Volume | SQLite file(s) for idempotency + outbox — **not** committed as source of truth |
| Module path | **Unknown** until create wave (name ≠ create) |

**Canonical production entry (class):** one entry that starts poller+health. Harness uses that entry with stub peer via environment — not a second permanent «test server» binary as the packaging SSOT.

---

## 3. Env / fail-closed / health

**Required env (locked / class):**

| Class | Key / note |
|-------|------------|
| Telegram bot / transport | **`TELEGRAM_BOT_TOKEN`** (locked) |
| Bridge base URL | class locked; exact key spelling may refine at implement (template: `BRIDGE_BASE_URL` in [`example.env`](../../../example.env)) |
| Channel Bearer (transport → bridge) | class locked; template `CHANNEL_BEARER` |
| SQLite / Volume path | class locked; template `SQLITE_PATH` |

**Local testing (operator workspace):** `doge-telegram/.env` holds a **real nonempty** `TELEGRAM_BOT_TOKEN` for Telegram Bot API tests (verified `2026-10-31T20:20:40Z` — key present / nonempty). **Never** copy the value into docs, tickets, or git. Committed template: [`example.env`](../../../example.env). Runtime secrets file: `.env` (gitignored).

**Fail-closed:** if a required class is missing → process must not claim ready; prefer exit or ready=false over half-running without peer/auth.

**Health:**

- Liveness: process up  
- Ready: required env present + SQLite open  
- Responses must not echo secrets  

**AC-TG-01-02:** no model API keys and no gateway submit in this service.

---

## 4. Verify surfaces

| Gate | What | Maps to |
|------|------|---------|
| Stub / harness | Same production entry; bridge stub (or scripted peer); synthetic updates as needed | AC-TG-01-04, AC-TG-01-05 |
| Unit vs prod entry | Prefer exercising the named production entry; avoid «green only on a different harness binary» as Done evidence | Packaging honesty |
| Live residual | Real Telegram Bot API ↔ real or staging bridge | Residual checklist; not silent REQ Done |
| AC-TG-01-01 | Target topology without n8n | Partial until live residual; greenfield (no live n8n today) |

**Profile test_command today:** `cd doge-telegram && python3 -V` — placeholder until create wave refines tooling ([profiles.yaml](../../../../docs/methodology/Zeya888-builder-queue/specs/profiles.yaml)).

---

## 5. Deploy residual

- Stub Pass ≠ Product Story Done ≠ live interview path proven.  
- Railway service **name** deferred (Unknown).  
- When create wave lands: bind entry, Volume, private networking to bridge, secrets — without inventing peer URLs beyond operator/platform facts.
