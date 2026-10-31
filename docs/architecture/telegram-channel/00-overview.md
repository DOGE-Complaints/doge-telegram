# Target technical architecture — Telegram channel transport

**Package:** `doge-telegram/docs/architecture/telegram-channel/`  
**Focus:** `doge-telegram/` · product name **`doge-telegram-channel`** (≠ folder)  
**Builder profile:** `telegram`  
**Input REQ:** [REQ-01 — REQ15 Telegram channel transport](../../requirements/REQ-01-REQ15-TELEGRAM-CHANNEL-TRANSPORT.md)  
**Parent product:** [REQ15](<../../../../docs/requirements backlog/REQ15-DOGEstonia-Interview-DeepSeek-And-Telegram-Channel.md>) (O3 / L1–L3 framing)  
**Interview report:** [zeya888.target-tech-arch-interview-req-01-telegram-channel-transport-2026-10-31.md](../../analysis/zeya888.target-tech-arch-interview-req-01-telegram-channel-transport-2026-10-31.md)  
**As-of:** `2026-10-31T19:54:24Z` (story-scope refresh `2026-10-31T20:08:33Z`)  
**Status:** Target architecture (no app scaffold on disk yet — name ≠ create)  
**Story scope:** package [`req-01-telegram-channel-transport`](../../tasks/backlog-stories/req-01-telegram-channel-transport/INDEX.md) — 5× `STORY-TELEGRAM-01`…`05` (Todo)

**Siblings:** [01-runtime-and-packaging.md](./01-runtime-and-packaging.md) · [02-data-and-delivery.md](./02-data-and-delivery.md)  
**Backlog package:** [`docs/tasks/backlog-stories/req-01-telegram-channel-transport/INDEX.md`](../../tasks/backlog-stories/req-01-telegram-channel-transport/INDEX.md)

---

## 1. Context & inputs

| Layer | Role |
|-------|------|
| Functional / product | REQ-01 Goal, Scope/OOS, AC-TG-01-01…05 |
| Story scope | [`req-01-telegram-channel-transport`](../../tasks/backlog-stories/req-01-telegram-channel-transport/INDEX.md) — STORY-TELEGRAM-01…05 |
| Target tech (this package) | How the focus realizes transport in stack/infra |
| Work items | Backlog package above (this arch package does **not** author NEW STORY keys) |

**Functional vs tech split:** REQ stays product-facing (why/what/AC). This package locks **how**: one thin process, long-poll ingress, Present peer HTTP, SQLite Volume, packaging/verify/residual.

**Operator fact (interview):** live n8n on prod is **absent** — greenfield transport path; do not assume cutover callers.

**Classify:** Mixed functional+tech + deployability-gap (empty focus runtime).

---

## 2. Target technical architecture of the focus

```text
Human ↔ Telegram Bot API
         ↕  long-poll (getUpdates) only — v1
   doge-telegram-channel  (single process)
         │  map update → Present channel envelope
         │  POST /v1/channel/turns | /v1/channel/actions
         │  Channel Bearer (transport secret domain)
         ▼
   doge-ai-bridge  (owns AI, interview, gateway)
         │  outbound envelope (Send/Edit/buttons) — fields per OpenAPI
         ▼
   outbox (SQLite Volume) → Telegram Bot API delivery + recovery
   + minimal HTTP /healthz (liveness) / ready (fail-closed)
```

| Component (logical) | Responsibility |
|---------------------|----------------|
| Long-poll loop | Ingress only; **not** Telegram webhook server |
| Mapper | Telegram update → Present turns/actions body (consume peer OpenAPI; no invent fields here) |
| Bridge HTTP client | Outbound only to Present paths |
| Idempotency store | Seen Telegram event ids in SQLite on Volume |
| Outbox | Persist outbound delivery jobs; retry/recovery |
| Health HTTP | Platform probe; **not** bot ingress |

**Peer contract (as-is on bridge):**

| Path | Code |
|------|------|
| `POST /v1/channel/turns` | `doge-ai-bridge/src/aibridge/app.py:909` |
| `POST /v1/channel/actions` | `doge-ai-bridge/src/aibridge/app.py:939` |
| OpenAPI SSOT | `doge-ai-bridge/docs/openapi/aibridge-channel-v1.openapi.yaml` |

**Callback order (from peer docs, not invented):** for callbacks — acknowledge Telegram callback promptly, then `POST /v1/channel/actions`, then apply Send/Edit from envelope (see aibridge channel façade / n8n workflow docs). Exact ack API details = implement against Bot API + peer docs.

**Trust boundaries**

| Domain | Owns | Must not hold |
|--------|------|----------------|
| This service | Bot/transport secrets; Channel Bearer to bridge; SQLite path | Model API keys; gateway credentials; interview FSM |
| Bridge | Models, roles, dual confirm, gateway client | Telegram Bot API ownership (target) |

---

## 3. Ownership / contracts

| Artifact class | Owner |
|----------------|--------|
| Source + docs | Git in `doge-telegram/` (product name `doge-telegram-channel`) |
| SQLite (seen + outbox) | **Volume** (not Git) |
| Channel OpenAPI | `doge-ai-bridge` (consume; do not fork SSOT here unless additive change approved — AC-TG-01-03) |
| Railway **service name** | **Unknown** until create wave (deferred) |
| CDN | N/A |

---

## 4. Runtime / packaging / verify / env / deploy-residual

See [01-runtime-and-packaging.md](./01-runtime-and-packaging.md). Summary locks:

- **Ingress v1:** long-poll only (not webhook; not dual-by-default).  
- **Process:** one production entry = poller + minimal health HTTP.  
- **Packaging:** Git ownership ≠ image packaging; name production entry (module path TBD create wave); Volume mount for SQLite.  
- **Verify:** same entry + stub bridge via env (AC-TG-01-04/05).  
- **Live residual:** real Telegram↔bridge smoke — explicit residual, not silent Product Done.  
- **Fail-closed:** missing required bot/transport token, bridge base URL, channel bearer, or DB path → not ready / do not run crookedly.

---

## 5. Coexistence with as-is

| Fact | Path / note |
|------|-------------|
| Focus runtime app | **Unknown** — no `.py` application tree yet (scaffold deferred; README) |
| Requirements | [REQ-01](../../requirements/REQ-01-REQ15-TELEGRAM-CHANNEL-TRANSPORT.md) Draft |
| Bridge channel façade | Present — `app.py:909/:939` |
| Live n8n prod | **Absent** (operator interview) — migration = bootstrap target path, not cutover of live callers |
| Builder bootstrap | `docs/tasks/` pkg-000000 marker only — not product P3 |

Data/delivery detail: [02-data-and-delivery.md](./02-data-and-delivery.md).

---

## 6. Open questions

- Exact `python -m …` / src layout (create wave).  
- Exact Railway service string.  
- JSON field mapping Telegram update ↔ channel envelopes — only from peer OpenAPI + implement read.  
- SQLite TTL/purge policy.  
- Health bind host/port defaults.  
- Private URL to bridge / full live residual env beyond bot token (bot key name locked: **`TELEGRAM_BOT_TOKEN`** — see [`01-runtime-and-packaging.md`](./01-runtime-and-packaging.md) §3; local `.env` may already hold a nonempty token for testing).

---

## 7. Explicitly not in this doc

- NEW backlog STORY keys, epic waves, task README, pkg edits  
- Invented HTTP paths beyond Present turns/actions  
- Product code, stub schemas «so paths exist»  
- Interview/provider/gateway logic (aibridge / siblings)
