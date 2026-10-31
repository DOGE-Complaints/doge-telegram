# Data and delivery (logical)

**Parent:** [00-overview.md](./00-overview.md)  
**REQ:** [REQ-01](../../requirements/REQ-01-REQ15-TELEGRAM-CHANNEL-TRANSPORT.md) §2 (idempotency, buttons, delivery recovery)  
**As-of:** `2026-10-31T19:54:24Z`

**Hard rule:** do not invent concrete SQL columns or JSON field names beyond REQ + peer OpenAPI + operator answers. Below = **logical** contracts.

---

## 1. Idempotency (inbound)

| Item | Lock |
|------|------|
| Store | **SQLite (or equivalent file DB) on Volume** |
| Purpose | Remember processed Telegram event ids so retries do not double-apply turns/actions |
| Process-local memory only | Rejected for v1 prod (lost on restart) |
| «Bridge-only dedup» as sole AC-04 | Rejected without explicit waive — REQ places event-id idempotency on transport |

**Event key (logical):** Telegram `update_id` (and type discrimination if required by mapping). Exact persistence schema = create/implement wave.

**Defense in depth:** bridge channel idempotency may still apply (`doge-ai-bridge` tests exist) — second belt, not replacement for transport store.

---

## 2. Outbox (outbound delivery recovery)

| Item | Lock |
|------|------|
| Pattern | **Outbox in the same SQLite Volume** |
| Purpose | Persist «deliver to Telegram» work from bridge envelopes; retry after failure/restart |
| Inline-only send with no journal | Rejected for v1 (weak recovery) |
| Log-only on Send failure | Rejected (conflicts REQ delivery recovery) |

**Logical states (illustrative, not schema):** pending → sending → sent | failed (with clear error visible to ops). Exactly-once **Telegram** delivery is best-effort with safe retry; coordinate with idempotency of inbound and peer behavior — details at implement time from Bot API + OpenAPI.

---

## 3. Mapping to Present channel contract

| Direction | Contract |
|-----------|----------|
| Inbound message path | Map to `POST /v1/channel/turns` |
| Inbound callback path | Ack callback → `POST /v1/channel/actions` → outbox Send/Edit |
| Envelope fields | **Consume** `doge-ai-bridge/docs/openapi/aibridge-channel-v1.openapi.yaml` (+ runtime API docs) |

Additive channel HTTP SSOT only if Present proven insufficient and explicitly approved (REQ OOS / AC-TG-01-03).

---

## 4. Privacy / logging (light)

- User message text may be PII-bearing in transit; this service is a pipe.  
- Prefer structured ops errors without dumping full secrets.  
- Do not add model/gateway credentials «for convenience».
