# 已实现能力清单

更新日期：2026-04-12

统一状态、未实现项与版本更新请优先查看：`FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`

## 一、账本主线（已实现）

- 本地 SQLite 账本：`watchlist / keywords / plans / trades / market_snapshots / info_events / reviews / health_reports / schedule_runs / journal_drafts / session_threads`
- 交易计划管理：创建、查询、状态更新、关联交易
- 交易记录管理：开仓、平仓、计划偏离、收益 / 基准收益 / 操作绩效差值
- 卖出后回顾：卖飞 / 有效保护 / 平淡走势识别
- 行为体检：计划执行率、计划外交易、持仓偏离、止损纪律、连亏后仓位变化、大赚后频率变化

## 二、用户视角快照与认知沉淀（已实现）

- `plans` / `trades` 已新增 `decision_context_json`
- 解析器已能抽取并合并以下“用户视角快照”字段：
  - `user_focus`
  - `observed_signals`
  - `position_reason`
  - `position_confidence`
  - `stress_level`
- `decision_context_json` 当前还会承载：
  - `interpretation`
  - `market_stage / environment_tags`
  - `position_size_pct / risk_boundary / planned_zone`
  - `emotion_notes / mistake_tags / source_notes`
- 对量化 / 半量化记录，当前已支持通过 `decision_context_json.strategy_context` 额外保留：
  - 策略条线
  - 策略家族
  - 核心因子列表
  - 因子选择理由
  - 启用原因
  - 参数版本
  - 组合角色 / 主观覆盖说明
- `plan create` / `trade log` / `plan enrich` / `trade enrich` / `apply_journal_text` 都会持久化这份上下文
- Vault 计划笔记与交易笔记会新增“用户视角快照”区块，并把量化策略上下文一起展示出来，便于展示与复盘
- 展示脚本 `generate_showcase_demo.py` 也会生成对应的认知切片，方便从记账一路展示到自进化和体检

## 三、便捷记账入口（已实现）

- `intake parse`：解析非标准化中文记账语句
- `intake apply`：字段足够时直接落账
- 自由文本抽取能力：
  - 股票代码 / 名称
  - 买入价 / 卖出价
  - 日期
  - 逻辑标签
  - 形态标签
  - 环境标签
  - 情绪片段
  - 失误标签
  - 用户视角快照字段
- 缺失字段识别：`missing_fields`
- 自动补问建议：`follow_up_questions`
- 标准化预览：`standardized_record`
  - 输出一句话摘要
  - 输出可检索的 `index_fields`
  - 明确提示“软结构只用于索引/统计，不用于自动交易”
- 轮询补全元数据：`polling_bundle`
  - `next_field / next_question`
  - `missing_field_queue`
  - `reply_strategy`
  - `completion_progress`
  - `reflection_queue`
  - `decision_axes`
  - `next_axis`
  - `shared_context_hints`
  - `parallel_question_groups`
- 轮询策略已升级为四轴补问：
  - 选股关注
  - 择时触发
  - 仓位边界
  - 情绪纪律
- 轮询策略现在还会按三种可复用范围给 OpenClaw 提示：
  - `trade_date`：同一日期的市场环境可合并补问
  - `symbol`：同一只票做 T 的主线 / 触发信号可合并补问
  - `strategy`：量化 / 半量化策略条线可作为独立上下文块补问
- 解析保守性增强：
  - 避免把 `603083` 这类 6 位股票代码误识别成日期或成交价
  - 避免把计划里的 `止损40` 误识别成真实卖出价
  - 更适合先快速落事实，再逐步补标签
- 标准化交割单导入：
  - `trade import-statement`
  - 支持 CSV / JSON 行级导入
  - 可先对齐价格、日期、数量，再把主观轨迹留给后续追问
  - 返回 `assistant_message / pending_question / follow_up_queue`

## 四、多轮草稿与 OpenClaw 会话入口（已实现）

- 草稿状态机：
  - `intake draft-start`
  - `intake draft-reply`
  - `intake draft-apply`
  - `intake draft-list`
- 草稿会持久化：`fields / missing_fields / next_question / raw_inputs / polling_bundle`
- 当当前仅有一份 active draft 时，可省略 `draft_id`
- `session_key` 已支持按用户 / 会话隔离草稿
- OpenClaw 会话级状态机：
  - `session turn`
  - `session state`
  - `session reset`
  - `finance_journal_session_agent.py`
- skill 可按 `session_key` 自动判断当前应当新建草稿、继续补草稿、自动落账，或把后续反思沉淀回最近记录
- 交割单导入若只命中一条记录，也会自动把 follow-up 问题挂进 `session_state.pending_question`
- Gateway 当前也支持 `交易 导入 文件=... session=... trade_date=...`

## 五、信息监测与晨报辅助（已实现）

- 事件手工录入：`event add`
- URL 适配抓取：
  - `event fetch-url`
  - `url_sources.adapters`
  - 支持 `html_timeline / html_list / html_article / rss / json_list / html_embedded_json`
- URL-only 云端抓取增强：
  - 自动尝试 `utf-8 / utf-8-sig / gb18030 / gbk / big5`
  - 自动忽略脚本、样式和低价值噪音文本
  - 支持 JSONP 风格接口
  - 支持 JS 赋值对象风格 feed，例如同花顺 `var thsRss = {...};`
- 当前仓库已放好 5 个展示友好的新闻预设：
  - `wallstreetcn-live-global`
  - `cls-telegraph`
  - `jin10-home-flash`
  - `eastmoney-kuaixun`
  - `10jqka-realtime-news`
- `event fetch` 可在禁用 Tushare 的情况下仅靠 URL adapters 独立落事件
- 晨报生成：`brief generate`
- 调度器已支持：
  - `schedules.event_fetch_times`
  - `schedules.fetch_events_before_morning_brief`
  - 让“先轮询快讯，再生成晨报”成为可配置流程
- 信息事件会保留：
  - `url`
  - `raw_payload_json`
  - 便于去重、复查和后处理

## 六、自进化、风格画像与体检（已实现）

- 自进化报告：`evolution report`
  - 提取优质路径、可复用基因、风险基因
- 自进化提醒：`evolution remind`
  - 创建计划时可附加个人路径提醒
  - 记录交易时可附加个人路径提醒
  - 晨报可附加 active plan 的自进化提醒
  - 会额外输出：`pre_trade_checklist / reflection_prompts / soft_structure_note`
- 风格画像：`evolution portrait`
  - 归纳优势路径、风险区域、情绪画像、纪律画像
- 已接入 bandit 风格排序层：
  - `posterior_mean`
  - `exploration_bonus`
  - `ucb_score`
  - `risk_penalty_score`
- 行为体检：`report health`
- 卖出后回顾反馈也会纳入自进化画像与提醒排序

## 七、展示与演示链路（已实现）

- `generate_showcase_demo.py` 可生成 2026 年 2 月起的一批展示用计划 / 交易 / 回顾 / 体检 / 晨报样例
- 展示样本会使用真实行情价格与真实新闻事件
- 选股原因 / 买卖点原因当前仍以展示模拟为主，便于在没有完整逐笔流水时先完成 demo
- 生成后的运行时目录可直接拿给 OpenClaw 或 Obsidian 做展示

## 八、已完成验证

- `python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests`
- `python -m unittest discover -s tests -v`
- 交割单导入 -> 会话追问 -> 继续 enrich 的本地闭环 smoke test 已覆盖
- 当前本地测试总数：`24`
- 回归测试已覆盖：
  - 股票代码不再误判为日期
  - 股票代码不再误判为买入价
  - 计划止损不再误判为卖出价
  - 用户视角快照字段解析
  - `decision_context_json` 持久化与 Vault 输出
  - `strategy_context` 的 Vault 展示
  - 共享上下文提示与并行补问分组
  - 四轴轮询与 schedule dry-run
  - JSONP feed 解析
  - 同花顺 JS 对象 feed 解析
  - URL adapters 可在禁用 market data 时独立工作
- 2026-04-11 真实联网抓取验证结果：
  - 总插入 `187` 条事件
  - `wallstreetcn`: `13`
  - `cls`: `22`
  - `jin10`: `52`
  - `eastmoney`: `50`
  - `10jqka`: `50`
- 2026-04-13 调度 dry-run 已验证：`07:55` 先执行 `event_fetch`，`08:00+` 再执行 `morning_brief`
