---
name: finance-journal
description: Workspace-level routing skill for the Finance Journal framework. Use it for the top-level capability map, memory architecture, private/public repo sync policy, OpenClaw gateway pull/push workflows, and routing into the journaling sub-skills.
---

# Finance Journal Workspace

## Read First

- `README.md`
- `TRADE_MEMORY_ARCHITECTURE.md`
- `IMPLEMENTED_FEATURES.md`
- `NOT_IMPLEMENTED_YET.md`
- `finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- `finance-journal-orchestrator/references/openclaw-session-contract.md`

## Route by Intent

- session journaling, draft continuation, statement import, vault sync, private repo pull/push, OpenClaw cloud sync -> `$finance-journal-orchestrator`
- plan creation, updates, and reference generation -> `$trade-plan-assistant`
- trade logs, post-trade review, self-evolution, style portrait -> `$trade-evolution-engine`
- discipline and health reporting -> `$behavior-health-reporter`

## Root Responsibilities

1. explain the memory-centric framework boundary
2. route execution requests to the right sub-skill
3. clarify how memory retrieval and bandit reranking fit together
4. point users to the community vision when they ask about shared memories or skills

## Boundaries

- this is a trade journaling and long-term memory framework, not an execution engine
- self-evolution outputs are review aids, not automatic trading rules
- community-facing skill cards are reusable experience layers, not copy-trading signals
