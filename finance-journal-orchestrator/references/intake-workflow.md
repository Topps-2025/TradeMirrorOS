# Intake Workflow

目标：让“记账”先变简单，再变聪明。

## 当前实现

这套框架已经支持 `intake parse` / `intake apply` 两步：

1. 接收非标准化中文记账语句
2. 识别它更像是 `plan` 还是 `trade`
3. 提取尽量多的结构化字段：
   - 股票代码 / 名称
   - 买卖日期 / 价格
   - 逻辑标签
   - 形态标签
   - 环境标签
   - 情绪备注
   - 失误标签
   - 用户视角快照字段
4. 返回 `missing_fields`
5. 返回 `follow_up_questions`，供 OpenClaw 继续追问补全
6. 返回 `standardized_record`，让 OpenClaw 看到“当前已经被整理成什么样”
7. 返回 `polling_bundle`
8. 若字段已足够，则直接 `apply` 落库并同步 vault

## 用户视角快照

当前实现里，系统不再只补“事实字段”，也会尽量补齐“用户当时看到的市场切片”：

- `user_focus`：用户当时关注了哪些股票 / 板块 / 主题
- `observed_signals`：用户提到的信号，例如“回踩 5 日线”“板块企稳”“跌不动了”
- `position_reason`：为什么这次仓位更重 / 更轻 / 只是试错仓
- `position_confidence`：对这次判断的主观把握度
- `stress_level`：当时的心理压力或焦虑程度

这些字段会在计划 / 交易落库时进入 `decision_context_json`，Vault 笔记里也会同步写成“用户视角快照”。

对于量化 / 半量化场景，建议把“主观仍然存在但不适合写成传统选股理由”的部分单独放进：

- `decision_context_json.strategy_context`

典型包括：

- 因子组为什么这样选
- 今天启用的是哪条策略条线
- 参数版本是否切换
- 是否有人为覆盖 / 降杠杆 / 暂停某条线

这样量化记录不会被硬塞回原来的主观短线话术，而是走一条独立的策略上下文轨迹。

## 四轴轮询补问

当前 `polling_bundle` 不只是“还缺哪个字段”，也会带一层更适合 OpenClaw 的轮询信息：

- `decision_axes`
- `next_axis`
- `next_field`
- `next_question`
- `missing_field_queue`
- `reply_strategy`
- `completion_progress`
- `reflection_queue`
- `shared_context_hints`
- `parallel_question_groups`

四个补问轴如下：

1. `selection`：你当时关注的是哪只票 / 哪个板块 / 哪条主线
2. `timing`：是什么触发了你现在买 / 卖 / 等待
3. `position`：为什么这次仓位这么配
4. `emotion`：当时的紧张、犹豫、冲动、纪律状态如何

这让 OpenClaw 更像一个“轻量采访者”，而不是只会机械补表单。

## 共享上下文与并行补问

为了减少重复轮询、节省 token，当前 `polling_bundle` 还会额外提示两类信息：

### 1. `shared_context_hints`

告诉 OpenClaw 哪些答案可以按范围复用：

1. `trade_date`：同一日期的市场环境、环境标签、关键触发信号
2. `symbol`：同一只票反复做 T 时的主线、观察重点、触发条件
3. `strategy`：量化 / 半量化策略的条线、因子组、参数版本、启用原因

### 2. `parallel_question_groups`

告诉 OpenClaw 哪些问题可以合并成一个“问题块”一次提：

1. `fact_block`：价格、日期、方向等事实快填
2. `market_context_block`：同日环境相关问题一起问
3. `symbol_context_block`：单票主线 / 做 T 相关问题一起问
4. `strategy_context_block`：量化策略条线相关问题一起问

推荐理解方式：

- 默认仍然“先问最关键的一块”
- 但如果 `parallel_question_groups` 已明确提示可以合并，就不必机械地一问一答
- 这样既保留稳健性，也能减少“同一天 / 同一票 / 同一策略”被反复追问

## 草稿轮询与会话状态机

同时也已经支持草稿轮询：

1. `intake draft-start`
2. `intake draft-reply`
3. `intake draft-apply`

草稿会持久化保存：

- 当前已识别字段
- 尚缺字段
- 下一问
- 已输入的原始语句轨迹
- 最近一次轮询元数据

OpenClaw 会话线程还会记住：

- 当前 active draft
- 最近聚焦的计划 / 交易
- 最近一次由 skill 返回给用户的话术

补充说明：

- 如果当前只有一份 active draft，后续 `draft-reply / draft-show / draft-apply` 可以不显式传 `draft_id`
- 如果同时存在多份 active draft，则需要明确指定 `draft_id`
- 现在也支持 `session_key`，便于 OpenClaw 按用户 / 群聊会话绑定草稿
- 对已经落账的计划 / 交易，还支持继续补充：`plan enrich / trade enrich`

## 推荐人机协同模式

### 模式 A：先解析，再追问

适合 QQ / OpenClaw 多轮对话：

1. 用户先发一段自然语句
2. OpenClaw 调 `intake parse`
3. 读取 `follow_up_questions` 与 `polling_bundle`
4. 继续向用户补问缺失字段
5. 补完后再调用 `plan create` / `trade log` / `trade close`

### 模式 A2：草稿状态机轮询

适合真的把“记账”做成连续对话：

1. 用户先发一段不完整语句
2. OpenClaw 调 `intake draft-start`
3. 读取 `next_question`
4. 用户每回答一次，就调用 `intake draft-reply`
5. 当草稿字段齐全时，系统自动落账

当前 `polling_bundle.reply_strategy` 已明确约定：

- 先把用户下一条回复当作 `next_field` 的候选答案
- 如果回复里顺带补了别的字段，再整体重跑解析器
- 事实字段优先，认知切片与软结构随后补
- 如果同日市场环境一致，可把日期级环境问题合并一次回答
- 如果同一只票只是做 T，可把选股主线和触发信号一次回答
- 如果是量化 / 半量化策略，可把策略条线、因子与启用原因作为独立上下文补一次

### 模式 A3：真正的会话级接话

适合直接挂到 OpenClaw workspace `skills/`：

1. OpenClaw 每轮只传 `session_key + text`
2. skill 读取本地 `session_threads`
3. 自动决定：
   - 是新建草稿
   - 还是继续补草稿
   - 还是自动落账
   - 还是把后续反思沉淀回最近记录
4. 返回 `assistant_message + session_state + structured payload`

### 模式 B：直接落账

适合信息比较完整时：

1. 用户发较完整的记账语句
2. OpenClaw 调 `intake apply`
3. 若 `applied=true`，直接完成落库与 Obsidian 导出
4. 若 `applied=false`，读取缺失字段并继续追问

### 模式 C：先落账，后补反思

适合盘中先快速记事实、盘后再慢慢沉淀：

1. 先通过 `intake apply` / `trade log` / `plan create` 完成基础落账
2. 盘后或几天后再调用 `plan enrich` / `trade enrich`
3. OpenClaw 读取返回的 `reflection_prompts / polling_bundle`
4. 继续追问用户，把逻辑、情绪、失误、经验补回原记录

## 设计原则

- 允许用户先说“人话”，不要一开始逼他填表
- 先保住事实，再慢慢补认知切片和标签
- 允许“先落账，再返工补充”，不要逼用户一次把所有复盘信息说完整
- 结构化只用于索引、检索、统计，不用于自动执行交易
- 情绪 / 失误 / 仓位理由 / 关注焦点，是个人风格沉淀的核心字段
- 标签抽取宁可保守，不要幻觉扩写
- 规则抽取宁可漏一点，也不要把股票代码、止损位错记成价格或日期
- 结构化后的记录，最终都要能回流到历史统计、自进化和行为体检

## 未来增强方向

- 真正的大模型标签抽取器
- 多轮追问状态机
- 基于个人历史样本的个性化补问
- 按个人历史自动建议“你常用但没填的标签”
- 通过历史轨迹，逐步识别个人交易风格原型
- 把草稿状态机从“字段补齐”升级到“真正理解上下文回答”的大模型代理
- 把 `shared_context_hints` 从“提示可复用”升级到“会话内自动缓存并批量复用”
- 把量化 `strategy_context` 接入独立的策略轨迹统计与自进化报告
