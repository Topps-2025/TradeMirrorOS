# TradeMirrorOS（中文说明）

更新日期：2026-04-18

TradeMirrorOS 是一个面向交易记忆的本地优先操作层。

它会把你的计划、执行、错误、有效路径与复盘循环重新映射回你自己，让这些内容不再淹没在聊天记录里，而是变成可持续保存、可检索、可复用的长期资产。

- 公共仓库：<https://github.com/Topps-2025/TradeMirrorOS.git>
- 英文 README：[`README.md`](README.md)
- 对外介绍文案：[`PUBLIC_PAGE_COPY.zh-CN.md`](PUBLIC_PAGE_COPY.zh-CN.md) / [`PUBLIC_PAGE_COPY.md`](PUBLIC_PAGE_COPY.md)

## 为什么叫 TradeMirrorOS

- `Trade`：它聚焦的是交易行为，而不是通用聊天记忆层。
- `Mirror`：它会把你的历史行为、认知、错误与有效路径重新映射回来。
- `OS`：它扮演的是一个操作层，而不是单点工具。

用更直白的话说，TradeMirrorOS 是一个服务于人机共演化的交易记忆操作系统。

## 它是什么

- 以对话为优先的计划、交易、复盘与纠错记录方式
- 基于 SQLite 和 Markdown 导出的结构化存储
- 由 memory cells、scenes、hyperedges 和 skill cards 组成的长程记忆层
- 会随数据库同步更新的本地知识图谱快照
- 面向 OpenClaw 的日常记录、复盘与召回编排

## 它不是什么

- 不是喊单系统
- 不是自动交易 Agent
- 不只是流水账
- 不是通用笔记堆放区

它是一个服务于交易工作的认知镜像层 + 长程记忆层。

## 运行时目录与仓库镜像快照

最重要的操作区分是：

- 实时运行目录：`_runtime/`
- 适合 Git 同步的镜像快照：仓库根目录下的 `artifacts/` 与 `obsidian-vault/`

实时数据库和实时 Obsidian 导出都生成在 `_runtime/` 下。
仓库根目录的 `artifacts/` 与 `obsidian-vault/` 是镜像快照，用来让 Git 在多台机器之间携带这些结果。

如果 OpenClaw 指向了错误的 `runtime_root`，即便仓库本身已经是最新状态，它仍可能读到旧账本。

## 关键命令

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn --session-key qq:user_a --trade-date 20260410 --text "在回调 setup 买入 603083"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --full --clean
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync-all
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py maintenance self-check
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "vault sync-all"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "maintenance self-check"
```

说明：

- `vault sync-all` 会重建 `_runtime/obsidian-vault`，并把镜像导出同步到仓库根目录的 `obsidian-vault/` 与 `artifacts/`
- `maintenance self-check` 用来确认 OpenClaw / 本地运行环境使用的 `runtime_root` 是否正确

## 推荐的本地同步流程

1. 把交易记录写入或导入 `_runtime/data/finance_journal.db`
2. 运行 `vault sync-all`
3. 提交并推送镜像后的仓库快照
4. 在另一台机器或 OpenClaw 云端环境中运行 `maintenance self-check`

## 当前架构

- `finance-journal-orchestrator/`：面向 OpenClaw 的入口、网关脚本与参考资料
- `trade-plan-assistant/`：计划创建与历史计划参考
- `trade-evolution-engine/`：交易复盘、提醒与自进化输出
- `behavior-health-reporter/`：行为与纪律报告
- `finance_journal_core/`：运行时、存储、记忆、检索与 vault 导出
- `tests/`：用于交易日志与记忆工作流的本地校验

## 公开 / 私有同步策略

- 公共 GitHub（`origin/main`）现在承载的是 TradeMirrorOS 的代码与文档界面。
- 如有需要，私有同步分支仍可继续携带运行时镜像与敏感账本快照。
- `_runtime*`、`*.db` 与券商导出文件默认保持忽略。

## 验证方式

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```
