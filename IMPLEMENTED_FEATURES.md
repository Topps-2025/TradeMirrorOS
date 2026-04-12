# Implemented Features

Updated: 2026-04-12

This file summarizes what is already implemented in the current codebase.

## Core Journal System

- local SQLite-backed ledger and runtime storage
- entities for watchlists, keywords, plans, trades, reviews, reports, drafts, and session threads
- JSON and Markdown artifact generation
- Obsidian vault export

## Free-Form Intake and Drafting

- `intake parse`
- `intake apply`
- conservative parsing that avoids misreading six-digit symbols as dates or prices
- missing-field detection and follow-up question generation
- standardized record preview
- reflection prompts for post-fact enrichment
- draft state machine with start, reply, show, apply, list, and cancel flows

## Session Logic

- `session turn`, `session state`, and `session reset`
- per-session draft ownership through `session_key`
- safe reuse of same-day market context
- safe reuse of same-symbol thesis context
- session persistence through `session_threads`
- `shared_context_hints` and `parallel_question_groups` in the polling bundle

## Statement Import

- `trade import-statement`
- CSV and JSON row import
- fact-first alignment of symbol, dates, prices, quantity, amount, and fee fields
- matching against existing trades when possible
- automatic close-out of an existing open trade when the imported facts fit
- follow-up queue and pending question support so the conversation can continue with reasoning and reflection
- gateway support for statement import through a structured command route

## Decision Context and Semi-Quant Support

- persistence of `decision_context_json` on plans and trades
- support for user focus, observed signals, position reason, confidence, stress, emotions, and mistake tags
- nested `strategy_context` for semi-quant workflows
- strategy line, factor set, activation reason, parameter version, portfolio role, and override notes can be stored and rendered
- vault export renders the extended decision context fields

## Planning, Trading, Review, and Analytics

- plan creation and status management
- trade logging and closing
- plan and trade enrichment after initial storage
- post-trade review cycle
- self-evolution reports and reminders
- style portrait generation
- behavior health reporting

## Information Monitoring

- manual event entry
- URL-based news and announcement fetchers
- multiple parser modes, including timeline, list, article, RSS, JSON, and embedded JSON
- morning brief generation
- schedule-aware event polling hooks

## Repository and Collaboration Infrastructure

- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- issue templates, PR template, CI workflow, and Dependabot config
- dependency entry point through `requirements.txt`

## Verified Locally

- `python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests`
- `python -m unittest discover -s tests -v`
