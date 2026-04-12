---
name: finance-journal
description: OpenClaw workspace 级总入口 skill。用于让 Control UI 在仓库根目录识别这套交易行为复盘记账框架，并把请求路由到子 skill（`finance-journal-orchestrator`、`finance-info-monitor`、`trade-plan-assistant`、`trade-evolution-engine`、`behavior-health-reporter`）；也适用于先判断框架已实现/未实现能力、再决定该调用哪个子模块时使用。
---

# Finance Journal Workspace

## Read First

- `README.md`
- `IMPLEMENTED_FEATURES.md`
- `NOT_IMPLEMENTED_YET.md`
- `finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- `finance-journal-orchestrator/references/openclaw-session-contract.md`

## Route by Intent

- 会话级记账、多轮补问、落账、知识库同步 -> 用 `$finance-journal-orchestrator`
- 新闻 / 公告 / 关键词 / 晨报抓取 -> 用 `$finance-info-monitor`
- 交易计划创建、更新、参考样本 -> 用 `$trade-plan-assistant`
- 交易记录、卖出后回顾、自进化、轨迹画像 -> 用 `$trade-evolution-engine`
- 行为体检、纪律与频率报告 -> 用 `$behavior-health-reporter`

## Root Responsibilities

1. 先判断用户是在问“框架状态 / 总体能力 / 集成方式”，还是在做具体业务动作。
2. 如果是总体问题，优先汇总顶层文档里的已实现 / 未实现状态，再给出下一步路由。
3. 如果是具体动作，直接把任务转给最匹配的子 skill，不要在根 skill 里重复实现子模块逻辑。
4. 如果任务跨模块，例如“先抓新闻，再写晨报，再结合自进化提醒”，就由根 skill 做编排说明。

## Control UI Notes

- 这个根 skill 的作用是让 OpenClaw Control UI 在仓库根目录直接识别整个工作区。
- 真正执行时，优先复用子目录里的 `SKILL.md` 与脚本入口，不要把所有规则堆回根目录。
- 当 UI 只展示一个入口时，默认从本 skill 开始，再向下路由到子 skill。

## Boundaries

- 这是交易行为复盘账本与辅助信息框架，不是荐股或自动交易系统。
- 允许用 URL 抓取新闻 / 公告，但抓到的是信息事件，不是买卖指令。
- 自进化输出只做历史路径复用与风险识别，不直接产出自动下单规则。
