---
name: finance-journal-orchestrator
description: 基于 OpenClaw 的交易行为复盘记账本总控技能。用于会话级记账、计划录入、多轮补全、已落账二次沉淀、自进化提醒、行为体检与 Obsidian 知识库同步；适合通过 OpenClaw、QQ、飞书等聊天平台调用，不替代人的最终买卖决策。
---

# Finance Journal Orchestrator

协调整个“交易行为复盘记账本”框架。

## Read First

先读：
- `..\FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`
- `references/data-contracts.md`
- `references/operating-rhythm.md`
- `references/openclaw-skill-functional-spec.md`
- `references/command-cheatsheet.md`
- `references/intake-workflow.md`
- `references/openclaw-session-contract.md`
- `config/runtime.example.json`

## Default Workflow

- 初始化运行时：`scripts/init_finance_journal.py`
- 结构化命令入口：`scripts/finance_journal_cli.py`
- OpenClaw / QQ / 飞书网关入口：`scripts/finance_journal_gateway.py`
- OpenClaw / 聊天平台会话级入口：`scripts/finance_journal_session_agent.py`
- 定时调度入口：`scripts/run_finance_journal_schedule.py`

## Route by Task

- 信息监测 / 晨报（可选增强） -> 用 `$finance-info-monitor`
- 计划创建 / 更新 / 历史参考 -> 用 `$trade-plan-assistant`
- 交易记录 / 卖出后回顾 / 搭档参考 -> 用 `$trade-evolution-engine`
- 行为体检 -> 用 `$behavior-health-reporter`
- Obsidian / Markdown 知识库导出 -> 直接使用本 skill 的 `vault` 命令
- 当用户只说“帮我把整套流程跑起来”时，就留在本 skill 协调

## Output Discipline

每次都遵守：
1. 先写 SQLite，再写 JSON / Markdown artifact。
2. 若启用 vault，再把结构化记录同步成 Obsidian markdown。
3. artifact 默认落在 `_runtime/artifacts/daily/YYYYMMDD/`。
4. 所有报告都要引用 trade date / period。
5. 明确哪些结论来自历史统计，哪些只是信息整理。
6. 不荐股、不替用户做最终决策。

## Typical Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake parse --mode trade --trade-date 20260410 --text "今天低吸了603083，43.2买的，想博弈CPO回流，盘中有点急，感觉还是拿不稳。"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create --ts-code 603083 --direction buy --thesis "回踩 5 日线参与" --logic-tags 龙头首阴,低吸 --buy-zone 42.5-43.0 --stop-loss 40.0 --valid-to 20260415 --with-reference
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log --ts-code 603083 --buy-date 20260410 --buy-price 43.2 --thesis "回踩 5 日线参与" --logic-type-tags 龙头首阴,题材驱动 --pattern-tags 均线回踩 --emotion-notes "盘中略急，但没有追高"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
python .\finance-journal-orchestrator\scripts\run_finance_journal_schedule.py schedule --now 2026-04-10T08:35 --dry-run
```

## Boundaries

- 只做信息服务、纪律提醒、历史统计与行为复盘。
- 账本主线是“计划 -> 执行 -> 回顾 -> 体检 -> 知识库沉淀”。
- 不执行交易、不推荐仓位、不隐式输出买卖建议。
- Tushare 远程抓取失败时，要诚实暴露 data gaps，不伪造数据。
