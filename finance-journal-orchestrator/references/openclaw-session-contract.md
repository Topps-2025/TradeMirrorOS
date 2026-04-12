# OpenClaw Session Contract

目标：把这套账本框架当成一个可直接放进 OpenClaw workspace `skills/` 的会话级 skill 来设计。

## 一、推荐入口

未来 OpenClaw 侧优先使用：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_session_agent.py `
  --session-key qq:user_a `
  --text "今天买了603083"
```

这个入口的设计意图是：

- OpenClaw 每收到一轮用户消息，就把消息和 `session_key` 交给这个脚本
- skill 自己决定当前这一轮是：
  - 新开草稿
  - 继续补草稿
  - 自动落账
  - 对最近的计划/交易做二次沉淀
  - 返回当前会话状态

## 二、为什么要单独做会话级入口

CLI 和 gateway 更适合：

- 人工调试
- 批量脚本
- 明确命令式调用

但 OpenClaw skill 的真实使用场景是：

- 用户在聊天里一句一句地说
- skill 需要记住当前正在补哪条账
- skill 需要知道上一个刚落账的是哪条计划/交易
- skill 需要把后续“补充一句”“反思一句”自动沉淀回去

所以会话级入口不是简单封装 CLI，而是一个更贴近对话状态机的 skill 契约。

## 三、当前支持的会话级能力

`finance_journal_session_agent.py` / `session turn` 当前已经支持：

1. 如果会话里有 active draft：
   - 自动把下一句当作补充
   - 自动决定是继续追问还是直接落账

2. 如果刚落账了计划 / 交易：
   - 用户后续再发“补充 / 反思 / 经验 / 情绪”类语句
   - 会自动沉淀回最近那条计划/交易

3. 如果用户只想看当前进度：
   - 可调用 `--state`

4. 如果用户想清空上下文重新开始：
   - 可调用 `--reset`

## 四、OpenClaw 侧建议透传的最小字段

至少透传：

- `session_key`
- `text`

建议额外透传：

- `trade_date`
- `mode`

推荐的 `session_key` 生成方式：

- 私聊：`qq:<user_id>`
- 群聊：`qq:<group_id>:<user_id>`
- 其他网关：`platform:chat_id:user_id`

原则是：

- 对同一用户/会话保持稳定
- 不同会话彼此隔离

## 五、当前返回结构

会话级入口返回的核心字段包括：

- `route`
- `assistant_message`
- `session_state`
- `draft` / `result`

其中：

- `assistant_message`：OpenClaw 可以直接发给用户
- `session_state`：OpenClaw 可用来决定是否需要本地缓存更多状态
- `draft` / `result`：OpenClaw 可进一步读取结构化信息、反思问题、自进化提醒

## 六、未来还要补的能力

当前会话级能力已经可用，但还不是最终形态。

后续仍需要：

- 从 OpenClaw 网关上下文里自动无感透传 `session_key`
- 让 skill 更稳定地区分“这是新记账”还是“这是对上一条的补充”
- 做真正的大模型多轮意图识别，而不只是当前的启发式路由
- 让会话级入口支持更丰富的上下文恢复和长期风格记忆

## 七、设计边界

即使做成会话级 skill，也仍然坚持：

- 这是交易行为复盘账本，不是荐股 agent
- 会话状态只服务于“更方便记账、更真实复盘、更持续沉淀”
- 标签和画像只用于索引、统计、反思，不用于自动交易
