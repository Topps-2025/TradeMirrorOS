# TradeMirrorOS Command Cheatsheet

## CLI

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn --session-key qq:user_a --trade-date 20260410 --text "Bought 603083 on a pullback setup"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade import-statement --file .\examples\statement_rows.csv --trade-date 20260415 --session-key qq:user_a
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create --ts-code 603083 --direction buy --thesis "pullback to 5-day moving average" --logic-tags leader,pullback --buy-zone 42.5-43.0 --stop-loss 40.0 --valid-to 20260415
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log --ts-code 603083 --buy-date 20260410 --buy-price 43.2 --thesis "pullback to 5-day moving average" --logic-type-tags leader,pullback --pattern-tags ma_pullback --market-stage range --environment-tags repair_flow,CPO
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution remind --logic-tags leader,pullback --pattern-tags ma_pullback --market-stage range --environment-tags repair_flow
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory rebuild
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory query --ts-code 603083 --market-stage range --tags leader,pullback
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory skillize --trade-date 20260415 --lookback-days 365
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --full --clean
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault graph
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault mirror-root
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py maintenance self-check
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py maintenance purge-range --start-date 20260201 --end-date 20260331
python .\finance-journal-orchestrator\scripts\run_memory_benchmark.py --root .\_runtime_benchmark --disable-market-data
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory revise memory_trade_xxx --add-tags error_cluster:trend_conflict --quality-score -8 --market-stage downtrend --correction-note "wrong thesis for downtrend"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py memory skill-edit skill_quality_path_xxx --add-do-not-use-when "when the market is shrinking and trending down"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py schedule --now 2026-04-15T08:05 --dry-run
```

## Gateway

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "session turn session=qq:user_a trade_date=20260410 text='Bought 603083 on a pullback setup'"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "plan create ts_code=603083 direction=buy thesis='pullback to 5-day moving average' logic_tags=leader,pullback buy_zone=42.5-43.0 stop_loss=40 valid_to=20260415"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "trade log ts_code=603083 buy_date=20260410 buy_price=43.2 thesis='pullback to 5-day moving average' logic_tags=leader,pullback pattern_tags=ma_pullback market_stage=range environment_tags=repair_flow,CPO"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "memory query ts_code=603083 market_stage=range tags=leader,pullback"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "memory skillize trade_date=20260415 lookback_days=365 min_samples=2"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "vault graph"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "vault mirror-root"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "vault sync full=true clean=true"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "vault sync-all"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "maintenance self-check"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "maintenance purge-range start_date=20260201 end_date=20260331"
```

## Private / Public Repo Sync

```powershell
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git push origin private-sync

git checkout main
git pull --rebase public main
git push public main
```
