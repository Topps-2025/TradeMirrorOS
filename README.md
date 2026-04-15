# Finance Journal

Finance Journal is now focused on one core problem: combining OpenClaw-style orchestration with long-term trading memory.

It is a local-first framework for:
- conversation-first trade journaling
- structured plan / trade / review records
- long-term memory storage and retrieval
- trajectory self-evolution with bandit reranking
- memory-to-skill solidification for reusable trading know-how

It is not a news monitor, announcement crawler, or copy-trading system.

## Current Architecture

- `finance-journal-orchestrator/`: OpenClaw-facing entry, session gateway, references
- `trade-plan-assistant/`: plan creation and historical reference
- `trade-evolution-engine/`: trade logs, review loop, self-evolution outputs
- `behavior-health-reporter/`: behavior and discipline reports
- `finance_journal_core/`: shared runtime, storage, memory, retrieval, vault export
- `tests/`: smoke tests for the memory-centric workflow

## Runtime Layout

- SQLite database: `_runtime/data/finance_journal.db`
- Daily artifacts: `_runtime/artifacts/daily/YYYYMMDD/`
- Long-term memory snapshots: `_runtime/memory/`
- Markdown vault: `_runtime/obsidian-vault/`

## Long-Term Memory Design

The current memory layer uses:
- `memory_cells`: atomic memory units built from plans, trades, and reviews
- `memory_scenes`: scene-level aggregates such as symbol, setup, stage, and strategy-line scenes
- `memory_hyperedges`: multi-node relations for setup, risk, strategy, regime, and symbol linkage
- `memory_skill_cards`: reusable skill cards distilled from stable historical paths

Retrieval is coarse-to-fine:
1. SQLite FTS5 + structured filters
2. scene / hyperedge expansion
3. bandit-aware reminder reranking

## Key Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn --session-key qq:user_a --trade-date 20260410 --text "Bought 603083 on a pullback setup"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade import-statement --file .\examples\statement_rows.csv --trade-date 20260415 --session-key qq:user_a
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution remind --logic-tags pullback,leader --pattern-tags ma_pullback --market-stage range --environment-tags repair_flow
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory rebuild
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory query --ts-code 603083 --market-stage range --tags pullback,repair_flow
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory skillize --trade-date 20260415 --lookback-days 365
python .\finance-journal-orchestrator\scripts\run_memory_benchmark.py --root .\_runtime_benchmark --disable-market-data
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
```

## Design Notes

- `TRADE_MEMORY_ARCHITECTURE.md`: concise design note for the EverOS / EverMemOS / HyperMem inspired memory stack
- `TRADE_MEMORY_SYSTEM_PAPER.md`: paper-style architecture write-up with LaTeX-ready equations and implementation mapping
- `OPENCLAW_DEMO_WORKFLOW.md`: end-to-end OpenClaw classroom demo flow
- `MEMORY_RETRIEVAL_BENCHMARK.md`: benchmark design, baselines, and current local results
- `IMPLEMENTED_FEATURES.md`: what is already done
- `NOT_IMPLEMENTED_YET.md`: what remains intentionally open

## Repo Sync Policy

- Public GitHub (`origin/main`) receives the core code, tests, and documentation.
- Private GitHub (`github-private/private-sync`) may additionally receive runtime data, broker statement exports, and local vault snapshots.
- `_runtime*`, `*.db`, and broker statement spreadsheets stay ignored by default and should only be force-added for private syncs.

## Validation

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```
