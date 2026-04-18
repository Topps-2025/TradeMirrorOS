---
name: finance-journal-orchestrator
description: OpenClaw-facing orchestration skill for conversation-first trade journaling, statement import, long-term memory retrieval, self-evolution reminders, markdown vault sync, and private/public repo synchronization between local desktop and cloud runtime. Use it when OpenClaw needs to pull updates from the private finance-journal repo, push fragmented cloud journaling back to the private repo, trigger local machine pull-through updates, or follow the TradeMirrorOS public-vs-private sync policy.
---

# Finance Journal Orchestrator

## Read First

- `../FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`
- `../TRADE_MEMORY_ARCHITECTURE.md`
- `references/data-contracts.md`
- `references/openclaw-skill-functional-spec.md`
- `references/openclaw-session-contract.md`
- `references/command-cheatsheet.md`
- `references/intake-workflow.md`
- `references/private-sync-handbook.md` when the task involves pull / push / sync / update / OpenClaw gateway / cloud-vs-local runtime alignment
- `references/openclaw-sync-prompts.md` when the user wants ready-to-paste gateway prompts or an auto-execution instruction block

## Default Workflow

- initialize runtime -> `scripts/init_finance_journal.py`
- structured CLI -> `scripts/finance_journal_cli.py`
- OpenClaw / QQ / Feishu gateway -> `scripts/finance_journal_gateway.py`
- session agent entry -> `scripts/finance_journal_session_agent.py`
- scheduler entry -> `scripts/run_finance_journal_schedule.py`

## Route by Task

- plan creation / update / historical reference -> `$trade-plan-assistant`
- trade log / statement import / post-trade review / evolution reminder -> `$trade-evolution-engine`
- behavior health report -> `$behavior-health-reporter`
- vault export and dashboard -> stay in this skill
- long-term memory rebuild / query / skillize -> stay in this skill
- private repo pull / push, cloud-to-local sync, local-to-cloud sync, and public-vs-private repo routing -> `$finance-journal-sync`

## Output Discipline

1. write SQLite first, then JSON / Markdown artifacts
2. sync to vault if enabled
3. make memory retrieval provenance explicit
4. make it clear which reminders come from history and which are just structured summaries
5. never output auto-trading instructions
6. for sync tasks, run `maintenance self-check` before and after important pull / push operations
7. treat `./_runtime` as the runtime source of truth for private data, and never push private runtime files to the public TradeMirrorOS remote

## Sync Policy

1. private runtime data belongs on `origin/private-sync` in `finance-journal-private`
2. public framework code and generic docs belong on `public/main` in TradeMirrorOS
3. if the request mixes code changes and private data sync, split the work into separate commits and separate pushes
4. prefer `python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime ...` for all OpenClaw-side runtime operations
5. never treat `vault graph` as a restore command; it only mirrors the current database state

## Boundaries

- this is a journaling and long-term memory orchestrator
- it does not fetch market news or morning briefs anymore
- skill cards are reusable review knowledge, not execution policies
