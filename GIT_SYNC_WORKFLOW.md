# Git Sync Workflow

Updated: 2026-04-13

This repository now uses a dual-remote strategy:

- GitHub `origin`: public, push core code only
- Gitee `gitee`: private, can additionally carry personal statement files and runtime ledger data

## Recommended Branch Model

Use two long-lived branches locally:

### 1. `main`

Purpose:

- public code branch
- safe to push to GitHub
- can also be pushed to Gitee

Should contain:

- `finance_journal_core/`
- `finance-journal-orchestrator/`
- `tests/`
- public docs such as `README.md`, `README.zh-CN.md`, `CONTRIBUTING.md`

Should not contain:

- raw broker statements
- `_runtime*/`
- personal ledgers or private notes

### 2. `private-sync`

Purpose:

- private data sync branch
- push to Gitee only
- used by cloud servers that need direct access to your real imported ledger state

May contain:

- `_runtime/`
- raw statement files such as `20260413交割单查询.xls`
- any private artifacts you explicitly choose to sync

Important:

- do not push `private-sync` to GitHub
- keep `private-sync` based on the latest `main`, then add the private files on top

## Why This Split Works

Git pushes commits, not “remote-specific ignore rules”.

That means:

- one branch cannot contain private files on Gitee but magically hide them on GitHub
- if a commit contains private data, pushing that same commit to GitHub will leak it

So the safe pattern is:

- `main` = public-safe commits
- `private-sync` = `main` plus private data commits

## Current Ignore Boundary

The repository already ignores runtime state by default:

- `_runtime*/`
- `*.db`
- `*.db-shm`
- `*.db-wal`

This is correct for `main`.

When preparing `private-sync`, you can still force-add those files with `git add -f`.

## Suggested Daily Flow

### Public code flow

1. work on code and docs in `main`
2. validate locally
3. commit only public-safe files
4. push `main` to:
   - `origin/main`
   - optionally `gitee/main`

### Private data flow

1. update `main` first
2. switch to `private-sync`
3. rebase or merge from `main`
4. force-add the private files you want to sync
5. commit the private sync snapshot
6. push `private-sync` to `gitee/private-sync`

## Recommended Commands

### A. Push public code to GitHub

```powershell
git checkout main
git status --short
git add README.md README.zh-CN.md GIT_SYNC_WORKFLOW.md
git add finance_journal_core finance-journal-orchestrator tests
git commit -m "feat: add grouped gateway follow-up workflow"
git push origin main
```

### B. Push the same core code to private Gitee

```powershell
git checkout main
git push gitee main
```

### C. Create or refresh the private sync branch

```powershell
git checkout main
git checkout -B private-sync
git add -f _runtime
git add -f "20260413交割单查询.xls"
git commit -m "data: sync private runtime and broker statements"
git push -u gitee private-sync
```

If `private-sync` already exists locally:

```powershell
git checkout private-sync
git rebase main
git add -f _runtime
git add -f "20260413交割单查询.xls"
git commit -m "data: refresh private runtime snapshot"
git push gitee private-sync
```

## Cloud Server Recommendation

For a cloud server that should receive both code and your personal ledger:

```powershell
git clone <your-gitee-private-repo>
git checkout private-sync
```

After that, future updates can use:

```powershell
git checkout private-sync
git pull --rebase gitee private-sync
```

## Safety Checklist Before Any Push

Before pushing to GitHub:

- verify you are on `main`
- run `git status --short`
- make sure `_runtime/`, raw `.xls` statements, and other private files are not staged

Before pushing to Gitee private branch:

- verify you are on `private-sync`
- confirm the remote target is `gitee`
- confirm the branch is not going to GitHub

## Recommended Data Completion Flow

For real-money workflows, the practical order is now:

1. import statement facts
2. run `trade incomplete`
3. run `generate_gateway_followups.py`
4. use the generated grouped prompts on the gateway side
5. continue enrichment until the backlog shrinks
6. regenerate self-evolution outputs after the missing context is filled in

Example:

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime trade incomplete --limit 200
python .\finance-journal-orchestrator\scripts\generate_gateway_followups.py --root .\_runtime --status open --format markdown --output .\_runtime\artifacts\daily\20260413\gateway_followups.md
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime evolution report --trade-date 20260413 --lookback-days 365 --min-samples 2
```

## Bottom Line

Use:

- `main` for public core code
- `private-sync` for private ledger snapshots on Gitee

That is the cleanest way to satisfy both goals:

- GitHub stays open-source and safe
- Gitee can act as your private cloud sync channel for real trading data
