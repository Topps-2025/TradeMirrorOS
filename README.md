# TradeMirrorOS

[English](#trademirroros) | [简体中文](README.zh-CN.md)

TradeMirrorOS is a local-first operating layer for trading memory.

它是一个面向交易记忆的本地优先操作层。

- Live on ClawHub / 已上线 ClawHub: <https://clawhub.ai/topps-2025/trademirroros>
- GitHub Repo / GitHub 仓库: <https://github.com/Topps-2025/TradeMirrorOS>
- Chinese README / 中文说明: [`README.zh-CN.md`](README.zh-CN.md)
- Public Copy / 对外文案: [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md) / [`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md)

## At a Glance / 一眼看懂

| Topic | English | 中文 |
| --- | --- | --- |
| Positioning | A trading-memory system for human + agent workflows. | 一个服务于人机协同工作流的交易记忆系统。 |
| Core Idea | Turn plans, executions, reviews, mistakes, and recovered edges into durable memory instead of disposable chat context. | 把计划、执行、复盘、错误与修复路径沉淀成可持续复用的长期记忆，而不是一次性的聊天上下文。 |
| Delivery | Local runtime, structured memory, searchable history, and reusable skill cards. | 本地运行时、结构化记忆、可检索历史，以及可复用的 skill cards。 |
| Status | The public project page is already live on ClawHub. | 项目的公开展示页已经在 ClawHub 上线。 |
| Safety | Local-first by default; it does not place trades or auto-push private trading data. | 默认本地优先；不替你下单，也不会自动推送你的私有交易数据。 |

## Project Philosophy / 项目理念

- **Memory before automation**: trading improvement compounds only when experience becomes searchable, reviewable, and reusable. / **记忆先于自动化**：只有当经验可以被检索、复盘和复用时，交易能力才会真正复利。
- **Facts before interpretation**: plans, executions, market context, and outcomes should settle before heavy conclusions are drawn. / **事实先于解释**：先沉淀计划、执行、市场环境与结果，再做高强度判断。
- **Local-first control**: the trader stays in charge of runtime, data boundaries, and publishing decisions. / **本地优先控制**：运行时、数据边界与发布动作始终由交易者掌控。
- **Human-agent co-evolution**: the system is designed to help a trader and an agent learn from the same evidence over time. / **人机共同进化**：让交易者与智能体围绕同一套证据长期学习、共同迭代。

## What You Can Build With It / 你可以如何使用它

- Capture plans, trades, reviews, and behavior reports in a conversation-first workflow. / 用对话优先的方式记录计划、交易、复盘与行为体检。
- Organize memory with cells, scenes, hyperedges, and skill cards instead of flat notes alone. / 不只依赖平铺笔记，而是用 cells、scenes、hyperedges 与 skill cards 组织记忆。
- Keep long-horizon context available for future journaling, review, and reminder workflows. / 为后续记录、复盘和提醒工作流持续提供长期上下文。
- Mirror a trader's real decision path so repeated mistakes and valid edges become visible. / 映射真实决策路径，让重复错误和有效优势都能被看见。

## Live on ClawHub / ClawHub 已上线

TradeMirrorOS already has a live public page on ClawHub:

- <https://clawhub.ai/topps-2025/trademirroros>

Use the GitHub repository as the open documentation and code surface, and use the ClawHub page as the easiest public entry point for discovery and sharing.

把 GitHub 仓库视为公开文档与代码入口，把 ClawHub 页面视为最直接的公开展示与传播入口。

## Core Modules / 核心模块

- [`finance-journal-orchestrator/`](finance-journal-orchestrator): orchestration, entry scripts, and journaling workflow / 编排入口、脚本与记录流程
- [`trade-plan-assistant/`](trade-plan-assistant): planning and pre-trade thinking / 计划制定与盘前思考
- [`trade-evolution-engine/`](trade-evolution-engine): review, reminders, and self-evolution outputs / 复盘、提醒与自进化输出
- [`behavior-health-reporter/`](behavior-health-reporter): discipline and behavior diagnostics / 纪律与行为体检
- [`finance_journal_core/`](finance_journal_core): runtime storage, retrieval, memory, and export layer / 运行时存储、检索、记忆与导出层
- [`tests/`](tests): validation for journaling and memory workflows / 记录与记忆工作流的验证用例

## Read More / 延伸阅读

- [`FRAMEWORK_PURPOSE_AND_VISION.md`](FRAMEWORK_PURPOSE_AND_VISION.md)
- [`TRADE_MEMORY_ARCHITECTURE.md`](TRADE_MEMORY_ARCHITECTURE.md)
- [`IMPLEMENTED_FEATURES.md`](IMPLEMENTED_FEATURES.md)
- [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md)
- [`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md)

## What It Is Not / 它不是什么

- not a signal-selling room / 不是喊单群
- not an auto-execution agent / 不是自动执行 Agent
- not a copy-trading system / 不是跟单系统
- not a generic note dump / 不是通用笔记堆放处

TradeMirrorOS is a mirror for trading cognition and a durable operating layer for evidence-based improvement.

TradeMirrorOS 的目标，是成为交易认知的镜子，以及一个服务于证据驱动成长的长期操作层。
