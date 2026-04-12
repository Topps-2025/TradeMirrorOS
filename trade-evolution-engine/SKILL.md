---
name: trade-evolution-engine
description: 负责交易日志、卖出后自动回顾、历史条件参考与交易行为自进化。它是整套账本的核心模块，适用于开仓/平仓记录、回看操作绩效差值、生成卖飞回顾、沉淀情绪/失误/经验，并同步到 Markdown 知识库。
---

# Trade Evolution Engine

## Read First

- `../finance-journal-orchestrator/references/data-contracts.md`
- `../finance-journal-orchestrator/references/operating-rhythm.md`
- `../finance-journal-orchestrator/references/command-cheatsheet.md`
- `references/evolution-algorithms.md`

## Primary Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log --ts-code 603083 --buy-date 20260410 --buy-price 43.2 --thesis "回踩 5 日线参与" --logic-type-tags 龙头首阴,题材驱动 --pattern-tags 均线回踩 --emotion-notes "盘中略急，但没有追高" --mistake-tags 拿不稳 --lessons-learned "更适合分批止盈"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade close <trade_id> --sell-date 20260415 --sell-price 46.8 --sell-reason "达到预设止盈" --lessons-learned "下次更早规划分批卖点"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py review run --as-of-date 20260422
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py review respond <review_id> --feedback "是，卖得偏早" --weight-action lower
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan reference --logic-tags 龙头首阴 --market-stage 震荡市 --environment-tags 高位分歧,CPO
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault trade <trade_id>
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution report --trade-date 20260415 --lookback-days 365 --min-samples 2
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution remind --logic-tags 低吸 --pattern-tags 均线回踩 --market-stage 震荡市 --environment-tags 修复回流
```

## Notes

- 能先记事实就先记事实；标签和解释可以后补，但买卖日期/价格不要丢。
- 回顾输出必须保留原始卖出理由，不允许事后篡改交易事实。
- 搭档参考本质是个人样本统计，不是预测模型。
- `emotion_notes / mistake_tags / lessons_learned` 是账本长期进化的关键字段，尽量别空着。
- 当前自进化已加入 bandit 风格排序层：优先匹配历史优质路径，再压制风险臂；它是提醒系统，不是自动策略。
