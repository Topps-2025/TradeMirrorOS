# Finance Journal

Finance Journal is a conversation-first trading journal and reflection framework for discretionary and semi-systematic traders.

It is designed for workflows such as:

- capturing plans, trades, emotions, mistakes, and lessons in natural language
- filling missing details through follow-up questions instead of forcing rigid forms up front
- importing standardized broker statement rows first, then adding the subjective reasoning later
- exporting structured records into Markdown, JSON artifacts, and an Obsidian vault
- turning historical trades into review prompts, health reports, and self-evolution summaries

The current implementation ships with defaults that are convenient for China A-share workflows, such as `ts_code`, Tushare-based market data, and prebuilt Chinese news adapters. However, the session model, statement-import flow, reflection loop, and vault-export architecture are intentionally reusable beyond one market.

## What This Repository Is

Finance Journal is primarily:

- a local-first trading behavior journal
- a session-oriented journaling skill for OpenClaw-style chat workflows
- a bridge between free-form notes and structured review data
- a personal improvement system for plans, trades, reviews, and discipline analysis

It is not:

- an order execution system
- a stock-picking oracle
- investment advice
- a fully automated quant platform

## Storage Model

The project uses a local-first storage stack:

- SQLite database: `_runtime/data/finance_journal.db`
- daily artifacts: `_runtime/artifacts/daily/YYYYMMDD/`
- long-term memory: `_runtime/memory/`
- Markdown knowledge base: `_runtime/obsidian-vault/`

## Repository Layout

- `finance-journal-orchestrator/`: primary skill entry, CLI wrappers, gateway scripts, references
- `finance-info-monitor/`: optional news and announcement monitoring skill
- `trade-plan-assistant/`: planning workflows and reference generation
- `trade-evolution-engine/`: trade journaling, post-trade review, self-evolution outputs
- `behavior-health-reporter/`: behavior and discipline reports
- `finance_journal_core/`: shared Python core logic
- `tests/`: offline smoke tests
- `examples/`: sample input files such as statement rows

## Quick Start

### 1. Initialize the runtime

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault init
```

### 2. Parse or apply a natural-language journal entry

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake parse `
  --mode trade `
  --trade-date 20260410 `
  --text "Bought 603083 around 43.2 today, looking for a CPO rebound, but I felt rushed intraday."

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake apply `
  --mode plan `
  --trade-date 20260410 `
  --text "Plan to buy 603083 around 42.5-43.0 with a stop at 40 if the sector rotation confirms."
```

### 3. Run a session-based journaling flow

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn `
  --session-key user_a `
  --trade-date 20260410 `
  --text "I bought 603083 today"
```

The session flow can:

- start a draft
- continue missing-field follow-up
- auto-apply when the facts are sufficient
- reuse same-day market context and same-symbol thesis context when safe
- enrich the latest plan or trade after the record is already stored

### 4. Import statement facts first, add reasoning later

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade import-statement `
  --file .\examples\statement_rows.csv `
  --trade-date 20260415 `
  --session-key user_a
```

This flow is built for a "facts first, reasons later" workflow:

- align symbol, dates, prices, quantity, amount, and fees from standardized CSV or JSON rows
- match an existing trade when possible
- close an existing open trade when the statement row supplies the sell facts
- return `assistant_message`, `pending_question`, and `follow_up_queue` so the conversation can continue with thesis, trigger, position sizing, emotion, and discipline details

### 5. Create a plan, log a trade, and export notes

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create `
  --ts-code 603083 `
  --direction buy `
  --thesis "Pullback into a 5-day moving average rebound setup" `
  --logic-tags first-pullback,mean-reversion `
  --buy-zone 42.5-43.0 `
  --stop-loss 40.0 `
  --valid-to 20260415

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log `
  --ts-code 603083 `
  --buy-date 20260410 `
  --buy-price 43.2 `
  --thesis "Pullback rebound setup" `
  --logic-type-tags first-pullback,theme-driven `
  --pattern-tags moving-average-retest

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
```

## Session and Polling Design

The parser and follow-up system intentionally avoid turning every message into a long rigid questionnaire.

Current outputs include:

- `standardized_record`: a soft-structured preview for indexing and review
- `polling_bundle`: next question, missing-field queue, parsing hints, completion progress, and reuse metadata
- `reflection_prompts`: post-fact prompts for lessons, mistakes, and behavioral review

`polling_bundle` also includes:

- `shared_context_hints`: tells the caller which answers may be reused across `trade_date`, `symbol`, or `strategy`
- `parallel_question_groups`: tells the caller which related questions can be merged into one reply block

This helps reduce repetitive polling, especially for:

- same-day market context
- repeated intraday trades on the same symbol
- semi-systematic strategy lines where factor choice and activation logic are shared across several entries

## Decision Context and Semi-Quant Workflows

Records can persist `decision_context_json`, which currently supports:

- user focus and observed signals
- position reason and confidence
- stress level, emotion notes, and mistake tags
- market stage, environment tags, and risk boundaries
- nested `strategy_context` for semi-quant or quant-adjacent workflows

`strategy_context` can hold fields such as:

- strategy line
- strategy family
- factor list
- factor selection reason
- activation reason
- parameter version
- portfolio role
- subjective override notes

The purpose is not to pretend the system is fully automated. The goal is to preserve the human override layer that still exists around factor selection, strategy activation, and tactical exceptions.

## Information Monitoring

The optional monitoring layer can:

- add manual events
- fetch events from configured URL adapters
- generate a morning brief
- support timeline pages, list pages, article pages, RSS, JSON feeds, and embedded JSON pages

Current examples and presets still emphasize the China market because they match the default adapters and test data, but the architecture is adapter-based rather than hard-coded to one site.

## Open Source Collaboration Files

This repository now includes the standard public-project files expected on Git hosting platforms:

- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `.github/ISSUE_TEMPLATE/`
- `.github/pull_request_template.md`
- `.github/workflows/ci.yml`
- `.github/dependabot.yml`

## Validation

Current local validation commands:

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```

## Additional Documents

- implemented capabilities: `IMPLEMENTED_FEATURES.md`
- known gaps and next steps: `NOT_IMPLEMENTED_YET.md`
- unified status and changelog: `FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`
- framework purpose and vision: `FRAMEWORK_PURPOSE_AND_VISION.md`
- community vision: `COMMUNITY_AGENT_LEDGER_VISION.md`
- git sync guidance: `GIT_SYNC_WORKFLOW.md`
- showcase demo notes: `SHOWCASE_DEMO_WALKTHROUGH.md`

## Notes

- Tushare tokens are read from `TUSHARE_TOKEN` or `TS_TOKEN` when market data is enabled.
- If networking is not available, pass `--disable-market-data` and use the journal offline.
- Examples still use A-share-style identifiers because they match the current adapters and fixtures.
- The framework focuses on journaling, review, and behavioral improvement rather than trade execution.
