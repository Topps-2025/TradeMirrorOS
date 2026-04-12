---
name: behavior-health-reporter
description: 负责交易行为体检报告生成，聚焦计划执行率、计划外交易、持仓偏离、止损纪律、连亏后行为与大赚后频率变化等非盈亏指标。
---

# Behavior Health Reporter

## Read First

- `../finance-journal-orchestrator/references/data-contracts.md`
- `../finance-journal-orchestrator/references/operating-rhythm.md`

## Primary Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py report health --period-start 20260401 --period-end 20260430 --period-kind monthly
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault report <report_id>
python .\finance-journal-orchestrator\scripts\run_finance_journal_schedule.py schedule --now 2026-05-06T08:20
```

## Notes

- 体检报告是行为镜子，不是绩效炫耀板。
- 当样本不足、仓位数据缺失或止损推断只能近似时，必须显式写出限制。
- 重点暴露“计划-执行偏差”和“情绪后行为变化”，而不是只看单笔盈亏。
- 报告生成后可以同步到 Obsidian vault，方便长期对比月度变化。
