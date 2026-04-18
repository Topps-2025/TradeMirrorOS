---
name: finance-journal-sync
description: Dedicated sync skill for Finance Journal private/public repo operations. Use it when OpenClaw needs to pull updates from `origin/private-sync`, push cloud journaling snapshots back to the private repo, trigger desktop pull-through updates, decide whether a change belongs to the private repo or `public/main`, or follow the `./_runtime` source-of-truth sync workflow safely.
---

# Finance Journal Sync

## Overview

Use this skill for all repository synchronization tasks between local desktop, cloud OpenClaw runtime, the private repo, and the public TradeMirrorOS repo.

Read:

- `references/sync-scenarios.md` for the step-by-step operational flows
- `references/gateway-prompts.md` for ready-to-paste OpenClaw gateway instructions

## Workflow Decision

Classify the request into one of four scenarios before running commands:

1. desktop already updated -> cloud pulls latest private data
2. cloud fragment journaling -> cloud pushes latest private snapshot
3. cloud already pushed -> OpenClaw takes over desktop to pull latest private changes
4. code-only framework update -> push to `public/main`

If the task mixes private runtime data and public framework changes, stop and split the work into separate commits and separate pushes.

## Runtime Rules

1. Treat `./_runtime` as the private runtime source of truth.
2. Run `maintenance self-check` before and after important pull / push operations.
3. If repo-root mirrors are stale, run `vault sync-all`, then rerun `maintenance self-check`.
4. Never treat `vault graph` as a restore command.
5. Never push private runtime files to the public TradeMirrorOS remote.

## Routing Rules

### Private repo flow

Use `origin/private-sync` when the task touches:

- `_runtime/data/finance_journal.db`
- `_runtime/obsidian-vault/`
- `obsidian-vault/`
- `artifacts/`
- private trade, review, or memory exports

### Public repo flow

Use `public/main` when the task touches:

- `finance_journal_core/`
- `finance-journal-orchestrator/`
- `tests/`
- generic docs, prompts, or public skill definitions

## Standard Commands

### Pull latest private data to cloud

```bash
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
```

### Push cloud snapshot back to private repo

```bash
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync cloud journaling snapshot"
git push origin private-sync
```

### Pull latest private changes onto desktop

```powershell
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

### Push code-only framework changes to public repo

```powershell
git checkout main
git pull --rebase public main
git cherry-pick <code-only-commit>
git push public main
```

## Output Contract

At the end of every sync task, report:

- repo root
- current branch
- current remote target
- HEAD commit hash
- `runtime_root`
- `matches_repo_runtime`
- `mirror_state.in_sync`
- `trades`
- `memory_cells`
