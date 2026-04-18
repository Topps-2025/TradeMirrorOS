# Sync Scenarios

## Scenario A: Desktop Already Updated -> Cloud Pulls Latest Private Data

Desktop side:

```powershell
python .inance-journal-orchestrator\scriptsinance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .inance-journal-orchestrator\scriptsinance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync private runtime snapshot"
git push origin private-sync
```

Cloud side:

```bash
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
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

## Scenario C: Cloud Already Pushed -> Desktop Pull Through OpenClaw

```powershell
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python .inance-journal-orchestrator\scriptsinance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

## Scenario D: Code-Only Framework Update -> Push To Public Repo

Before acting, verify the change does not include:

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
