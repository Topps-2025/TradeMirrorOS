---
name: finance-journal
description: Workspace-level routing skill for the Finance Journal framework. Use it when the caller needs the top-level capability map, implementation status, or routing into the more specific sub-skills.
---

# Finance Journal Workspace

## Read First

- `README.md`
- `IMPLEMENTED_FEATURES.md`
- `NOT_IMPLEMENTED_YET.md`
- `finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- `finance-journal-orchestrator/references/openclaw-session-contract.md`

## Route by Intent

- session-based journaling, multi-turn follow-up, ledger apply, vault sync -> `$finance-journal-orchestrator`
- news, announcements, keywords, morning brief inputs -> `$finance-info-monitor`
- plan creation, updates, and reference generation -> `$trade-plan-assistant`
- trade records, post-trade review, self-evolution, style portrait -> `$trade-evolution-engine`
- discipline, frequency, and health reporting -> `$behavior-health-reporter`

## Root Responsibilities

1. decide whether the user is asking about overall framework status or a concrete workflow
2. if it is a framework-level question, summarize implemented and missing capabilities first
3. if it is an execution request, route to the most relevant sub-skill instead of duplicating logic here
4. if the task spans multiple modules, explain the orchestration path clearly

## Boundaries

- this is a trade journaling and review framework, not an execution engine
- information fetchers collect context, not buy or sell instructions
- self-evolution outputs are review aids, not automatic trading rules
