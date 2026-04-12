# Contributing

Thanks for contributing to Finance Journal.

## Before You Start

Please read:

- `README.md`
- `IMPLEMENTED_FEATURES.md`
- `NOT_IMPLEMENTED_YET.md`
- `GIT_SYNC_WORKFLOW.md`

If your change affects session or integration contracts, also read:

- `finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- `finance-journal-orchestrator/references/data-contracts.md`

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Validate Before Opening a PR

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```

## Contribution Guidelines

- Keep each change focused. Avoid mixing unrelated refactors into one PR.
- Update user-facing docs whenever behavior, contracts, or workflows change.
- Do not commit `_runtime*/`, local SQLite databases, or temporary logs.
- Be explicit about scope, risks, migration concerns, and validation steps.
- Use English in public-facing repository discussions and docs by default.

## Good PR Contents

A clear pull request usually includes:

- background and motivation
- main changes
- validation steps and outputs
- any contract, schema, or workflow impact
