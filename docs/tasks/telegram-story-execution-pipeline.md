# Telegram — Story execution pipeline

> **Профиль Builder Queue:** `telegram`  
> **Операторский маршрут:** [`docs/methodology/Zeya888-builder-queue/core/workflow.md`](../../../docs/methodology/Zeya888-builder-queue/core/workflow.md)  
> **Runtime plan:** [`.cursor/plans/Telegram_builder.plan.md`](../../../.cursor/plans/Telegram_builder.plan.md)

## SSOT

| Слой | Источник |
|------|----------|
| Builder Queue statuses | [`bullrun-launch-index.md`](bullrun-launch-index.md) |
| Очередь исполнения | immutable `telegram-active-packages/pkg-*.yaml` |
| Backlog | [`backlog-stories/INDEX.md`](backlog-stories/INDEX.md) |
| Operator contract | [`telegram-operator-contract.md`](../../../docs/methodology/Zeya888-builder-queue/contracts/telegram-operator-contract.md) |
| Tests | `cd doge-telegram && python3 -V` (`profiles.yaml` → `test_command`) |

## Skill routing

| Зона | Skill |
|------|-------|
| Python Telegram transport | `python-pro` |
| Task README override | as declared in README |

## Boundary

Outbound HTTP only to doge-ai-bridge channel façade (`/v1/channel/turns`, `/v1/channel/actions`). No model keys; no interview FSM in this focus.

## Перед batch-run (обязательно)

1. [`bullrun-launch-index.md`](bullrun-launch-index.md) §«Актуальная точка».
2. [`telegram-active-package.current.yaml`](telegram-active-package.current.yaml) → `package_file`.
3. `python3 docs/methodology/Zeya888-builder-queue/cli/builder_resolve_queue.py --project telegram --verify`
4. Epic/story without materialized task queue → **P1.1** / **P1.3**, not P3 Execute.
5. One `input_mode` per session (contract §4).

## Gate: Story AC

After last task README in story — AC from materialized story or backlog `STORY-TELEGRAM-*`.

## Gate: Epic AC

After all stories in epic — Goal/AC in epic file.

## Fixed plan

@attach runtime plan — **не** Build / Execute на файле плана.
