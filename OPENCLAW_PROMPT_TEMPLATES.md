# OpenClaw Prompt Templates

更新日期：2026-04-18

这些模板是给 OpenClaw 网关直接粘贴使用的。

它们的目标是让 OpenClaw：

1. 自动识别应该读哪份同步手册
2. 判断这次是“私有数据同步”还是“公共框架更新”
3. 严格按手册执行 pull / push / self-check / vault sync-all

优先参考：

- `finance-journal-orchestrator/references/private-sync-handbook.md`
- `finance-journal-orchestrator/references/openclaw-sync-prompts.md`

## 1. 自动检测同步手册并执行

```text
进入当前 finance-journal 仓库根目录。先读取 finance-journal-orchestrator/SKILL.md、finance-journal-orchestrator/references/private-sync-handbook.md、finance-journal-orchestrator/references/openclaw-sync-prompts.md。根据用户请求自动判断这是以下哪种场景：A. 本地已更新，云端需要从私有仓拉取；B. 云端碎片化记账后需要推回私有仓；C. 云端已推送，需要接管电脑自动拉取；D. 核心代码框架更新，需要推送到 TradeMirrorOS。执行前先报告你识别出的场景、目标远端、目标分支和将要运行的关键命令；执行后汇报 self-check 与 trades / memory_cells 数量。
```

## 2. 云端从私有仓拉取最新账本

```text
进入 finance-journal 私有仓库根目录，读取 finance-journal-orchestrator/references/private-sync-handbook.md。把这次任务视为“场景 A：本地已更新，云端需要拉到最新私有数据”。执行 git fetch origin private-sync、git checkout private-sync、git pull --rebase origin private-sync，然后执行 python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check。若 self-check 显示 repo-root 镜像与 runtime 不一致，再执行 vault sync-all 并重跑 self-check。最后报告当前 HEAD、runtime_root、mirror_state.in_sync、trades、memory_cells。
```

## 3. 云端碎片化记账后推回私有仓

```text
进入 finance-journal 私有仓库根目录，读取 finance-journal-orchestrator/references/private-sync-handbook.md。把这次任务视为“场景 B：云端碎片化记账后推回私有仓”。先执行 python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all，再执行 maintenance self-check。确认状态 ok 后，执行 git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault，并执行 git add obsidian-vault artifacts，提交并 git push origin private-sync。最后汇报 commit hash、push 结果、trades、memory_cells。
```

## 4. 接管电脑自动拉取私有仓更新

```text
进入电脑本地的 finance-journal 私有仓库根目录，读取 finance-journal-orchestrator/references/private-sync-handbook.md。把这次任务视为“场景 C：云端已推送，需要电脑自动拉取”。执行 git fetch origin private-sync、git checkout private-sync、git pull --rebase origin private-sync，然后执行 python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check。若镜像不同步，再补跑 vault sync-all 与 self-check。最后报告当前 HEAD、runtime_root、mirror_state.in_sync、trades、memory_cells。
```

## 5. 代码框架更新推送到 TradeMirrorOS

```text
进入当前 finance-journal 仓库根目录，读取 finance-journal-orchestrator/references/private-sync-handbook.md。把这次任务视为“场景 D：核心代码框架更新”。先检查待提交文件是否包含 _runtime/data/finance_journal.db、_runtime/obsidian-vault、obsidian-vault、artifacts；如果包含，这不是纯公共框架提交，需要提醒拆分。若只包含代码与通用文档，则切到 main，拉取 public/main，把 code-only 提交推送到 TradeMirrorOS。最后报告是否为纯公共提交、推送到哪个远端、当前 HEAD。
```

## 6. 一次性安全同步模板

```text
进入当前 finance-journal 仓库根目录。先读取 finance-journal-orchestrator/references/private-sync-handbook.md，再执行 git status --short --branch 和 git remote -v。根据工作树内容判断这次是否涉及私人数据；如果涉及账本、vault、artifacts，则一律按私有仓 private-sync 工作流执行；如果只涉及代码与通用文档，则按 TradeMirrorOS public/main 工作流执行；如果混合，停止并明确拆分方案。整个过程中，把 ./_runtime 视为私有运行时真源，所有重要步骤前后都执行 self-check。
```

## 7. 英文版总提示

```text
Enter the current finance-journal repo root. Read finance-journal-orchestrator/SKILL.md, finance-journal-orchestrator/references/private-sync-handbook.md, and finance-journal-orchestrator/references/openclaw-sync-prompts.md first. Decide whether this task is: (A) pull latest private runtime data from origin/private-sync to cloud, (B) push fragmented cloud journaling back to origin/private-sync, (C) pull the latest private changes onto the desktop through OpenClaw takeover, or (D) push code-only framework updates to public/main on TradeMirrorOS. Treat ./_runtime as the private runtime source of truth, run maintenance self-check before and after important sync steps, and never push private runtime files to the public remote.
```
