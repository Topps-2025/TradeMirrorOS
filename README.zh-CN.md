# TradeMirrorOS（中文说明）

[中文](#trademirroros中文说明) | [English README](README.md)

TradeMirrorOS 是一个面向交易记忆的本地优先操作层。

它希望解决的不是“再做一个交易工具”，而是一个更根本的问题：
如何让计划、执行、复盘、错误、修复路径和有效经验，不再散落在聊天记录与零碎笔记里，而是沉淀为可以持续复用的长期记忆。

- ClawHub 展示页（已上线）：<https://clawhub.ai/topps-2025/trademirroros>
- GitHub 仓库：<https://github.com/Topps-2025/TradeMirrorOS>
- 英文 README：[`README.md`](README.md)
- 对外文案：[`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md) / [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md)

## 一句话定位

TradeMirrorOS 面向的是“人 + 智能体”协同的交易工作流。
它不是为了替你交易，而是为了把你的交易过程变成结构化、可检索、可复盘、可复用的记忆系统。

## 项目理念

- **记忆先于自动化**：交易能力的提升，首先来自经验的复利；经验只有被沉淀成可检索、可复盘、可复用的记忆，才真正有价值。
- **事实先于解释**：先记录计划、执行、市场环境与结果，再做更重的归因、评价与结论。
- **本地优先控制**：运行时、数据边界、同步方式和发布动作，默认都由用户自己掌控。
- **人机共同进化**：系统的目标，是让交易者与智能体围绕同一套证据不断学习，而不是只消费一次性的 prompt 输出。

## 它能做什么

- 用对话优先的方式记录计划、交易、复盘、纠错与行为体检
- 用 memory cells、scenes、hyperedges 和 skill cards 组织长期记忆
- 为未来的提醒、复盘、决策支持提供可持续的长期上下文
- 映射真实决策路径，让重复错误、有效 setup、行为偏差和可复用优势逐渐变得清晰

## 为什么这件事重要

很多交易系统只关心“这次赚了还是亏了”。
TradeMirrorOS 更关心的是：
为什么会做这个决定、当时看到了什么、忽略了什么、哪些路径可以保留、哪些错误正在重复。

换句话说，它试图把交易成长从“短期反馈”推进到“长期记忆操作系统”。

## 已上线 ClawHub

TradeMirrorOS 已经在 ClawHub 上线：

- <https://clawhub.ai/topps-2025/trademirroros>

GitHub 仓库更适合作为公开文档、源码与设计说明入口；
ClawHub 页面则更适合作为外部展示、分享和快速访问入口。

## 核心模块

- [`finance-journal-orchestrator/`](finance-journal-orchestrator)：编排入口、脚本与记录流程
- [`trade-plan-assistant/`](trade-plan-assistant)：计划制定与盘前思考
- [`trade-evolution-engine/`](trade-evolution-engine)：复盘、提醒与自进化输出
- [`behavior-health-reporter/`](behavior-health-reporter)：纪律与行为体检
- [`finance_journal_core/`](finance_journal_core)：运行时存储、检索、记忆与导出层
- [`tests/`](tests)：记录与记忆工作流的验证用例

## 延伸阅读

- [`FRAMEWORK_PURPOSE_AND_VISION.md`](FRAMEWORK_PURPOSE_AND_VISION.md)
- [`TRADE_MEMORY_ARCHITECTURE.md`](TRADE_MEMORY_ARCHITECTURE.md)
- [`IMPLEMENTED_FEATURES.md`](IMPLEMENTED_FEATURES.md)
- [`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md)
- [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md)

## 它不是什么

- 不是喊单群
- 不是自动执行 Agent
- 不是跟单系统
- 不是一个通用笔记堆放处

TradeMirrorOS 更像一个交易认知镜像层：
让你看见自己的历史、看见自己的模式、看见自己的偏差，并在更长的时间尺度上持续进化。
