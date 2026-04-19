<div align="center">

# TradeMirrorOS

**A local-first operating layer for trading memory**

**把交易经验沉淀为长期记忆的本地优先操作层**

[![ClawHub Live](https://img.shields.io/badge/ClawHub-Live-0ea5e9?style=flat-square)](https://clawhub.ai/topps-2025/trademirroros)
[![Local First](https://img.shields.io/badge/Local-First-111827?style=flat-square)](#product-pillars)
[![Trading Memory](https://img.shields.io/badge/Focus-Trading%20Memory-14532d?style=flat-square)](#why-it-exists)
[![Bilingual](https://img.shields.io/badge/Docs-English%20%2F%20%E4%B8%AD%E6%96%87-b45309?style=flat-square)](README.zh-CN.md)

[ClawHub](https://clawhub.ai/topps-2025/trademirroros) · [中文说明](README.zh-CN.md) · [Public Copy](PUBLIC_PAGE_COPY.md) · [项目理念](FRAMEWORK_PURPOSE_AND_VISION.md)

</div>

## Hero

TradeMirrorOS turns plans, executions, reviews, mistakes, and recovered edges into durable memory instead of disposable chat context.

It is designed for traders who want a system that remembers how they think, how they drift, how they recover, and how they improve over time.

## Why It Exists

Most trading tools stop at records.
TradeMirrorOS is built to preserve reasoning.

| Without a memory layer | With TradeMirrorOS |
| --- | --- |
| Plans disappear into chat history. | Plans become structured, queryable memory. |
| Reviews are isolated notes. | Reviews connect to scenes, patterns, and reusable skill cards. |
| Mistakes repeat because context fades. | Mistakes stay visible across journaling and recall workflows. |
| Improvement depends on willpower alone. | Improvement compounds through evidence-backed memory. |

## Product Pillars

- **Memory before automation**: experience must become searchable, reviewable, and reusable before automation is worth trusting.
- **Facts before interpretation**: plans, executions, market context, and outcomes settle first; heavy conclusions come later.
- **Local-first control**: runtime, data boundaries, and publishing decisions remain under user control.
- **Human-agent co-evolution**: trader and agent learn from the same evidence instead of restarting from a blank prompt.

## What The Product Surface Looks Like

| Layer | What it does |
| --- | --- |
| Journaling | Captures plans, trades, reviews, corrections, and behavior reports in a conversation-first workflow. |
| Memory | Organizes history into memory cells, scenes, hyperedges, and skill cards. |
| Retrieval | Keeps long-horizon context available for future journaling, reminders, and review loops. |
| Export | Mirrors structured outputs into repo-friendly documentation and vault artifacts. |
| Presentation | Ships publicly on GitHub and is already live on ClawHub. |

## Who It Is For

- traders building a durable review habit instead of a one-off note pile
- human + agent workflows that need long-horizon memory instead of short context windows
- local-first users who want visible boundaries around runtime and publishing
- builders who want trading cognition to become inspectable, not hidden inside intuition

## What It Is Not

- not a signal-selling room
- not an auto-execution agent
- not a copy-trading system
- not a generic note dump

## Live On ClawHub

TradeMirrorOS already has a live public page:

- <https://clawhub.ai/topps-2025/trademirroros>

Use GitHub as the open code and documentation surface.
Use ClawHub as the lightweight public showcase and discovery entry.

## Core Modules

| Module | Purpose |
| --- | --- |
| [`finance-journal-orchestrator/`](finance-journal-orchestrator) | Entry scripts, orchestration, and journaling workflow control |
| [`trade-plan-assistant/`](trade-plan-assistant) | Planning support and pre-trade thinking |
| [`trade-evolution-engine/`](trade-evolution-engine) | Reviews, reminders, and self-evolution outputs |
| [`behavior-health-reporter/`](behavior-health-reporter) | Discipline and behavior diagnostics |
| [`finance_journal_core/`](finance_journal_core) | Runtime storage, retrieval, memory, and export layer |
| [`tests/`](tests) | Validation for journaling and memory workflows |

## Read More

- [`README.zh-CN.md`](README.zh-CN.md)
- [`FRAMEWORK_PURPOSE_AND_VISION.md`](FRAMEWORK_PURPOSE_AND_VISION.md)
- [`TRADE_MEMORY_ARCHITECTURE.md`](TRADE_MEMORY_ARCHITECTURE.md)
- [`IMPLEMENTED_FEATURES.md`](IMPLEMENTED_FEATURES.md)
- [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md)
- [`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md)

## Encoding Note

Documentation files are stored as UTF-8 with LF line endings so Chinese and English content stays stable across GitHub, editors, and sync workflows.
