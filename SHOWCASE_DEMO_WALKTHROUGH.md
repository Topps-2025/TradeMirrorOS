# Showcase Demo Walkthrough

The repository includes a showcase generator that creates a realistic-looking demo runtime for product walkthroughs.

## Goal

The showcase is meant to demonstrate:

- plans
- trades
- reviews
- health reports
- morning briefs
- self-evolution outputs
- vault exports

without requiring a fully populated real account history.

## Important Boundary

The showcase uses a hybrid approach:

- market prices and event flows can be grounded in real data
- reasons, reflections, and some behavioral text may still be synthetic demonstration content

That makes it useful for demos, but it should not be confused with a full real-money journal.

## Typical Flow

```powershell
python .\inance-journal-orchestrator\scripts\generate_showcase_demo.py `
  --root .\_runtime_showcase_202602_202604 `
  --start-date 20260203 `
  --end-date 20260410 `
  --brief-date 20260411 `
  --max-trades 14
```

## What It Produces

A successful demo build can generate:

- sample plans and trades
- post-trade reviews
- health reports
- daily notes
- self-evolution and style-portrait artifacts
- vault-ready Markdown pages

## Recommended Usage

Use the showcase when you need:

- a product walkthrough
- a demo dataset for UI or agent integration
- an example runtime for testing export flows

Do not present showcase text as a fully faithful historical ledger.
