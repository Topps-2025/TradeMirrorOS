# Git Sync Workflow

Updated: 2026-04-12

This document explains how to keep code and runtime ledger data in sync without accidentally overwriting one environment with another.

## Goals

1. sync code and skill configuration between local and cloud environments with Git
2. avoid treating the runtime ledger database as a file that should be blindly overwritten by `git pull` or `git push`

## Recommended Boundary

Split the repository into two layers:

### Code layer: track with Git

- `finance_journal_core/`
- `finance-journal-orchestrator/`
- `tests/`
- top-level docs and templates

### Runtime ledger layer: do not track directly with Git

- `_runtime*/data/finance_journal.db`
- `_runtime*/artifacts/`
- `_runtime*/memory/`
- `_runtime*/obsidian-vault/`

The repository already ignores `_runtime*/` and SQLite database files through `.gitignore` so runtime state is not committed by default.

## Why Not Commit the SQLite Ledger Directly

The SQLite ledger is a current-state database, not a natural append-only merge log.

If the full database file is pushed back and forth with Git, common risks include:

- local changes overwriting cloud-side journal updates
- cloud changes overwriting local follow-up notes and session traces
- binary merge conflicts that cannot be resolved safely at record level
- accidental rollback of a meaningful block of trading history

Because of that, the recommended rule is simple:

- Git syncs code and contracts
- journal facts should move through structured import and export flows

## Safe Ways to Connect Local and Cloud Workflows Today

### 1. Conversational journaling

Continue using:

- `session turn`
- `intake draft-start / draft-reply`
- `trade enrich`

This is the best path for gradually adding subjective context such as thesis, trigger, position sizing logic, emotion, and mistakes.

### 2. Standardized statement import

Currently supported:

- `trade import-statement --file ...`
- gateway route: `trade import file=... session=... trade_date=...`

This flow prioritizes fact alignment first:

- symbol and name
- buy and sell dates
- buy and sell prices
- quantity, amount, and fees when supplied

After the facts are aligned, the system can continue through:

- `assistant_message`
- `pending_question`
- `follow_up_queue`
- `session_state.pending_question`

That lets you keep reasoning, triggers, position logic, and emotional context in the conversational layer instead of forcing them into the import file.

## Recommended Operating Flow

### Code updates

1. change code locally and validate it
2. `git add` and `git commit`
3. push code to the remote repository
4. run `git pull --rebase` on the server

### Ledger completion

1. capture quick journal notes on the cloud side, or import standardized statement rows there
2. pull the latest code where needed
3. continue enrichment through text, notes, or vault exports
4. do not rely on uploading a whole runtime directory and overwriting the target environment

## Recommended Next Step for Stronger Sync

If you later want safer bidirectional ledger sync between local and cloud environments, the next features should be:

1. structured export and import bundles
   - JSONL or NDJSON at record level
   - explicit `entity_id`, `updated_at`, and `source` fields
2. ledger merge rules
   - record-level merge instead of whole-database overwrite
   - conflict rules for `trade`, `plan`, `review`, and `session_thread`

Until those features exist, the safest rule remains:

- code through Git
- facts through conversational enrichment and standardized statement import
