# OpenClaw Sync Prompts

Use these prompts when OpenClaw needs a ready-to-run instruction block.

## Detect The Correct Handbook And Execute

```text
Enter the current finance-journal repo root. Read finance-journal-orchestrator/SKILL.md, finance-journal-orchestrator/references/private-sync-handbook.md, and finance-journal-orchestrator/references/openclaw-sync-prompts.md first. Identify whether this task is: (A) desktop already updated and cloud needs to pull from origin/private-sync, (B) cloud fragment journaling needs to push back to origin/private-sync, (C) desktop needs to pull the latest private changes through OpenClaw takeover, or (D) code-only framework changes should go to public/main on TradeMirrorOS. Before executing, summarize the scenario, target remote, target branch, and critical commands. After executing, report self-check, HEAD, trades, and memory_cells.
```

## Pull Latest Private Runtime To Cloud

```text
Enter the finance-journal private repo root. Treat this as scenario A from private-sync-handbook.md. Pull the latest private-sync branch from origin, run maintenance self-check against ./_runtime, and if runtime mirrors are stale, run vault sync-all and self-check again. Report HEAD, runtime_root, mirror_state.in_sync, trades, and memory_cells.
```

## Push Cloud Journaling Snapshot To Private Repo

```text
Enter the finance-journal private repo root. Treat this as scenario B from private-sync-handbook.md. Run vault sync-all and maintenance self-check with --root ./_runtime, then stage the private DB and mirrored vault exports, commit, and push to origin/private-sync. Report commit hash, push result, trades, and memory_cells.
```

## Pull Latest Private Changes Onto Desktop

```text
Enter the desktop finance-journal private repo root. Treat this as scenario C from private-sync-handbook.md. Pull origin/private-sync onto the desktop checkout, run maintenance self-check with --root ./_runtime, and if mirrors are stale, repair them with vault sync-all and rerun self-check. Report HEAD, runtime_root, mirror_state.in_sync, trades, and memory_cells.
```

## Push Public Framework Changes

```text
Enter the current finance-journal repo root. Treat this as scenario D from private-sync-handbook.md. First verify the working tree does not include private runtime files or mirrored private exports. If the change is code-only and doc-only, move the change onto main and push it to public/main on TradeMirrorOS. If private data is mixed in, stop and explain the split that is required.
```
