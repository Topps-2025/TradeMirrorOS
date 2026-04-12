# Finance Journal 状态与更新记录

更新日期：2026-04-12
当前状态版本：`0.2.5`

这是一份统一文档，用来同时记录：

- 当前已实现功能
- 当前未实现功能
- 版本更新记录
- 接下来最值得优先推进的方向

## 一、当前产品定位

当前这套框架首先是：

- 基于 OpenClaw 的交易行为复盘记账本
- 面向主观 / 半量化交易者的个人认知沉淀工具
- 开始支持量化 / 半量化策略的人为启停、因子选择与策略条线上下文记账
- 支持本地 SQLite + JSON / Markdown + Obsidian 的长期记忆系统
- 以会话级交互为主的 skill，适合挂到 OpenClaw、QQ、飞书等聊天平台
- 允许在云端仅靠 URL 轮询新闻 / 公告 / 快讯的辅助信息层

当前不是：

- 自动交易系统
- 荐股系统
- 替人决策的投资顾问
- 纯量化策略执行平台
- 自称知道“客观市场真相”的上帝视角监控器

## 二、当前已实现功能

### 1. 账本底座与存储层

已实现：

- 本地 SQLite 数据库
- 计划、交易、回顾、体检、信息事件、草稿、会话线程持久化
- JSON / Markdown artifact 输出
- Obsidian 知识库导出
- 会话状态与最近聚焦实体持久化

### 2. 用户视角快照与自由文本解析

已实现：

- `intake parse`
- `intake apply`
- 非标准化中文语句解析
- 从自然语言中提取基础事实字段
- 输出软结构化结果：
  - `standardized_record`
  - `polling_bundle`
  - `reflection_prompts`
- 计划 / 交易持久化 `decision_context_json`
- 用户视角快照字段：
  - `user_focus`
  - `observed_signals`
  - `position_reason`
  - `position_confidence`
  - `stress_level`
- `decision_context_json` 扩展字段：
  - `interpretation`
  - `market_stage / environment_tags`
  - `position_size_pct / risk_boundary / planned_zone`
  - `emotion_notes / mistake_tags / source_notes`
- 对量化 / 半量化记录，支持在 `decision_context_json.strategy_context` 中保存：
  - 策略条线 / 策略家族
  - 核心因子 / 因子选择理由
  - 启用原因 / 参数版本
  - 组合角色 / 主观覆盖说明
- 四轴轮询补问：
  - 选股关注
  - 择时触发
  - 仓位边界
  - 情绪纪律

### 3. 多轮补问与会话状态机

已实现：

- 草稿级状态机：`intake draft-start / draft-reply / draft-apply`
- OpenClaw 会话级状态机：`session turn / state / reset`
- `finance_journal_session_agent.py`
- `session_threads` 会话持久化
- `polling_bundle.shared_context_hints`
- `polling_bundle.parallel_question_groups`
- 交割单导入后的 follow-up 问题回挂到 `session_state.pending_question`

当前已支持按 `session_key` 自动判断：

- 新建草稿
- 继续补草稿
- 自动落账
- 对最近计划 / 交易做二次沉淀
- 查询当前会话状态
- 清空会话重新开始
- 给上层提示哪些问题可以按 `trade_date / symbol / strategy` 范围复用或并行补问

### 4. 计划、交易、自进化与体检

已实现：

- `plan create`
- `trade log`
- `trade import-statement`
- `trade close`
- `plan enrich`
- `trade enrich`
- `evolution report`
- `evolution remind`
- `evolution portrait`
- `review run`
- `report health`

当前已能输出：

- 优质路径
- 可复用基因
- 风险基因
- 复核清单
- 反思追问
- 基础风格画像
- 行为体检报告

### 5. 新闻 / 公告 / 晨报辅助链路

已实现：

- `event add`
- `event fetch-url`
- `event fetch`
- `brief generate`
- URL-only 新闻源适配
- JSONP feed 解析
- JS 赋值对象 feed 解析
- 晨报前轮询配置：
  - `schedules.event_fetch_times`
  - `schedules.fetch_events_before_morning_brief`

当前已在本地配置中启用：

- `wallstreetcn-live-global`
- `cls-telegraph`
- `jin10-home-flash`
- `eastmoney-kuaixun`
- `10jqka-realtime-news`

### 6. 展示链路

已实现：

- `generate_showcase_demo.py`
- 2026 年 2 月起的展示用计划 / 交易 / 回顾 / 体检 / 晨报样例生成
- 展示样例带真实行情价格与真实新闻事件
- 展示样例同步带 `decision_context`，便于从记账一路展示到自进化与体检

## 三、当前未实现功能

### 1. 真正的大模型多轮代理

当前仍是启发式 + 状态机混合。

还未实现：

- 纯大模型驱动的多轮意图识别
- 更稳的槽位理解与上下文修正
- 自动理解“这句话是在修正上一轮哪个字段”
- 自适应提问顺序
- 更强的歧义消解
- 会话内真正自动复用“同日环境 / 同票做T / 同策略条线”答案

### 2. 更完整的平台无感接入

还未实现：

- OpenClaw 网关自动无感注入 `session_key`
- QQ / 飞书平台侧的标准适配层脚本
- 用户身份、群聊身份、跨设备上下文自动恢复
- 平台消息格式到 skill 参数的正式桥接层

### 3. 更深的风格建模与轨迹复用

当前已有基础风格画像与 bandit 排序，但还未实现：

- 风格画像版本化
- 不同市场阶段下的风格切换检测
- 更强的轨迹相似度匹配
- 按策略条线 / 因子组 / 参数版本拆开的独立量化轨迹统计
- 量化轨迹与主观交易轨迹的对照分析
- contextual bandit 在线更新闭环
- offline RL / trajectory policy
- 自动生成阶段性风格变化报告
- 原则卡片 / 禁做清单蒸馏

### 4. 真实资金流水与执行层接入

还未实现：

- 券商 / 持仓 / 账户自动导入
- 精准仓位管理与真实资金曲线
- 分时级行为还原
- 图像 / 盘口截图自动归档
- 真实逐笔交易流水回放

### 5. 更重的信息聚合与社区层

虽然 URL-only 新闻抓取已可用，但还未实现：

- 更成熟的跨站聚合、去噪、排序与摘要
- 与记账会话完全打通的信息提醒编排
- source-level 质量评分与自动降权
- 匿名经验卡片共享
- 面向大众的交易思想白皮书社区

## 四、最新验证结果

### 1. 本地回归

- `python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests`
- `python -m unittest discover -s tests -v`
- 当前测试总数：`24`

### 2. 真实联网抓取验证

2026-04-11 执行命令：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime_live_verify_20260411_v4 --disable-market-data event fetch --start-date 20260411 --end-date 20260411
```

结果：

- 总插入 `187` 条事件
- 无错误
- `wallstreetcn`: `13`
- `cls`: `22`
- `jin10`: `52`
- `eastmoney`: `50`
- `10jqka`: `50`

### 3. 调度 dry-run

2026-04-13 08:05 的 dry-run 已验证：

- 先命中 `event_fetch:20260413:0755`
- 再命中 `morning_brief:20260413`
- 且 `fetch_events=true`

这说明“先轮询新闻，再生成晨报”的节奏已经接进调度器。

## 五、版本更新记录

## `0.2.5` | 2026-04-12

本次更新重点放在“GitHub 开源仓库布局 + License + Docker 交付”。

新增 / 强化：

- 新增 `LICENSE`，当前默认采用 MIT License
- 补齐 `CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / SUPPORT.md`
- 新增 GitHub 协作文件：
  - `.github/ISSUE_TEMPLATE/`
  - `.github/pull_request_template.md`
  - `.github/workflows/ci.yml`
  - `.github/dependabot.yml`
- 新增 `requirements.txt`
- 新增 `Dockerfile / .dockerignore / compose.yaml / docker/entrypoint.sh`
- README 新增 Docker 运行方式与开源仓库协作说明
- 本地 Git 仓库已初始化，并为云端推送预留远端接入

## `0.2.4` | 2026-04-12

本次更新重点放在“交割单事实对齐 + 会话延续 + Git 同步边界说明”。

新增 / 强化：

- 新增 `trade import-statement`，支持标准化 CSV / JSON 交割单导入
- 交割单导入会优先对齐价格、日期、数量，并尝试匹配已有交易或补齐平仓
- 导入结果新增 `assistant_message / pending_question / follow_up_queue`
- 若导入时带 `session_key` 且只命中一条记录，会自动把后续补问挂进 `session_state.pending_question`
- Gateway 新增 `交易 导入 文件=... session=... trade_date=...`
- 补充 `GIT_SYNC_WORKFLOW.md` 与 `.gitignore`，明确代码走 Git、运行时账本不直接覆盖同步
- 本地回归测试新增“Gateway 导入交割单 -> 会话继续 enrich”闭环校验

## `0.2.3` | 2026-04-12

本次更新重点放在“量化策略上下文 + 共享上下文轮询优化”。

新增 / 强化：

- `decision_context_json` 文档与展示补齐 `interpretation / market_stage / environment_tags / position_size_pct / risk_boundary / planned_zone`
- 支持通过 `decision_context_json.strategy_context` 记录量化 / 半量化策略条线、因子组、参数版本、启用原因与主观覆盖说明
- Vault 的“用户视角快照”现在也会展示量化策略上下文
- `polling_bundle` 新增 `shared_context_hints / parallel_question_groups`
- 轮询策略开始显式提示三类可复用范围：`trade_date / symbol / strategy`
- 本地回归测试补充了量化上下文展示与并行补问元数据校验

## `0.2.2` | 2026-04-11

本次更新重点放在“用户视角快照 + 新闻 URL-only 适配 + 轮询优化”。

新增 / 强化：

- 计划 / 交易新增 `decision_context_json`
- Intake 新增 `user_focus / observed_signals / position_reason / position_confidence / stress_level`
- `polling_bundle` 新增 `decision_axes / next_axis`，补问逻辑升级为四轴轮询
- Vault 计划 / 交易笔记新增“用户视角快照”区块
- 调度器支持 `event_fetch_times` 与 `fetch_events_before_morning_brief`
- 展示脚本开始生成 `decision_context`
- URL 适配器补齐同花顺 JS 对象 feed 兼容，真实联网验证 5 站点全部打通
- 顶层 `SKILL.md` 已可让 OpenClaw Control UI 直接识别整个工作区并路由子 skill

## `0.2.1` | 2026-04-11

本次更新重点放在“把 skill 说明写得更像真实可接入的会话协议”。

新增 / 强化：

- 重写并扩展 `finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- 明确 OpenClaw、QQ、飞书的接入视角、最小输入契约和推荐展示策略
- 补充人话式用户话术、会话示例、失败处理与边界说明
- 统一整理这份主状态文档，作为已实现 / 未实现 / 版本更新的单一入口

## `0.2.0` | 2026-04-11

本轮重点：让它更像一个可直接挂进 OpenClaw workspace `skills/` 的会话级 skill。

新增：

- OpenClaw 会话级状态机
- `session_threads` 持久化
- `finance_journal_session_agent.py`
- 已落账记录的二次沉淀：`plan enrich / trade enrich`
- 风格画像：`evolution portrait`
- OpenClaw 会话契约文档

## `0.1.0` | 初始基线

建立了最小可用闭环：

- SQLite 账本
- 计划 / 交易 / 回顾 / 体检
- 自由文本解析
- 草稿补问
- Obsidian 导出
- 自进化报告基础版

## 六、接下来最值得优先做的事

如果继续按当前方向推进，优先级建议是：

1. 做更稳的大模型会话理解，让“非标准化记账 -> 结构化沉淀”更自然
2. 把“共享上下文提示”升级成会话内自动缓存与批量复用，进一步减少重复轮询
3. 做更成熟的晨报聚合、去噪与 source-level 评分
4. 做风格画像版本化、轨迹相似度与长期对比，并补一条独立的量化轨迹线
5. 做真实资金流水接入与账户级记账
6. 再考虑 contextual bandit 在线更新与更细粒度轨迹学习

## 七、相关文档

- 根入口 skill：`SKILL.md`
- 技能说明：`finance-journal-orchestrator/SKILL.md`
- 功能说明：`finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- 会话契约：`finance-journal-orchestrator/references/openclaw-session-contract.md`
- 命令速查：`finance-journal-orchestrator/references/command-cheatsheet.md`
- 框架目的与愿景：`FRAMEWORK_PURPOSE_AND_VISION.md`
