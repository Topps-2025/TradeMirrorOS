# Private Sync Handbook

## Purpose

Use this handbook when OpenClaw needs to synchronize Finance Journal between:

- local desktop
- cloud gateway / cloud runtime
- private repo `origin/private-sync`
- public repo `public/main`

This is the canonical operational guide for OpenClaw sync tasks.

## Repo Split Policy

### Private data -> `origin/private-sync`

Push private data only to the private repo when the change touches:

- `_runtime/data/finance_journal.db`
- `_runtime/obsidian-vault/`
- `obsidian-vault/`
- `artifacts/`
- any private trade, review, or memory export

### Public framework -> `public/main`

Push public framework changes only to TradeMirrorOS when the change touches:

- `finance_journal_core/`
- `finance-journal-orchestrator/`
- `tests/`
- public docs, prompts, and generic workflow files

If a task mixes code updates and private runtime data, split it into separate commits and separate pushes.

## Runtime Rules

1. Treat `./_runtime` as the private runtime source of truth.
2. Use `python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime ...` for OpenClaw-side runtime operations.
3. Run `maintenance self-check` before and after important pull / push operations.
4. If repo-root mirrors are stale, run `vault sync-all` and then rerun `maintenance self-check`.
5. Never treat `vault graph` as a restore command. It only exports the current DB state.

## Scenario A: Desktop Already Updated -> Cloud Pulls Latest Private Data

### Desktop side

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync private runtime snapshot"
git push origin private-sync
```

### Cloud side

```bash
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
```

If needed:

```bash
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
```

## Scenario B: Cloud Fragment Journaling -> Push Back To Private Repo

```bash
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync cloud journaling snapshot"
git push origin private-sync
```

## Scenario C: Cloud Already Pushed -> OpenClaw Takes Over Desktop To Pull

```powershell
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

If needed:

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

## Scenario D: Code-Only Framework Update -> Push To TradeMirrorOS

Before pushing, verify the change does not include:

- `_runtime/data/finance_journal.db`
- `_runtime/obsidian-vault/`
- `obsidian-vault/`
- `artifacts/`

Then:

```powershell
git checkout main
git pull --rebase public main
git cherry-pick <code-only-commit>
git push public main
```

## What To Report Back

At the end of every sync task, report:

- repo root
- current branch
- current remote target
- current HEAD commit hash
- `runtime_root`
- `matches_repo_runtime`
- `mirror_state.in_sync`
- `trades`
- `memory_cells`

## Skill Trigger Guidance

When the user mentions any of these ideas, load this handbook before acting:

- sync
- pull update
- push update
- private repo
- cloud repo
- OpenClaw gateway
- desktop takeover
- local and cloud alignment
