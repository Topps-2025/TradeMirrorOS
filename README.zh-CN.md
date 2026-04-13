# Finance Journal

[English](README.md) | [简体中文](README.zh-CN.md)

Finance Journal 是一个以对话为中心的交易记账、复盘与自我进化框架，适合主观交易者以及半系统化交易者。

它适合这样的工作流：

- 用自然语言记录计划、交易、情绪、错误和经验
- 先落标准化事实，再通过补问补齐主观信息
- 先导入券商交割单，再补选股理由、市场环境和仓位判断
- 导出 Markdown、JSON 产物以及 Obsidian 笔记库
- 把历史交易转化为复盘提示、行为体检和自进化总结

当前实现对中国 A 股工作流更友好，例如默认使用 `ts_code`、Tushare 行情接口与中文资讯适配器；但会话模型、交割单导入、轮询补全和知识库导出架构本身并不限定于单一市场。

## 这个仓库是什么

Finance Journal 主要是：

- 本地优先的交易行为日志系统
- 面向 OpenClaw 风格聊天工作流的 session 化技能
- 自由文本与结构化复盘数据之间的桥梁
- 围绕计划、交易、复盘、纪律分析的个人改进系统

它不是：

- 交易执行系统
- 自动选股器
- 投资建议工具
- 全自动量化平台

## 存储模型

项目使用本地优先的存储结构：

- SQLite 数据库：`_runtime/data/finance_journal.db`
- 每日产物：`_runtime/artifacts/daily/YYYYMMDD/`
- 长期记忆：`_runtime/memory/`
- Markdown 知识库：`_runtime/obsidian-vault/`

## 仓库结构

- `finance-journal-orchestrator/`：主技能入口、CLI 包装、网关脚本与参考文档
- `finance-info-monitor/`：可选的新闻与公告监控技能
- `trade-plan-assistant/`：计划创建与参考生成
- `trade-evolution-engine/`：交易记录、卖后回顾与自进化输出
- `behavior-health-reporter/`：行为与纪律体检报告
- `finance_journal_core/`：共享 Python 核心逻辑
- `tests/`：离线 smoke tests
- `examples/`：示例输入文件，例如交割单行数据

## 快速开始

### 1. 初始化运行时目录

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault init
```

### 2. 解析或落账一段自然语言交易记录

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake parse `
  --mode trade `
  --trade-date 20260410 `
  --text "今天 43.2 买了 603083，想做 CPO 回流，但盘中有点着急。"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake apply `
  --mode plan `
  --trade-date 20260410 `
  --text "计划 42.5-43.0 买 603083，跌破 40 止损，等板块轮动确认。"
```

### 3. 运行基于 session 的多轮记账流程

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn `
  --session-key user_a `
  --trade-date 20260410 `
  --text "我今天买了 603083"
```

这个 session 流程可以：

- 启动草稿
- 持续补全缺失字段
- 在事实足够时自动落账
- 在安全条件下复用同日市场环境或同票主线
- 记录已入库后继续补充计划/交易上下文

### 4. 先导入交割单事实，再补主观原因

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade import-statement `
  --file .\examples\statement_rows.csv `
  --trade-date 20260415 `
  --session-key user_a
```

这个流程支持“事实先行、原因后补”：

- 先对齐代码、日期、价格、数量、金额和费用
- 支持 CSV、JSON，以及券商导出的 `.xls` 文本文件（例如 GBK + 制表符格式）
- 能匹配已有交易，或在交割单给出卖出事实时补全平仓
- 返回 `assistant_message`、`pending_question`、`follow_up_queue` 与 `completeness_backlog`，方便继续补选股逻辑、触发信号、仓位理由与情绪纪律

### 4b. 扫描哪些交割还缺主观字段

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade incomplete `
  --status open `
  --limit 200

python .\finance-journal-orchestrator\scripts\generate_gateway_followups.py `
  --root .\_runtime `
  --status open `
  --format markdown `
  --max-groups 12 `
  --max-singles 12 `
  --output .\_runtime\artifacts\daily\20260413\gateway_followups.md
```

这个补全队列会指出：

- 哪些交易还缺阻塞字段，例如 `thesis`
- 哪些交易还缺主观上下文，例如 `user_focus`、`observed_signals`、`position_reason`、`environment_tags`
- 哪些记录可以按“同日环境”或“同票主线”并行补问
- 当前是否已具备进入自进化分析的最低完整度

### 5. 创建计划、记录交易并同步笔记

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create `
  --ts-code 603083 `
  --direction buy `
  --thesis "回踩 5 日线后的反弹参与" `
  --logic-tags first-pullback,mean-reversion `
  --buy-zone 42.5-43.0 `
  --stop-loss 40.0 `
  --valid-to 20260415

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log `
  --ts-code 603083 `
  --buy-date 20260410 `
  --buy-price 43.2 `
  --thesis "回踩反弹结构" `
  --logic-type-tags first-pullback,theme-driven `
  --pattern-tags moving-average-retest

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
```

## Session 与轮询设计

解析器和补问系统不会把每条消息都变成僵硬的长表单。

当前输出包含：

- `standardized_record`：适合索引与检索的软结构预览
- `polling_bundle`：下一问、缺失字段队列、解析提示、完成度与复用提示
- `reflection_prompts`：落事实之后继续追问复盘与经验的提示

`polling_bundle` 还包含：

- `shared_context_hints`：提示哪些答案可在 `trade_date`、`symbol` 或 `strategy` 维度复用
- `parallel_question_groups`：提示哪些相关问题可合并为一个补问块

这能减少重复轮询，尤其适用于：

- 同一天的市场环境补充
- 同一只票的多次做 T 或重复交易
- 半系统化策略中共用的因子、启用原因与参数版本说明

现在，同样的分组逻辑也通过 `trade incomplete` 和 `import-statement -> completeness_backlog` 暴露出来，方便网关平台并行补问相关交易，而不是逐条机械追问。

## 决策上下文与半量化工作流

记录可以保存 `decision_context_json`，当前支持：

- 用户关注焦点与观察到的信号
- 仓位理由与主观信心
- 压力水平、情绪备注与错误标签
- 市场阶段、环境标签与风险边界
- 面向半量化/量化邻接流程的 `strategy_context`

`strategy_context` 可存储：

- 策略条线
- 策略家族
- 因子列表
- 因子选择理由
- 启用原因
- 参数版本
- 组合角色
- 主观覆盖说明

目标不是把系统包装成全自动交易器，而是保留人在因子选择、策略启用和临场调整中的主观层。

## 信息监控

可选的信息监控层可以：

- 添加手动事件
- 根据配置的 URL 适配器抓取事件
- 生成晨报
- 支持时间线页面、列表页、文章页、RSS、JSON feed 以及嵌入式 JSON 页面

当前默认适配器仍偏向中国市场，但整体结构是基于适配器的，并非硬编码到某个站点。

## 开源协作文件

仓库包含公开协作常见文件：

- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `.github/ISSUE_TEMPLATE/`
- `.github/pull_request_template.md`
- `.github/workflows/ci.yml`
- `.github/dependabot.yml`

## 校验

当前本地校验命令：

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```

## 其他文档

- 已实现能力：`IMPLEMENTED_FEATURES.md`
- 已知缺口与后续项：`NOT_IMPLEMENTED_YET.md`
- 统一状态与变更记录：`FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`
- 框架愿景：`FRAMEWORK_PURPOSE_AND_VISION.md`
- 社区方向：`COMMUNITY_AGENT_LEDGER_VISION.md`
- Git 同步说明：`GIT_SYNC_WORKFLOW.md`

## 备注

- 启用市场数据时，会从 `TUSHARE_TOKEN` 或 `TS_TOKEN` 读取 token。
- 如果当前环境无法联网，可以传 `--disable-market-data` 以离线运行。
- 示例仍以 A 股标识符为主，因为它们与现有适配器和测试数据匹配。
- 框架聚焦于记账、复盘和行为改进，而不是交易执行。
