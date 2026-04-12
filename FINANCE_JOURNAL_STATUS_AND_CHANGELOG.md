# Finance Journal Status and Changelog

Updated: 2026-04-12
Current status version: `0.2.7`

This is the single status document for:

- current product definition
- implemented capabilities
- remaining gaps
- version updates

## Current Product Definition

Finance Journal is currently positioned as:

- a local-first trade journaling framework
- a session-oriented OpenClaw-compatible skill
- a behavior-review and self-improvement loop for traders
- a ledger that preserves both hard facts and subjective decision context

The implementation still ships with A-share-friendly defaults, but the high-level architecture is intended to be reusable across broader markets over time.

## Current Highlights

- statement import now supports fact alignment first and reasoning follow-up later
- session logic can reuse same-day and same-symbol context when safe
- semi-quant strategy context can be stored alongside discretionary notes
- repository-level open source files are in place for Git hosting and collaboration
- public-facing top-level documentation has been shifted to English to make the project more broadly accessible

## Version History

### `0.2.7` | 2026-04-12

Focus: make the repository more globally readable on GitHub and Gitee.

Changes:

- rewrote top-level repository-facing docs in English
- clarified that current market defaults are China-oriented while the architecture is broader
- kept collaboration files and public repo guidance English-first

### `0.2.6` | 2026-04-12

Focus: remove Docker packaging while keeping repository collaboration infrastructure.

Changes:

- removed Docker packaging files and Docker-specific documentation
- kept CI focused on compile and unit test validation

### `0.2.5` | 2026-04-12

Focus: add repository collaboration scaffolding.

Changes:

- added license and public collaboration files
- added issue templates, PR template, CI, and Dependabot configuration

### `0.2.4` | 2026-04-12

Focus: statement fact alignment, session continuation, and Git sync boundaries.

Changes:

- added `trade import-statement`
- added follow-up queues and session pending-question support for imported statements
- documented safe code-vs-ledger sync boundaries

### `0.2.3` | 2026-04-12

Focus: strategy context and polling optimization.

Changes:

- added richer decision-context rendering
- added `shared_context_hints` and `parallel_question_groups`
- improved session reuse behavior for same-day and same-symbol contexts

## Suggested Next Priorities

1. add cleaner multi-market abstractions around identifiers, feeds, and examples
2. improve model-native session understanding beyond heuristic parsing
3. build safer record-level import/export and merge flows across local and cloud runtimes
4. deepen style and trajectory analytics for semi-systematic workflows
