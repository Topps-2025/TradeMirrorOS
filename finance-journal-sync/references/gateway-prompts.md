# Gateway Prompts

## Detect the right workflow and execute

```text
Use $finance-journal-sync. Enter the current finance-journal repo root, read finance-journal-sync/SKILL.md, finance-journal-sync/references/sync-scenarios.md, and finance-journal-sync/references/gateway-prompts.md, then decide whether this is scenario A, B, C, or D. Before executing, summarize the chosen scenario, target remote, target branch, and critical commands. After executing, report self-check, HEAD, trades, and memory_cells.
```

## Pull latest private data to cloud

```text
Use $finance-journal-sync. Treat this as scenario A. Pull the latest origin/private-sync changes into the cloud checkout, run maintenance self-check with --root ./_runtime, and if mirrors are stale, run vault sync-all and self-check again. Report HEAD, runtime_root, mirror_state.in_sync, trades, and memory_cells.
```

## Push cloud journaling snapshot

```text
Use $finance-journal-sync. Treat this as scenario B. Run vault sync-all and maintenance self-check with --root ./_runtime, then stage the private DB and mirrored exports, commit, and push to origin/private-sync. Report commit hash, push result, trades, and memory_cells.
```

## Pull latest private changes onto desktop

```text
Use $finance-journal-sync. Treat this as scenario C. Pull origin/private-sync onto the desktop checkout, run maintenance self-check with --root ./_runtime, and if mirrors are stale, repair them with vault sync-all and rerun self-check. Report HEAD, runtime_root, mirror_state.in_sync, trades, and memory_cells.
```

## Push public framework changes

```text
Use $finance-journal-sync. Treat this as scenario D. First verify the working tree does not include private runtime files or mirrored private exports. If the change is code-only and doc-only, move it onto main and push it to public/main on TradeMirrorOS. If private data is mixed in, stop and explain the split that is required.
```
