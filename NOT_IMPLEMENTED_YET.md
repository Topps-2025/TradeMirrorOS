# Not Implemented Yet

Updated: 2026-04-12

This file lists important gaps that are still intentionally open.

## Large-Model-Native Conversation Management

The project already supports heuristic parsing, draft persistence, and follow-up metadata, but it does not yet provide:

- a fully model-native multi-turn slot-filling agent
- robust correction handling for "I meant the previous field, not this one"
- adaptive follow-up ordering based on user behavior history
- automatic in-session batching of related questions without caller orchestration
- cross-device context restore and merge logic

## Broader Market Generalization

The architecture is reusable, but the current implementation still defaults to market assumptions that are convenient for China A-share workflows, such as:

- `ts_code`
- Tushare-oriented integrations
- Chinese-language examples and presets in deeper workflow references

Future work could add cleaner market adapters for broader international usage.

## Deeper Style and Trajectory Modeling

The project does not yet provide:

- long-horizon versioned style evolution tracking
- more robust regime-switch detection
- trajectory similarity search beyond tag overlap
- dedicated analytics split by strategy line, factor family, and parameter version
- fine-grained contextual bandit or RL-style online updating

## Data and Execution Layer

Not implemented yet:

- broker API synchronization
- account-level portfolio and cash tracking
- tick-by-tick replay
- chart or screenshot archiving
- execution automation
- robust record-level merge tooling across multiple runtime databases

## Community Layer

Not implemented yet:

- shared community ledger assets
- anonymized cross-user learning cards
- moderation and provenance layers for public strategy knowledge bases

## Why These Gaps Exist

The project has deliberately prioritized:

1. making journaling easier
2. making review more truthful and less templated
3. building a minimal loop from raw trade notes to reflection and discipline reports
4. keeping the system honest about what is fact, what is interpretation, and what is still missing
