# Git Sync Workflow

更新日期：2026-04-12

这份说明用于解决两个目标：

1. 代码和 skill 配置通过 Git 在本地与云服务器之间同步
2. 运行时账本数据不要因为一次 `git pull / push` 被整体覆盖

## 一、建议的同步边界

建议把仓库内容分成两层：

- **代码层（进 Git）**
  - `finance_journal_core/`
  - `finance-journal-orchestrator/`
  - `tests/`
  - 顶层文档与配置模板
- **运行时账本层（不直接进 Git）**
  - `_runtime*/data/finance_journal.db`
  - `_runtime*/artifacts/`
  - `_runtime*/memory/`
  - `_runtime*/obsidian-vault/`

当前仓库已通过 `.gitignore` 默认忽略 `_runtime*/` 和 SQLite 文件，避免把本地运行时账本直接提交到代码仓库。

## 二、为什么不要直接把账本数据库推到 Git

SQLite 账本是“当前状态快照”，不是天然适合多人双向合并的 append-only 日志。

如果把整库文件直接放进 Git，常见风险包括：

- 本地提交把云端新增记账整体覆盖
- 云端提交把本地补充的会话轨迹整体覆盖
- 二进制冲突无法做细粒度 merge
- 一次误操作就会把整段交易轨迹回退

因此推荐：

- **Git 负责同步代码和协议**
- **账本事实通过结构化导入/导出补回**

## 三、当前可用的安全串联方式

### 1. 口述记账

继续使用：

- `session turn`
- `intake draft-start / draft-reply`
- `trade enrich`

适合在聊天侧持续补充主观轨迹、情绪、失误和经验。

### 2. 标准化交割单导入

当前已支持：

- `trade import-statement --file ...`
- Gateway：`交易 导入 文件=... session=... trade_date=...`

它会优先做“事实对齐”：

- 代码 / 名称
- 买入日期 / 卖出日期
- 买入价格 / 卖出价格
- 数量 / 金额 / 手续费（若文件提供）

对齐完成后，再通过：

- `assistant_message`
- `pending_question`
- `follow_up_queue`
- `session_state.pending_question`

把“选股原因 / 触发信号 / 仓位理由 / 情绪轨迹”留到后续对话慢慢补。

这比直接同步整个 SQLite 更安全，也更适合云端与本地分工。

## 四、推荐协作流程

### 代码更新

1. 本地改代码并测试
2. `git add` / `git commit`
3. 推到远端仓库
4. 云服务器 `git pull --rebase`

### 账本补全

1. 云端会话里先口述记账，或直接上传标准化交割单
2. 本地需要复核时，拉最新代码
3. 再用同一份交割单、补充文本或 Vault 笔记继续 enrich
4. 不直接依赖“覆盖式上传整个 runtime 目录”

## 五、后续建议

如果后面要把“云端新增账本内容”更稳地回流到本地，建议下一步新增两类能力：

1. **结构化导出/导入包**
   - 按交易、计划、回顾导出 JSONL / NDJSON
   - 每条记录带 `entity_id / updated_at / source`
2. **账本合并策略**
   - 以记录级 merge 替代整库覆盖
   - 对 `trade / plan / review / session_thread` 分别制定冲突规则

在这两项能力落地前，最稳妥的策略仍然是：

- 代码走 Git
- 账本事实走口述补充 + 标准化交割单导入
