# Finance Journal Skills

这是一个基于 OpenClaw 的“交易行为复盘记账本”技能框架。

现在仓库根目录也提供了一个总入口 `SKILL.md`，方便 OpenClaw Control UI 直接把整个工作区识别成一个可路由的 skill，再下钻到各子 skill。

当前优先级已经明确为：

1. 先把交易行为、计划纪律、卖出后回顾、月度体检做好
2. 再把新闻/公告监测作为可选辅助模块接进来

也就是说，这套框架首先是你的本地交易复盘账本，其次才是信息提醒工具。

当前实现选择 `SQLite + Markdown/JSON artifacts + Obsidian Vault` 的本地优先方案：

- 数据库：`_runtime/data/finance_journal.db`
- 日级产物：`_runtime/artifacts/daily/YYYYMMDD/`
- 长期记忆：`_runtime/memory/`
- Markdown 知识库：`_runtime/obsidian-vault/`

## 目录结构

- `finance-journal-orchestrator/`：主 skill，包含 CLI、OpenClaw 网关、配置和参考文档。
- `finance-info-monitor/`：可选的信息监测 skill。
- `trade-plan-assistant/`：交易计划 skill。
- `trade-evolution-engine/`：交易记录、自进化和卖出回顾 skill。
- `behavior-health-reporter/`：行为体检报告 skill。
- `finance_journal_core/`：共享 Python 核心逻辑。
- `tests/`：本地无网 smoke test。

## 快速开始

1. 初始化运行时目录和数据库

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault init
```

2. 用自然语言快速记账 / 建计划

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake parse `
  --mode trade `
  --trade-date 20260410 `
  --text "今天低吸了603083，43.2买的，想博弈CPO回流，盘中有点急，感觉还是拿不稳。"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake apply `
  --mode plan `
  --trade-date 20260410 `
  --text "计划在42.5-43.0低吸603083，止损40，看CPO回流。"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake draft-start `
  --mode trade `
  --trade-date 20260410 `
  --session-key qq:user_a `
  --text "今天买了603083"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake draft-reply <draft_id> `
  --text "43.2"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake draft-reply <draft_id> `
  --text "逻辑是CPO修复回流，想做低吸。"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan enrich <plan_id> `
  --text "补充：这是龙头首阴低吸，高位分歧里博弈CPO回流，止损40。"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade enrich <trade_id> `
  --text "补充：当时有点急，属于冲动追高。经验：下次先等回踩确认。"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution portrait `
  --trade-date 20260415 `
  --lookback-days 365 `
  --min-samples 2

python .\finance-journal-orchestrator\scripts\finance_journal_session_agent.py `
  --session-key qq:user_a `
  --trade-date 20260410 `
  --text "今天买了603083"
```

当前 `intake` 的策略偏保守：

- 优先避免把 6 位股票代码误识别成价格或日期
- 优先避免把计划中的止损价误识别成真实卖出价
- 字段不够时返回 `missing_fields` 与 `follow_up_questions`，便于后续由 OpenClaw / 大模型继续追问补全
- 现在也会返回：
  - `standardized_record`：当前这笔记录的软结构标准化预览
  - `polling_bundle`：下一问、字段队列、解析提示、完成进度，以及 `decision_axes / next_axis / shared_context_hints / parallel_question_groups`
  - `reflection_prompts`：在事实落账之外，可继续追问的反思问题
- 解析器现在也会尽量补齐“用户视角快照”字段：
  - `user_focus`
  - `observed_signals`
  - `position_reason`
  - `position_confidence`
  - `stress_level`
- 计划 / 交易落库时会把这些内容持久化到 `decision_context_json`，Vault 笔记里也会同步写出“用户视角快照”区块
- `decision_context_json` 现在除了基础主观切片，也允许挂一层 `strategy_context`，用于量化 / 半量化策略里的因子选择、策略条线、参数版本、启用原因和主观覆盖说明
- 当前已支持持久化草稿状态机：可以先起草、再按问题逐轮补充，字段齐了以后自动落账
- 当且仅当当前只有一份 active draft 时，`draft-show / draft-reply / draft-apply / draft-cancel` 可以省略 `draft_id`
- 现在也支持 `session_key`：OpenClaw 可以按用户 / 群聊会话去绑定草稿，避免多人并发时串草稿
- 现在也支持对既有记录做二次沉淀：
  - `plan enrich`
  - `trade enrich`
  - 适合先落事实、后补逻辑/情绪/经验，把零碎反思持续沉淀回原记录
- 现在也支持真正面向 OpenClaw 的会话级入口：
  - `session turn`
  - `session state`
  - `session reset`
  - 以及更轻量的 `finance_journal_session_agent.py`
  - 目标是让 OpenClaw 每轮只传 `session_key + text`，skill 自己处理“新建草稿 / 继续补充 / 自动落账 / 二次沉淀”
- `polling_bundle` 现在还会提示：
  - `shared_context_hints`：哪些答案可以按 `trade_date / symbol / strategy` 范围复用
  - `parallel_question_groups`：哪些问题可以作为“同日环境块 / 单票做T块 / 量化策略块”并行补问，减少重复轮询

3. 添加关注池和关键词

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py watchlist add 600519 --name 贵州茅台
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py keyword add CPO
```

3.1 直接按 URL 抓公告 / 新闻

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url `
  --url "https://example.com/announcements?code=603083" `
  --type announcement `
  --mode html_list `
  --ts-code 603083 `
  --name 剑桥科技 `
  --include-patterns 公告,业绩
```

如果是长期运行在云端的 OpenClaw，推荐把站点适配写进：

- `finance-journal-orchestrator/config/runtime.local.json` 的 `url_sources.adapters`

这样 `event fetch` / `brief generate --fetch-events` 会自动把 URL 适配源一起抓进来，不再强依赖 Tushare。

当前已内置为 disabled 预设的公开新闻源包括：

- 华尔街见闻：`https://wallstreetcn.com/live/global`
- 金十数据：`https://www.jin10.com/`
- 财联社电报：`https://www.cls.cn/telegraph`
- 东方财富快讯：`https://kuaixun.eastmoney.com/`
- 同花顺实时快讯：`https://news.10jqka.com.cn/realtimenews.html`

这些预设说明见：

- `finance-info-monitor/references/news-source-presets.md`

当前仓库里也已经放了一份可直接启用的本地配置：

- `finance-journal-orchestrator/config/runtime.local.json`

当前默认已启用 5 个 URL-only 新闻源：

- 华尔街见闻
- 财联社电报
- 金十数据
- 东方财富快讯
- 同花顺实时快讯

2026-04-11 已做过一次真实联网抓取验证，单日共插入 187 条事件：

- `wallstreetcn`: 13
- `cls`: 22
- `jin10`: 52
- `eastmoney`: 50
- `10jqka`: 50

这意味着当前这套配置已经能在“云端只有网址、没有浏览器自动化”的前提下，直接跑出可展示的晨报输入源。

对于这类云端 URL 抓取，当前已经支持 5 类解析方式：

- `html_timeline`：时间轴 / 电报流页面
- `html_list`：普通链接列表
- `html_article`：单篇文章详情
- `rss` / `json_list`：公开 feed / JSON 接口
- `html_embedded_json`：页面正文在脚本 JSON 里的 SSR 页面

例如财联社预设现在就是：

- 先走 `html_timeline`
- 如果页面 DOM 时间线抓不到，再自动回退到 `html_embedded_json`

这样更适合“服务器上只有 URL、没有浏览器环境”的部署方式。

调度器现在也已经支持：

- `schedules.event_fetch_times`：在盘前 / 盘中 / 盘后按固定时刻轮询新闻源
- `schedules.fetch_events_before_morning_brief`：晨报前先补抓一次事件，避免晨报吃到旧数据

4. 建立交易计划

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create `
  --ts-code 603083 `
  --name 剑桥科技 `
  --direction buy `
  --thesis "回踩 5 日线博弈 CPO 反弹" `
  --logic-tags 龙头首阴,低吸 `
  --market-stage 震荡市 `
  --environment-tags 高位分歧,CPO `
  --buy-zone 42.5-43.0 `
  --stop-loss 40.0 `
  --holding-period 3-5天 `
  --valid-to 20260415 `
  --with-reference
```

5. 记录交易、导入交割单与平仓

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log `
  --ts-code 603083 `
  --name 剑桥科技 `
  --buy-date 20260410 `
  --buy-price 43.2 `
  --thesis "回踩 5 日线参与" `
  --logic-type-tags 龙头首阴,题材驱动 `
  --pattern-tags 均线回踩 `
  --emotion-notes "盘中略有急躁，但没有追高" `
  --mistake-tags 拿不稳 `
  --lessons-learned "更适合按计划分批止盈" `
  --decision-context-json '{"user_focus":["剑桥科技","CPO板块"],"observed_signals":["回踩5日线","板块修复"],"position_reason":"先开试错仓","position_confidence":0.62,"stress_level":4}'

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log `
  --ts-code 600519 `
  --name 贵州茅台 `
  --buy-date 20260410 `
  --buy-price 1350 `
  --thesis "高股息修复低吸" `
  --logic-type-tags 低吸 `
  --pattern-tags 均线回踩 `
  --decision-context-json '{"user_focus":["贵州茅台","消费板块"],"observed_signals":["板块企稳"],"position_reason":"低波防守仓先试错","strategy_context":{"strategy_line":"高股息修复低吸","strategy_family":"半量化择时","factor_list":["股息率","板块修复","估值回归"],"factor_selection_reason":"当前更想验证高股息+板块修复的共振窗口","activation_reason":"消费板块企稳后恢复试仓","parameter_version":"dividend_repair_v2","portfolio_role":"低波防守仓","subjective_override":"公告前只开观察仓"}}'

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade close <trade_id> `
  --sell-date 20260415 `
  --sell-price 46.8 `
  --sell-reason "达到预设止盈" `
  --lessons-learned "下次要更早规划分批卖点"

python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade import-statement `
  --file .\examples\statement_rows.csv `
  --trade-date 20260415 `
  --session-key qq:user_a
```

`trade import-statement` 适合导入标准化 CSV / JSON 交割单：

- 先对齐代码、日期、价格、数量等“硬事实”
- 若命中已有交易，会优先匹配或补齐平仓，不重复建单
- 返回 `assistant_message / pending_question / follow_up_queue`
- 若带 `session_key`，后续可以直接继续一句“补充：我当时做它是因为……”把选股原因、仓位理由、情绪轨迹慢慢补齐

6. 导出 Obsidian 复盘笔记

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault daily --trade-date 20260415
```

7. 生成晨报、回顾和体检

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py brief generate --trade-date 20260411
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py review run --as-of-date 20260422
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py report health --period-start 20260401 --period-end 20260430 --period-kind monthly
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution report --trade-date 20260415 --lookback-days 365 --min-samples 2
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution portrait --trade-date 20260415 --lookback-days 365 --min-samples 2
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution remind --logic-tags 低吸 --pattern-tags 均线回踩 --market-stage 震荡市 --environment-tags 修复回流
```

8. 一键生成展示用样例账本（2026-02-03 到 2026-04-11）

```powershell
python .\finance-journal-orchestrator\scripts\generate_showcase_demo.py `
  --root .\_runtime_showcase_202602_202604 `
  --start-date 20260203 `
  --end-date 20260410 `
  --brief-date 20260411 `
  --max-trades 14
```

这个脚本会：

- 用真实行情价格生成一批展示用计划 / 交易 / 回顾
- 自动沉淀自进化报告、风格画像、体检报告和晨报
- 保留“价格与日期真实、交易理由与反思为展示模拟文案”的边界

## Obsidian Vault 结构

自动生成在 `obsidian-vault/` 下：

- `00-dashboard/`：交易复盘总览
- `01-plans/`：每个交易计划一篇笔记
- `02-trades/`：每笔交易一篇复盘笔记
- `03-reviews/`：卖出后回顾笔记
- `04-reports/`：月度 / 自定义周期体检报告
- `05-daily/`：按交易日聚合的每日复盘页

这层的目的，是把 SQLite 里的结构化数据变成你可以在 Obsidian 里长期维护的复盘知识库。

## OpenClaw / QQ 网关模式

`finance_journal_gateway.py` 支持把自然语言先规整成 `域 + 动作 + key=value` 的命令格式，便于 OpenClaw 转发：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "计划 新建 code=603083 direction=buy thesis='回踩5日线博弈CPO反弹' logic_tags=龙头首阴,低吸 buy_zone=42.5-43.0 stop_loss=40 valid_to=20260415 with_reference=true"

python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "交易 沉淀 trade_id=trade_xxx text='补充：当时有点急，属于冲动追高。经验：下次先等回踩确认。'"

python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "进化 画像 trade_date=20260415 lookback_days=365 min_samples=2"

python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "会话 接话 session=qq:user_a trade_date=20260410 text='今天买了603083'"
```

如果是未来直接挂进 OpenClaw workspace `skills/` 的用法，建议优先走：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_session_agent.py `
  --session-key qq:user_a `
  --trade-date 20260410 `
  --text "今天买了603083"
```

这样 OpenClaw 每轮只需要稳定透传 `session_key + text`，skill 自己处理当前到底是在起草、续写、落账还是二次沉淀。

## Docker 用法

如果你想把这套 skill 当作开源项目快速拉起，可以直接使用仓库根目录的 `Dockerfile`、`.dockerignore`、`compose.yaml` 和 `docker/entrypoint.sh`。

### 1. 直接构建镜像

```powershell
docker build -t finance-journal:local .
```

### 2. 用命名卷保存运行时账本

```powershell
docker volume create finance-journal-data

docker run --rm -it `
  -v finance-journal-data:/app/_runtime `
  finance-journal:local init

docker run --rm -it `
  -v finance-journal-data:/app/_runtime `
  finance-journal:local trade import-statement --file /app/examples/statement_rows.csv --trade-date 20260415 --session-key qq:user_a
```

### 3. 调用 Gateway / Session Agent

```powershell
docker run --rm -it `
  -v finance-journal-data:/app/_runtime `
  finance-journal:local gateway --command "交易 导入 文件=/app/examples/statement_rows.csv session=qq:user_a trade_date=20260415"

docker run --rm -it `
  -v finance-journal-data:/app/_runtime `
  finance-journal:local session-agent --session-key qq:user_a --trade-date 20260410 --text "今天买了603083"
```

### 4. 用 Compose 跑一次性命令

```powershell
docker compose run --rm finance-journal init
docker compose run --rm finance-journal session-agent --session-key qq:user_a --trade-date 20260410 --text "今天买了603083"
```

镜像默认把 `_runtime` 放在容器内的 `/app/_runtime`，建议始终挂卷，不要把运行时账本直接 bake 进镜像层。

## 开源仓库布局

当前仓库已补齐一套更适合 GitHub 开源协作的基础文件：

- `LICENSE`：当前默认使用 MIT License
- `CONTRIBUTING.md`：本地开发与提交流程
- `CODE_OF_CONDUCT.md`：协作行为约定
- `SECURITY.md`：安全问题报告方式
- `SUPPORT.md`：使用支持入口
- `.github/ISSUE_TEMPLATE/`：Bug / Feature 模板
- `.github/pull_request_template.md`：PR 模板
- `.github/workflows/ci.yml`：CI + Docker build 校验
- `.github/dependabot.yml`：依赖与 GitHub Actions 更新策略

## 说明

- Tushare Token 默认读取环境变量 `TUSHARE_TOKEN` / `TS_TOKEN`。
- 若当前环境不方便联网，可在命令里附加 `--disable-market-data`，框架会退化到纯本地记账与统计。
- 框架只做信息提醒、纪律辅助、历史统计和行为复盘，不做荐股、不做买卖决策替代。
- 新闻/公告模块现在是可选增强，不是账本核心依赖。
- 新闻/公告现在支持 URL 适配抓取，抓下来的事件会保留原始 `url` 与 `raw_payload_json`，便于云端复查与二次清洗。
- 当前多轮补问仍以 `follow_up_questions` 为基础，完整的大模型轮询补全代理仍属于下一阶段能力。
- 当前已经能返回“同日环境 / 同票做T / 同策略条线”的复用提示和并行补问分组，但还没有做到会话内全自动缓存与批量复用。
- 当前自进化模块已经能从历史闭环交易里提取“优质路径 / 可复用基因 / 风险基因”，并可给计划与晨报附加提醒。
- 当前自进化还新增了一层 bandit 风格排序：会给路径 / 基因附加 posterior mean、UCB、风险臂分数，更适合做“先复核谁、先压制谁”的提醒。
- 现在也能生成一版 `evolution portrait` 风格画像，把优势路径、风险区域、情绪画像、纪律画像压缩成更适合长期观察的卡片。
- 自进化提醒现在不仅会匹配当前标签，还会附加“习惯风险提醒”，比如计划外偏离、情绪失控、重复失误等。
- 自进化提醒现在还会返回：
  - `pre_trade_checklist`：给 OpenClaw 做出手前复核
  - `reflection_prompts`：给 OpenClaw 做轻量反思追问
  - `soft_structure_note`：强调这些基因只是历史索引，不是自动交易规则
- 卖出后回顾的反馈也已开始回流到自进化统计里，用来提示“确认卖飞 / 纪律性卖出被确认”这类经验。
- 计划和交易在落账之后，还可以继续用自然语言补充反思；这些补充会回写原记录，并继续回流到知识库和自进化提醒。
- 对量化 / 半量化记录，当前已支持通过 `decision_context_json.strategy_context` 保留策略条线、因子组和启停主观说明；独立的量化轨迹统计与自进化仍属于下一阶段能力。

## 补充文档

- 已实现能力：`IMPLEMENTED_FEATURES.md`
- 待实现能力：`NOT_IMPLEMENTED_YET.md`
- 统一状态与版本记录：`FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`
- 框架目的与愿景：`FRAMEWORK_PURPOSE_AND_VISION.md`
- 社区愿景：`COMMUNITY_AGENT_LEDGER_VISION.md`
- OpenClaw 技能功能说明：`finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
- 自由文本记账流：`finance-journal-orchestrator/references/intake-workflow.md`
- OpenClaw 会话契约：`finance-journal-orchestrator/references/openclaw-session-contract.md`
- Git / 云端协作建议：`GIT_SYNC_WORKFLOW.md`
- 开源协作说明：`CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `SECURITY.md` / `SUPPORT.md`
- 自进化算法路线：`trade-evolution-engine/references/evolution-algorithms.md`
- 新闻源预设：`finance-info-monitor/references/news-source-presets.md`
