<div align="center">

# TradeMirrorOS（中文说明）

**一个把交易经验沉淀为长期记忆的本地优先操作层**

**A local-first operating layer for trading memory**

[![ClawHub 已上线](https://img.shields.io/badge/ClawHub-%E5%B7%B2%E4%B8%8A%E7%BA%BF-0ea5e9?style=flat-square)](https://clawhub.ai/topps-2025/trademirroros)
[![本地优先](https://img.shields.io/badge/%E6%9C%AC%E5%9C%B0%E4%BC%98%E5%85%88-Local%20First-111827?style=flat-square)](#产品支柱)
[![聚焦交易记忆](https://img.shields.io/badge/%E8%81%9A%E7%84%A6-%E4%BA%A4%E6%98%93%E8%AE%B0%E5%BF%86-14532d?style=flat-square)](#为什么要做这件事)
[![English](https://img.shields.io/badge/Docs-English-b45309?style=flat-square)](README.md)

[ClawHub 展示页](https://clawhub.ai/topps-2025/trademirroros) · [English README](README.md) · [对外文案](PUBLIC_PAGE_COPY.zh-CN.md) · [项目理念](FRAMEWORK_PURPOSE_AND_VISION.md)

</div>

## 产品概述

TradeMirrorOS 想解决的不是“再做一个交易工具”，而是一个更底层的问题：
如何让计划、执行、复盘、错误、修复路径和有效经验，不再散落在聊天记录与零碎笔记里，而是沉淀为长期可复用的记忆系统。

它更像一个交易认知镜像层，让你看见自己的历史、模式、偏差与进化路径。

## 为什么要做这件事

很多交易系统停留在“记录结果”。
TradeMirrorOS 更关心“保留推理”。

| 没有记忆层时 | 有了 TradeMirrorOS 之后 |
| --- | --- |
| 计划容易淹没在聊天记录里 | 计划会沉淀为结构化、可检索的长期记忆 |
| 复盘常常只是孤立笔记 | 复盘会连接到 scenes、patterns 和 skill cards |
| 错误会因为上下文流失而重复发生 | 错误会持续暴露在后续记录、检索与提醒流程中 |
| 进步更多依赖意志力 | 进步会通过证据驱动的记忆机制逐步复利 |

## 产品支柱

- **记忆先于自动化**：经验必须先变成可检索、可复盘、可复用的资产，自动化才值得被信任。
- **事实先于解释**：先沉淀计划、执行、市场环境与结果，再做更重的归因和结论。
- **本地优先控制**：运行时、数据边界和发布动作始终由用户掌控。
- **人机共同进化**：交易者与智能体围绕同一套证据长期学习，而不是每次都从空 prompt 开始。

## 它提供怎样的产品能力

| 层级 | 作用 |
| --- | --- |
| 记录层 | 以对话优先方式记录计划、交易、复盘、纠错与行为体检 |
| 记忆层 | 用 memory cells、scenes、hyperedges 与 skill cards 组织历史经验 |
| 检索层 | 为未来的记录、提醒与复盘持续提供长周期上下文 |
| 导出层 | 把结构化结果镜像到仓库文档与 vault 产物中 |
| 展示层 | 通过 GitHub 与 ClawHub 形成公开可访问的项目展示面 |

## 适合谁

- 想把交易复盘做成长期系统，而不是一次性笔记的人
- 需要“人 + 智能体”协同工作流，并且依赖长期上下文的人
- 希望运行时和发布边界清晰、坚持本地优先的人
- 希望让交易认知变得可观察、可解释、可持续改进的人

## 它不是什么

- 不是喊单群
- 不是自动执行 Agent
- 不是跟单系统
- 不是通用笔记堆放处

## 已上线 ClawHub

TradeMirrorOS 已经在 ClawHub 上线：

- <https://clawhub.ai/topps-2025/trademirroros>

GitHub 更适合作为公开文档与源码入口。
ClawHub 更适合作为对外展示、分享和快速访问入口。

## 核心模块

| 模块 | 作用 |
| --- | --- |
| [`finance-journal-orchestrator/`](finance-journal-orchestrator) | 编排入口、脚本与记录流程控制 |
| [`trade-plan-assistant/`](trade-plan-assistant) | 计划制定与盘前思考 |
| [`trade-evolution-engine/`](trade-evolution-engine) | 复盘、提醒与自进化输出 |
| [`behavior-health-reporter/`](behavior-health-reporter) | 纪律与行为体检 |
| [`finance_journal_core/`](finance_journal_core) | 运行时存储、检索、记忆与导出层 |
| [`tests/`](tests) | 记录与记忆工作流的验证用例 |

## 延伸阅读

- [`README.md`](README.md)
- [`FRAMEWORK_PURPOSE_AND_VISION.md`](FRAMEWORK_PURPOSE_AND_VISION.md)
- [`TRADE_MEMORY_ARCHITECTURE.md`](TRADE_MEMORY_ARCHITECTURE.md)
- [`IMPLEMENTED_FEATURES.md`](IMPLEMENTED_FEATURES.md)
- [`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md)
- [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md)

## 编码说明

文档文件统一按 UTF-8 与 LF 行尾保存，尽量降低 GitHub、编辑器和同步流程中的中文乱码风险。
