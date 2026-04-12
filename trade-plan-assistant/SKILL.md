---
name: trade-plan-assistant
description: 负责交易计划的结构化创建、有效期管理、状态更新与历史相似场景参考查询。适用于盘前计划录入、计划提醒、执行/放弃标记，但不替代用户做计划内容上的决策。
---

# Trade Plan Assistant

## Read First

- `../finance-journal-orchestrator/references/data-contracts.md`
- `../finance-journal-orchestrator/references/command-cheatsheet.md`

## Primary Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create --ts-code 603083 --direction buy --thesis "回踩 5 日线参与" --logic-tags 龙头首阴,低吸 --buy-zone 42.5-43.0 --stop-loss 40.0 --valid-to 20260415 --with-reference
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan list --active-only --trade-date 20260410
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan status <plan_id> --status executed --trade-id <trade_id>
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan reference --logic-tags 龙头首阴 --market-stage 震荡市 --environment-tags 高位分歧,CPO
```

## Notes

- 先问清标的、方向、逻辑、止损和有效期，再落库。
- 历史参考只能描述历史统计，不允许写成“建议买入/卖出”。
- 若用户放弃计划，尽量记录 `reason`，便于后续体检。
