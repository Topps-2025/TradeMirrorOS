# OpenClaw 云端同步工作流

更新日期：2026-04-18

本文用于说明 OpenClaw 场景下，Finance Journal / TradeMirrorOS 的同步边界与操作流程。

适用情况：

- 桌面端已经记录完成
- 云端需要拉取最新私有运行时
- 云端通过 OpenClaw 追加了碎片化记录
- 桌面端需要由 OpenClaw 接管同步
- 仅框架代码和公共文档需要推送到公共仓

参考来源：

- `finance-journal-sync/SKILL.md`
- `finance-journal-sync/references/sync-scenarios.md`
- `finance-journal-sync/references/gateway-prompts.md`
- `finance-journal-orchestrator/references/private-sync-handbook.md`
- `finance-journal-orchestrator/references/openclaw-sync-prompts.md`

## 同步边界说明

需要先明确两条同步链路：

### 1. 公共框架 -> `TradeMirrorOS`

包含内容：

- `finance_journal_core/`
- `finance-journal-orchestrator/`
- `tests/`
- 公共 README / prompts / workflow 文档
- 其他不包含私有交易数据的框架文件

目标位置：

- `public/main`
- 仓库：`https://github.com/Topps-2025/TradeMirrorOS`

### 2. 私有运行时 -> `finance-journal-private`

包含内容：

- `_runtime/data/finance_journal.db`
- `_runtime/obsidian-vault/`
- 仓库根目录 `obsidian-vault/`
- 仓库根目录 `artifacts/`
- 任何私有交易、复盘、记忆导出

目标位置：

- `origin/private-sync`
- 仓库：`https://github.com/Topps-2025/finance-journal-private.git`

## 运行时规则

1. 把 `./_runtime` 视为私有运行时的唯一事实来源
2. `vault sync-all` 负责把 runtime 内容镜像到 repo-root
3. `maintenance self-check` 用来核验 runtime / repo-root / runtime_root 是否一致
4. `vault graph` 只负责导出当前图谱，不是恢复命令
5. 私有运行时文件绝不能推到 `TradeMirrorOS`

## OpenClaw 通用入口提示词

如果你希望 OpenClaw 先判断场景再执行，可以直接使用：

```text
使用 $finance-journal-sync，先读取 finance-journal-sync/SKILL.md、finance-journal-sync/references/sync-scenarios.md 与 finance-journal-sync/references/gateway-prompts.md，然后判断当前任务属于哪一种同步场景。执行前先总结目标远端、目标分支和关键命令；执行后汇报 self-check、HEAD、trades、memory_cells。
```

## 场景 A：桌面端已更新，云端拉取最新私有数据

桌面端先执行：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync private runtime snapshot"
git push origin private-sync
```

云端再执行：

```bash
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
```

## 场景 B：云端碎片化记录回推私有仓

```bash
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync cloud journaling snapshot"
git push origin private-sync
```

## 场景 C：桌面端通过 OpenClaw 接管拉取最新私有变更

先拉取：

```powershell
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

如果镜像落后，再补一次：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

## 场景 D：仅框架 / 文档更新推送到 TradeMirrorOS

```powershell
git checkout main
git pull --rebase public main
git cherry-pick <code-only-commit>
git push public main
```

执行前必须确认本次改动不包含：

- `_runtime/data/finance_journal.db`
- `_runtime/obsidian-vault/`
- `obsidian-vault/`
- `artifacts/`

## 每次同步后建议回报的信息

建议至少输出以下内容：

- 当前仓库根目录
- 当前分支
- 当前远端目标
- 当前 HEAD commit hash
- `runtime_root`
- `matches_repo_runtime`
- `mirror_state.in_sync`
- `trades`
- `memory_cells`
