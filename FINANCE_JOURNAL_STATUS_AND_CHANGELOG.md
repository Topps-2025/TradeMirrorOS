# Finance Journal Status and Changelog

Updated: 2026-04-15
Current status version: `0.4.0`

## Current Product Definition

Finance Journal is currently positioned as:
- a local-first trade journaling framework
- a session-oriented OpenClaw-compatible skill
- a long-term memory system for trading decisions
- a memory-to-skill architecture for reusable review knowledge

## Current Highlights

- removed the news / announcement / morning-brief skill layer
- added persistent long-term memory tables and retrieval flow
- added memory query and skill-card solidification commands
- kept bandit as the top-layer prioritization mechanism for self-evolution reminders
- updated the community vision toward linked memories plus reusable skill cards
- added a paper-style architecture note for formal design communication
- added an OpenClaw demo workflow note and a first retrieval benchmark harness

## Version History

### `0.4.0` | 2026-04-15

Focus: shrink to the trading-memory core and adopt an EverOS-inspired memory architecture.

Changes:
- removed `finance-info-monitor` and retired showcase runtimes
- removed public CLI / gateway routes for watchlist, keyword, event, and brief workflows
- added `memory_cells`, `memory_scenes`, `memory_hyperedges`, and `memory_skill_cards`
- added `memory rebuild`, `memory query`, and `memory skillize`
- reworked docs around local hybrid memory retrieval and skill-card solidification
- added `TRADE_MEMORY_SYSTEM_PAPER.md` as a more formal architecture note
- removed legacy news bootstrap tables from the active schema bootstrap

### `0.3.0` | 2026-04-10

Focus: public repository scaffolding and OpenClaw compatibility.

## Suggested Next Priorities

1. add optional embedding providers behind the new memory interface
2. deepen scene compaction and multi-runtime merge logic
3. formalize community-facing memory-card and skill-card provenance
4. connect finer-grained trajectories to the existing bandit layer
