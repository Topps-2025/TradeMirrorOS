# OpenClaw 云端同步工作流

更新日期：2026-04-18

这份文档是 OpenClaw 网关与本地电脑协同使用 Finance Journal / TradeMirrorOS 时的正式操作手册。

如果任务涉及：

- 云服务器从私有仓拉取最新账本
- 云服务器把碎片化记账结果推回私有仓
- 电脑批量导入交割单后，让 OpenClaw 云端拿到最新数据
- 电脑不在手边时，通过 OpenClaw 接管电脑完成拉取
- 区分“公共框架更新”与“私人数据同步”

优先阅读：

- `finance-journal-orchestrator/references/private-sync-handbook.md`
- `finance-journal-orchestrator/references/openclaw-sync-prompts.md`

## 一、仓库职责分离

必须始终区分两类更新：

### 1. 公共框架更新 -> `TradeMirrorOS`

适用于：

- `finance_journal_core/`
- `finance-journal-orchestrator/`
- `tests/`
- 通用 README / 文档 / workflow
- 不包含私人交易数据的技能与提示词

目标远端：

- `public/main`
- 仓库：`https://github.com/Topps-2025/TradeMirrorOS`

### 2. 私人数据同步 -> `finance-journal-private`

适用于：

- `_runtime/data/finance_journal.db`
- `_runtime/obsidian-vault/`
- repo-root `obsidian-vault/`
- repo-root `artifacts/`
- 任何带有私人交易内容的导出物

目标远端：

- `origin/private-sync`
- 仓库：`https://github.com/Topps-2025/finance-journal-private.git`

## 二、最重要的原则

1. `./_runtime` 是私有运行时真源
2. `vault sync-all` 用于从 runtime 重建并镜像到 repo-root
3. `maintenance self-check` 用于核对 runtime / repo-root / runtime_root 是否一致
4. `vault graph` 不是恢复命令，只是把当前数据库状态导出成图谱
5. 私人数据不要推到 `TradeMirrorOS`

## 三、场景 A：电脑本地已更新，云端需要拉到最新私有数据

典型场景：

- 电脑批量导入交割单
- 本地修复数据库
- 本地更新了私有 vault 镜像

### 电脑本地先做

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync private runtime snapshot"
git push origin private-sync
```

### OpenClaw 云端再做

```bash
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
```

如果 `self-check` 报 repo-root 镜像不一致，再执行：

```bash
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
```

## 四、场景 B：电脑不在手边，云端碎片化记账后推回私有仓

典型场景：

- 在 OpenClaw 网关里补记一笔交易
- 云端补充 review / memory / vault 导出
- 希望稍后本地电脑自动拉到同一份账本

### OpenClaw 云端执行

```bash
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data vault sync-all
python ./finance-journal-orchestrator/scripts/finance_journal_cli.py --root ./_runtime --disable-market-data maintenance self-check
git add -f _runtime/data/finance_journal.db _runtime/obsidian-vault
git add obsidian-vault artifacts
git commit -m "chore: sync cloud journaling snapshot"
git push origin private-sync
```

## 五、场景 C：云端推完后，让 OpenClaw 接管电脑自动拉取

当电脑在线且可被 OpenClaw 接管时，在电脑对应的 OpenClaw 执行环境中运行：

```powershell
git fetch origin private-sync
git checkout private-sync
git pull --rebase origin private-sync
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

若镜像不一致，再补：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime --disable-market-data maintenance self-check
```

## 六、场景 D：核心代码框架更新，推送到 TradeMirrorOS

适用于：

- 核心代码逻辑
- 通用提示词
- 不含私人数据的 skills / docs

推荐流程：

1. 在本地完成代码改动
2. 确认提交里不包含 `_runtime/data/finance_journal.db`、`_runtime/obsidian-vault/`、`obsidian-vault/`、`artifacts/`
3. 切到公共分支并推送到 TradeMirrorOS

示例：

```powershell
git checkout main
git pull --rebase public main
git cherry-pick <code-only-commit>
git push public main
```

如果某次改动既包含框架又包含私人数据：

- 把框架改动和数据同步拆成两个提交
- 框架提交推到 `public/main`
- 私人数据提交推到 `origin/private-sync`

## 七、OpenClaw 实际执行时的判断顺序

遇到更新 / 同步请求时，先判断：

1. 这次是“私人数据同步”还是“公共框架更新”？
2. 如果涉及账本、数据库、vault、artifacts，一律走私有仓
3. 如果只涉及代码与通用文档，一律走 TradeMirrorOS
4. 如果混合，拆分提交、拆分 push

## 八、标准检查项

每次拉取或推送后，至少汇报：

- 当前仓库根目录
- 当前分支
- 当前远端
- `runtime_root`
- `matches_repo_runtime`
- `mirror_state.in_sync`
- `trades`
- `memory_cells`
- 当前 HEAD commit hash

## 九、给 OpenClaw 的一句话版总原则

```text
把 ./_runtime 视为私有运行时真源；私人数据只走 origin/private-sync，公共框架只走 public/main；所有重要同步动作前后都跑 --root ./_runtime maintenance self-check，必要时补跑 vault sync-all。
```
