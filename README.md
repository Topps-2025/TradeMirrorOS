# TradeMirrorOS

TradeMirrorOS is a local-first operating layer for trading memory.

It mirrors your plans, executions, mistakes, effective paths, and review loops back to you so they become durable, searchable, and reusable instead of disappearing into chat history.

- Public repo: <https://github.com/Topps-2025/TradeMirrorOS.git>
- Chinese README: [`README.zh-CN.md`](README.zh-CN.md)
- Promo copy: [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md) / [`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md)

## Why the name

- `Trade`: this is for trading behavior, not a general chat memory layer.
- `Mirror`: it reflects your historical behavior, cognition, errors, and valid paths back to you.
- `OS`: it acts as an operating layer, not a single-purpose utility.

In plain English, TradeMirrorOS is a trading-memory operating system for human-machine co-evolution.

## What it is

- conversation-first journaling for plans, trades, reviews, and corrections
- structured storage backed by SQLite and markdown exports
- long-term memory with memory cells, scenes, hyperedges, and skill cards
- local knowledge-graph snapshots that update with the database
- OpenClaw-friendly orchestration for daily capture, review, and recall

## What it is not

- not a signal-calling system
- not an auto-trading agent
- not just a ledger
- not a generic note dump

It is a cognitive mirror plus long-term memory layer for trading work.

## Runtime vs Repo Snapshot

The most important operational distinction is:

- live runtime: `_runtime/`
- git-friendly mirror snapshot: `artifacts/` and `obsidian-vault/` at repo root

The live database and live Obsidian exports are generated under `_runtime/`.
The repo-root `artifacts/` and `obsidian-vault/` are mirrored snapshots that exist so git can carry them across machines.

If OpenClaw points at the wrong `runtime_root`, it can read an older ledger even when the repository itself is up to date.

## Key Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn --session-key qq:user_a --trade-date 20260410 --text "Bought 603083 on a pullback setup"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --full --clean
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py maintenance self-check
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "vault sync-all"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "maintenance self-check"
```

## Recommended Local Sync Flow

1. Write or import trades into `_runtime/data/finance_journal.db`.
2. Run `vault sync-all` to rebuild the runtime vault and mirror exports to repo root.
3. Commit and push the mirrored repo snapshot.
4. On another machine or in OpenClaw cloud, pull the repo and run `maintenance self-check`.

## Current Architecture

- `finance-journal-orchestrator/`: OpenClaw-facing entry, gateway scripts, and references
- `trade-plan-assistant/`: plan creation and historical reference
- `trade-evolution-engine/`: trade reviews, reminders, self-evolution outputs
- `behavior-health-reporter/`: behavior and discipline reports
- `finance_journal_core/`: runtime, storage, memory, retrieval, and vault export
- `tests/`: local validation for journaling and memory workflows

## Public / Private Sync Policy

- Public GitHub (`origin/main`) is now the TradeMirrorOS code and documentation surface.
- Private sync branches can still carry runtime mirrors and sensitive ledger snapshots when needed.
- `_runtime*`, `*.db`, and broker exports remain ignored by default.

## Validation

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```
