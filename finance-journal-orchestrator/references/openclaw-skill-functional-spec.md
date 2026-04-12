# OpenClaw Skill 功能说明

更新日期：2026-04-12
适用 skill：`finance-journal-orchestrator`
当前建议版本：`0.2.4`

这份文档同时服务两类读取方：

- OpenClaw：需要知道这个 skill 该怎么调用、返回什么、边界是什么
- QQ / 飞书 / 其他聊天平台接入层：需要知道如何把自然语言映射成稳定的会话调用

文档关注的不是某一个脚本，而是整个“交易行为复盘记账本”skill 的会话契约、任务边界、常见话术和推荐落地方式。

## 一、技能定义

这是一个围绕“记账 -> 补全 -> 沉淀 -> 自进化 -> 体检”展开的会话级交易复盘账本 skill。

它首先解决的是：

- 让用户更方便地把计划、交易、情绪、失误、经验记下来
- 让大模型从非标准化表达里提炼出软结构标签，便于后续检索、统计、提醒
- 让已落账记录可以继续被补充、反思、修正，持续沉淀为个人交易风格资产
- 对量化 / 半量化策略，把因子选择、策略条线启停、参数版本与主观覆盖动作单独记成策略上下文

它不是：

- 荐股 agent
- 自动下单 agent
- 纯量化执行引擎
- 替用户给出最终买卖决策的投顾

## 二、适用对象与不适用对象

更适合：

- 主观交易者
- 半量化交易者
- 想把交易经历沉淀为个人方法论的人
- 愿意用聊天方式长期做复盘的人

相对不适合：

- 完全自动执行的纯量化系统
- 几乎不做短中频交易、样本极少的用户
- 只想直接听买卖建议、不愿意提供真实交易背景的用户

## 三、核心价值主张

### 1. 便捷记账

允许用户先说“人话”，例如：

- “今天买了603083”
- “43.2买的，CPO修复回流，盘中有点急”
- “计划在42.5到43低吸，止损40”

skill 负责把这些内容整理成：

- 基础事实字段
- 软结构标签
- 待补字段队列
- 反思问题

### 2. 多轮补全

用户不必一次把所有字段说全。

skill 会：

- 判断当前缺什么
- 一次只追问一个核心问题
- 在字段足够时自动落账
- 落账后继续引导补“情绪 / 失误 / 经验 / 场景判断”

### 3. 已落账后的二次沉淀

用户经常会在事后补一句：

- “其实这是冲动追高”
- “更像高位分歧里的放量突破”
- “下次先等回踩确认”

这类语句不能丢。skill 应自动判断它是在补充最近一条计划还是最近一条交易，并把它回写原记录。

### 4. 自进化提醒

当同类标签、同类环境、同类失误不断出现时，skill 可以基于个人历史输出：

- 优质路径
- 风险基因
- 复核清单
- 风格画像
- 反思追问

### 5. 行为体检

skill 不只看盈亏，也看：

- 计划执行率
- 计划外交易占比
- 止损纪律
- 持仓周期偏离
- 盈利后是否放松标准
- 连亏后是否放大风险

## 四、严格边界

OpenClaw 调用本 skill 时应始终保持以下边界：

- 标签只用于索引、统计、提醒、反思，不用于自动执行交易
- 所有结论默认表述为“基于你的历史记录”
- 数据缺失时直接提示缺口，不伪造市场数据或交易事实
- 不输出“建议买入 / 建议卖出 / 建议仓位”
- 不把用户的一句模糊表达强行解释成精确的量化规则

## 五、推荐接入方式

### 模式 A：OpenClaw 会话级直接调用

最推荐。

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_session_agent.py `
  --session-key qq:user_a `
  --trade-date 20260410 `
  --text "今天买了603083"
```

适合：

- OpenClaw workspace `skills/`
- QQ / 飞书等聊天平台的自然语言接入
- 真正的一轮一句、多轮补全式交互

优点：

- 上层只需要持续传 `session_key + text`
- skill 自己记住当前草稿、最近实体、上一次路由结果
- 可以自动在“起草 / 补充 / 落账 / 二次沉淀 / 状态查询”之间切换

### 模式 B：Gateway 命令式调用

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py `
  --command "记账 session=qq:user_a trade_date=20260410 text='今天买了603083'"
```

适合：

- 平台网关希望先做一层路由或权限控制
- 需要用统一命令协议挂接多个 skill

### 模式 C：CLI 调试与本地验证

适合：

- 开发调试
- 本地 smoke test
- 手工复现某一轮会话结果

## 六、平台侧最小输入契约

建议 OpenClaw 或平台接入层每轮最少提供：

- `session_key`：会话唯一键
- `text`：用户原始输入

建议尽量补充：

- `trade_date`：如果消息明确属于某个交易日，优先传入
- `mode`：`auto / trade / plan`
- `lookback_days`：自进化查询时的回看窗口

推荐的 `session_key` 生成方式：

- QQ 私聊：`qq:<user_id>`
- QQ 群聊：`qq:<group_id>:<user_id>`
- 飞书私聊：`feishu:<open_id>`
- 飞书群聊：`feishu:<chat_id>:<open_id>`
- 其他平台：`platform:<chat_id>:<user_id>`

原则：

- 同一用户、同一聊天上下文必须稳定
- 群聊里不同用户必须隔离
- 平台重启后同一个会话仍尽量能恢复到同一 `session_key`

## 七、平台适配层推荐做法

平台适配层推荐只做薄封装，不要在平台侧过早“理解”交易逻辑。

推荐流程：

1. 收到用户消息
2. 从平台元数据生成 `session_key`
3. 原样透传用户 `text`
4. 若平台已有日期上下文，则补传 `trade_date`
5. 调用会话级 skill
6. 读取 `assistant_message` 回发用户
7. 如果存在 `session_state.pending_question`，等待用户下一轮继续说

不要在平台侧做的事：

- 不要先把用户原话改写成太多结构化标签
- 不要在平台侧替 skill 判断“这是计划还是交易”
- 不要在平台侧强制用户填表单式字段

## 八、用户可直接说的人话范式

### 1. 快速记账

用户常见说法：

- “今天买了603083”
- “43.2买的，感觉有承接”
- “下午回封的时候又加了一笔”
- “卖了，46.8走的，主要怕板块继续分歧”

### 2. 计划录入

用户常见说法：

- “记一个计划，603083回踩42.5到43低吸，止损40”
- “这个计划逻辑是龙头首阴，博弈CPO修复”
- “有效期看到下周二”

### 3. 已落账补充

用户常见说法：

- “补充：当时有点急，属于冲动追高”
- “补一句，这笔其实更像高位分歧里的放量突破”
- “经验：下次先等回踩确认再上”
- “修正一下，不是43.2，是43.05”

### 4. 自进化 / 画像 / 体检

用户常见说法：

- “帮我看看最近低吸这类做得怎么样”
- “我最近最常犯的错误是什么”
- “生成我的风格画像”
- “生成本月行为体检”
- “最近是不是老计划外交易”

### 5. 会话控制

用户常见说法：

- “现在记到哪一步了”
- “继续”
- “重置一下，我们重新记”

## 九、当前 skill 能处理的核心任务

### 1. 新建计划或交易草稿

若信息不完整，返回：

- `route = draft_started`
- `assistant_message`
- `draft`
- `session_state`

### 2. 继续补字段

若上一轮已有 active draft，本轮优先把用户输入当补充。

若仍未完成，返回：

- `route = draft_continued`
- `assistant_message`
- `draft`
- `session_state`

若字段已够，自动落账，返回：

- `route = draft_applied`
- `assistant_message`
- `result`
- `session_state`

### 3. 会话内直接一步落账

若首句就足够完整，可能直接返回：

- `route = applied_from_session`
- `assistant_message`
- `result`
- `session_state`

### 4. 已落账记录二次沉淀

若识别为对最近计划/交易的补充，返回：

- `route = entity_enriched`
- `assistant_message`
- `result`
- `session_state`

### 5. 状态查询 / 重置

分别返回：

- `route = session_state`
- `route = session_reset`

## 十、推荐返回结构与平台展示策略

当前会话级 skill 建议平台优先读取这些字段：

- `assistant_message`
- `route`
- `session_state`

`session_state` 当前重点字段包括：

- `session_key`
- `active_mode`
- `trade_date`
- `active_draft_id`
- `active_entity_kind`
- `active_entity_id`
- `pending_question`
- `entity_summary`
- `last_route`
- `last_assistant_text`

如果平台希望做更强编排，再读取：

- `draft`
- `result`
- `polling_bundle`
- `reflection_prompts`
- `evolution_reminder`
- `follow_up_queue`

其中 `polling_bundle` 里新增的两个字段，适合平台做“少轮次交互”：

- `shared_context_hints`：提示哪些答案可以按 `trade_date / symbol / strategy` 范围复用
- `parallel_question_groups`：提示哪些问题可以并成一个问题块一起问

推荐展示策略：

1. 直接把 `assistant_message` 发给用户
2. 若 `pending_question` 非空，让下一轮用户直接回答即可
3. 若有 `reflection_prompts`，一次最多展示 1 条，避免问题过多
4. 若有 `evolution_reminder`，优先作为“补充提示”，不要伪装成指令
5. 若 `route = statement_import` 且 `session_state.pending_question` 非空，不要重复追问价格 / 日期，直接继续补主观原因

## 十一、记账与反思的对话原则

skill 在会话里应尽量遵守：

- 默认一次只追一个关键问题块，而不一定永远只追一个字段
- 先落事实，再补反思
- 优先保留用户原话，再抽软结构标签
- 允许用户先记流水，再逐步沉淀为风格和原则
- 当输入明显含糊时宁可追问，也不要自作主张补完

当 `parallel_question_groups` 已明确提示可以合并时，允许把几个高度相近的问题并成一个块，例如：

- 同日市场环境一起问
- 同一只票做 T 的主线与触发条件一起问
- 量化策略条线、因子与启用原因一起问

推荐追问顺序：

1. 先补最关键的事实字段：标的、价格、方向、时间
2. 再补最核心的主观逻辑：为什么买 / 为什么卖 / 为什么放弃
3. 再补环境、情绪、错误、经验
4. 最后再给个人历史提醒或复盘问题

### 交割单导入时的对话建议

当 skill 返回 `route = statement_import` 时，推荐平台这样处理：

- 先把 `assistant_message` 原样发给用户，确认“事实已对齐”
- 若 `session_state.pending_question` 非空，下一轮直接承接这条问题
- 不要重复追问已经由交割单给出的价格、日期、数量
- 如果 `follow_up_queue` 里有多条记录，可按 `trade_id` 逐条追问，不必一次全部展开

## 十二、会话示例

### 示例 A：QQ / 飞书里的快速记账

用户：`今天买了603083`

skill：`已帮你起草一条交易记录。下一问：买入价格大概是多少？`

用户：`43.2`

skill：`收到。下一问：这笔最核心的买入逻辑是什么？`

用户：`CPO修复回流，想做低吸，但盘中有点急`

skill：`这笔交易已记下：603083，买入价 43.2。已补充逻辑与情绪备注。接下来可以继续补一句：如果重来一次，你最想修正的动作是什么？`

### 示例 B：已落账后的二次沉淀

用户：`补充：其实这笔更像高位分歧里的放量突破`

skill：`已把这条补充沉淀到最近交易里，更新了场景与标签。下一步可继续想一想：这类形态下你最容易在哪个环节失手？`

### 示例 C：会话状态查询

用户：`现在记到哪一步了`

skill：`当前还在补这条草稿。下一问：买入价格大概是多少？`

### 示例 D：风格 / 体检提问

用户：`帮我看看我最近是不是老计划外交易`

skill：`可以。我会基于你的历史计划与交易记录做行为体检，结果只代表你的个人历史统计。`

## 十三、数据落地原则

所有结果默认遵守：

1. 先写 SQLite
2. 再写 JSON / Markdown artifact
3. 若启用了 vault，再同步到 Obsidian markdown
4. 所有报告都应明确 trade date 或 period
5. 所有自进化结论都应注明样本来自个人历史

## 十四、失败处理与降级策略

遇到以下情况时，skill 应优先稳健而不是激进：

- 字段不够：返回草稿与追问，不强行落账
- 语义冲突：优先请用户确认
- 市场数据缺失：明确标注 `data gap`
- 无足够样本：直接提示“样本不足以形成稳定统计”
- 会话失焦：允许用户查询状态或重置

## 十五、与其他参考文档的关系

如果要继续深入，建议搭配阅读：

- skill 入口说明：`finance-journal-orchestrator/SKILL.md`
- 会话契约：`finance-journal-orchestrator/references/openclaw-session-contract.md`
- 命令速查：`finance-journal-orchestrator/references/command-cheatsheet.md`
- 当前状态与版本更新：`FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`

这份功能说明的目标，是让这套框架真正朝“可直接放进 OpenClaw workspace `skills/` 的会话级交易复盘 skill”去收敛，同时让 QQ、飞书等平台上的普通用户也能直接用自然语言持续记账、补充、复盘和沉淀。
