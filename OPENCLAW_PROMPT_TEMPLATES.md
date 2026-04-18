# OpenClaw Prompt Templates

更新日期：2026-04-18

下面整理的是给 OpenClaw 使用的现成提示词模板。

参考来源：

- `finance-journal-sync/SKILL.md`
- `finance-journal-sync/references/sync-scenarios.md`
- `finance-journal-sync/references/gateway-prompts.md`
- `finance-journal-orchestrator/references/private-sync-handbook.md`
- `finance-journal-orchestrator/references/openclaw-sync-prompts.md`

## 1. 先判断属于哪一种同步场景

```text
进入当前 finance-journal 仓库根目录，先读取 finance-journal-sync/SKILL.md、finance-journal-sync/references/sync-scenarios.md、finance-journal-sync/references/gateway-prompts.md、finance-journal-orchestrator/references/private-sync-handbook.md、finance-journal-orchestrator/references/openclaw-sync-prompts.md，再判断当前任务属于哪一种场景：A. 桌面端已更新，云端需要拉取最新私有运行时；B. 云端碎片化记录需要回推到私有仓；C. 桌面端需要通过 OpenClaw 接管拉取最新私有变更；D. 仅框架 / 文档更新需要推送到 TradeMirrorOS 公共仓。执行前先概述目标分支、目标远端与关键命令；执行后汇报 self-check 结果，以及 trades / memory_cells 的数量。
```

## 2. 云端拉取最新私有数据

```text
使用 $finance-journal-sync，把当前任务视为场景 A：从 origin/private-sync 拉取最新私有数据到云端工作区，并对 --root ./_runtime 运行 maintenance self-check。若 runtime 与 repo-root 镜像不同步，则执行 vault sync-all 后再次 self-check。最后汇报 HEAD、runtime_root、mirror_state.in_sync、trades、memory_cells。
```

## 3. 云端回推碎片化日志

```text
使用 $finance-journal-sync，把当前任务视为场景 B：先执行 vault sync-all 与 maintenance self-check，然后暂存私有 DB 与镜像导出结果，提交并 push 到 origin/private-sync。最后汇报 commit hash、push 结果、trades、memory_cells。
```

## 4. 桌面端通过 OpenClaw 拉取最新私有变更

```text
使用 $finance-journal-sync，把当前任务视为场景 C：从 origin/private-sync 拉取最新内容到桌面工作区，并对 --root ./_runtime 运行 maintenance self-check。若镜像落后，则执行 vault sync-all 并再次 self-check。最后汇报 HEAD、runtime_root、mirror_state.in_sync、trades、memory_cells。
```

## 5. 只推送框架更新到 TradeMirrorOS

```text
使用 $finance-journal-sync，把当前任务视为场景 D：先确认工作树中不包含私有 runtime 文件或私有镜像导出。如果变更仅涉及代码与公共文档，则将变更整理到 main 并推送到 TradeMirrorOS 的 public/main；如果混入私有数据，则停止执行并说明需要如何拆分提交。
```

## 6. 英文版模板

```text
Use $finance-journal-sync. Enter the current finance-journal repo root, read finance-journal-sync/SKILL.md, finance-journal-sync/references/sync-scenarios.md, and finance-journal-sync/references/gateway-prompts.md first, then decide whether this task is: (A) pull latest private runtime data from origin/private-sync to cloud, (B) push fragmented cloud journaling back to origin/private-sync, (C) pull the latest private changes onto the desktop through OpenClaw takeover, or (D) push code-only framework updates to public/main on TradeMirrorOS. Treat ./_runtime as the private runtime source of truth, run maintenance self-check before and after important sync steps, and never push private runtime files to the public remote.
```
