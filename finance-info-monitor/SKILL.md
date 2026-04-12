---
name: finance-info-monitor
description: 负责关注池、关键词与宏观事件的信息监测，以及盘前晨报生成。它是交易复盘账本的辅助模块，不是核心主线；适用于抓取或录入公告/新闻事件、生成每日晨报、检查关注池上一交易日快照，但不输出买卖建议。
---

# Finance Info Monitor

## Read First

- `../finance-journal-orchestrator/references/data-contracts.md`
- `../finance-journal-orchestrator/references/operating-rhythm.md`
- `../finance-journal-orchestrator/references/command-cheatsheet.md`
- `references/news-source-presets.md`

## Primary Commands

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch --start-date 20260409 --end-date 20260410
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url --url "https://example.com/announcements?code=603083" --type announcement --mode html_list --ts-code 603083 --name 剑桥科技 --include-patterns 公告,业绩
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url --url "https://www.cls.cn/telegraph" --type macro --source cls --mode html_timeline --trade-date 20260411
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event add --type announcement --headline "剑桥科技发布新订单" --ts-code 603083 --name 剑桥科技 --priority high --trade-date 20260410
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py brief generate --trade-date 20260410 --fetch-events
```

## Notes

- 优先维护 `watchlist` 与 `keywords`，再刷新事件。
- 个股公告默认继续优先走 Tushare；新闻快讯优先走 URL adapters。
- 这个模块是“锦上添花”，账本主线依然是计划、交易、回顾和体检。
- 抓取失败时不要编造数据，直接记录错误或改用 `event add` 手动补录。
- 现在支持 URL 适配抓取：云端只要能访问网页 / RSS / JSON 接口，就可以通过 `event fetch-url` 或 `url_sources.adapters` 配置落事件。
- 对华尔街见闻 / 金十 / 财联社 / 东方财富 / 同花顺这类快讯页，优先尝试 `html_timeline`。
- 如果页面正文主要塞在脚本 JSON 里，再切到 `html_embedded_json`，或在配置里给 `html_timeline` 加 `fallback_mode=html_embedded_json`。
- 对公告 / 新闻抓取，优先保留原始 `url` 与 `raw_payload`，便于后续复查、去重和二次清洗。
- 输出只做“信息不遗漏”，不做投资判断。
