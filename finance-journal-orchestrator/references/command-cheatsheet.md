# Command Cheatsheet

## CLI

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake parse --mode trade --trade-date 20260410 --text "今天低吸了603083，43.2买的，想博弈CPO回流，盘中有点急，感觉还是拿不稳。"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake apply --mode plan --trade-date 20260410 --text "计划在42.5-43.0低吸603083，止损40，看CPO回流。"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake draft-start --mode trade --trade-date 20260410 --session-key qq:user_a --text "今天买了603083"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake draft-reply <draft_id> --text "43.2"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py intake draft-show --session-key qq:user_a
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py watchlist add 600519 --name 贵州茅台
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py keyword add CPO
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch --start-date 20260411 --end-date 20260411
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url --url "https://www.cls.cn/telegraph" --type macro --source cls --mode html_timeline --trade-date 20260411
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url --url "https://np-weblist.eastmoney.com/comm/web/getFastNewsZhibo?client=web&biz=web_724&pageSize=50" --type macro --source eastmoney --mode json_list --trade-date 20260411 --items-path data.fastNewsList --headline-path title --summary-path summary --published-path showTime
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url --url "http://stock.10jqka.com.cn/thsgd/ywjh.js" --type macro --source 10jqka --mode json_list --trade-date 20260411 --items-path item --headline-path title --summary-path content --published-path pubDate
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py brief generate --trade-date 20260411 --fetch-events
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py plan create --ts-code 603083 --direction buy --thesis "回踩 5 日线参与" --logic-tags 龙头首阴,低吸 --buy-zone 42.5-43.0 --stop-loss 40.0 --holding-period 3-5天 --valid-to 20260415 --decision-context-json '{"user_focus":["剑桥科技","CPO板块"],"observed_signals":["回踩5日线","板块修复"],"position_reason":"试错仓","position_confidence":0.60,"stress_level":3}'
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log --ts-code 603083 --buy-date 20260410 --buy-price 43.2 --thesis "回踩 5 日线参与" --logic-type-tags 龙头首阴,题材驱动 --pattern-tags 均线回踩 --decision-context-json '{"user_focus":["剑桥科技","消费电子链"],"observed_signals":["分时止跌","量能回暖"],"position_reason":"先开两成试错仓","position_confidence":0.62,"stress_level":4}'
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade log --ts-code 600519 --buy-date 20260410 --buy-price 1350 --thesis "高股息修复低吸" --logic-type-tags 低吸 --pattern-tags 均线回踩 --decision-context-json '{"user_focus":["贵州茅台","消费板块"],"observed_signals":["板块企稳"],"position_reason":"低波防守仓先试错","strategy_context":{"strategy_line":"高股息修复低吸","strategy_family":"半量化择时","factor_list":["股息率","板块修复","估值回归"],"factor_selection_reason":"当前更想验证高股息+板块修复的共振窗口","activation_reason":"消费板块企稳后恢复试仓","parameter_version":"dividend_repair_v2","portfolio_role":"低波防守仓","subjective_override":"公告前只开观察仓"}}'
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade import-statement --file .\examples\statement_rows.csv --trade-date 20260415 --session-key qq:user_a
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade incomplete --status open --limit 200
python .\finance-journal-orchestrator\scripts\generate_gateway_followups.py --root .\_runtime --status open --format markdown --output .\_runtime\artifacts\daily\20260415\gateway_followups.md
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py trade close <trade_id> --sell-date 20260415 --sell-price 46.8 --sell-reason "达到预设止盈"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py review run --as-of-date 20260422
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py report health --period-start 20260401 --period-end 20260430 --period-kind monthly
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution report --trade-date 20260415 --lookback-days 365 --min-samples 2
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution portrait --trade-date 20260415 --lookback-days 365 --min-samples 2
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py evolution remind --logic-tags 低吸 --pattern-tags 均线回踩 --market-stage 震荡市 --environment-tags 修复回流
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session turn --session-key qq:user_a --trade-date 20260410 --text "今天买了603083"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session state --session-key qq:user_a
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py session reset --session-key qq:user_a --reason "重新开始"
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault init
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py vault sync --trade-date 20260415
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py schedule --now 2026-04-13T08:05 --dry-run
```

## Gateway

OpenClaw / QQ 侧建议把自然语言先整理为：`域 动作 key=value ...`

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "记账 session=qq:user_a text='今天买了603083' trade_date=20260410"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "会话 接话 session=qq:user_a text='补充：我主要盯的是CPO板块和量能回暖。'"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "计划 新建 code=603083 direction=buy thesis='回踩5日线参与' logic_tags=龙头首阴,低吸 buy_zone=42.5-43.0 stop_loss=40 valid_to=20260415 decision_context_json='{\"user_focus\":[\"剑桥科技\",\"CPO\"],\"observed_signals\":[\"5日线支撑\"],\"position_reason\":\"试错仓\"}'"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "交易 记录 code=603083 buy_date=20260410 buy_price=43.2 thesis='回踩5日线参与' logic_tags=龙头首阴,题材驱动 pattern_tags=均线回踩 decision_context_json='{\"user_focus\":[\"剑桥科技\"],\"observed_signals\":[\"跌不动了\"],\"stress_level\":4}'"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "交易 记录 code=600519 buy_date=20260410 buy_price=1350 thesis='高股息修复低吸' logic_tags=低吸 pattern_tags=均线回踩 decision_context_json='{\"user_focus\":[\"贵州茅台\",\"消费板块\"],\"observed_signals\":[\"板块企稳\"],\"strategy_context\":{\"strategy_line\":\"高股息修复低吸\",\"strategy_family\":\"半量化择时\",\"factor_list\":[\"股息率\",\"板块修复\"],\"activation_reason\":\"消费板块企稳后恢复试仓\",\"parameter_version\":\"dividend_repair_v2\"}}'"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "交易 导入 文件=.\examples\statement_rows.csv session=qq:user_a trade_date=20260415"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "事件 抓取网址 url=https://www.cls.cn/telegraph event_type=macro source=cls mode=html_timeline trade_date=20260411"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "事件 抓取网址 url=http://stock.10jqka.com.cn/thsgd/ywjh.js event_type=macro source=10jqka mode=json_list trade_date=20260411 items_path=item headline_path=title summary_path=content published_path=pubDate"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "进化 画像 trade_date=20260415 lookback_days=365 min_samples=2"
python .\finance-journal-orchestrator\scripts\finance_journal_gateway.py --command "体检 生成 period_start=20260401 period_end=20260430 period_kind=monthly"
```
