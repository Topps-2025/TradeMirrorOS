# 新闻源 URL 预设

更新日期：2026-04-11

这份文档用来说明：

- 个股公告继续优先走 Tushare
- 宏观 / 快讯 / 电报类新闻优先走 URL adapters
- 当前已内置哪些站点预设
- 真实联网验证结果如何

## 一、分工原则

### 1. 个股公告

优先走 Tushare：

- `anns_d`
- 配合本地 `watchlist`

原因：

- 标的映射更稳定
- 去重更容易
- 对“某只股票的公告”检索更直接

### 2. 宏观 / 快讯 / 电报

优先走 URL 适配：

- 云端只要能访问网页，就能抓
- 不强依赖单一数据供应商
- 更适合 OpenClaw 部署在服务器上的场景

## 二、当前已配置的公开页面

`runtime.example.json` 里提供了预设模板，`runtime.local.json` 里已经放了可直接启用的配置。

当前核心站点与 parser 如下：

1. 华尔街见闻
   - URL: `https://wallstreetcn.com/live`
   - parser: `html_embedded_json`
   - 说明: 页面主体在脚本 JSON 里，适合 SSR 提取

2. 财联社电报
   - URL: `https://www.cls.cn/telegraph`
   - parser: `html_timeline`
   - fallback: `html_embedded_json`

3. 金十数据
   - URL: `https://www.jin10.com/`
   - parser: `html_timeline`

4. 东方财富快讯
   - URL: `https://np-weblist.eastmoney.com/comm/web/getFastNewsZhibo?...`
   - parser: `json_list`

5. 同花顺实时快讯
   - URL: `http://stock.10jqka.com.cn/thsgd/ywjh.js`
   - parser: `json_list`
   - 说明: feed 形态是 `var thsRss = {...};`，当前已兼容 JS 赋值对象解析

额外模板：

- `10jqka-economic-calendar`
- `demo-macro-rss`

## 三、这一版为了“云端只给网址也能抓”补的能力

- 自动尝试 `utf-8 / utf-8-sig / gb18030 / gbk / big5`，降低中文站点乱码概率
- 自动忽略脚本、样式和低价值噪音文本
- `html_timeline` 会组合日期标记和时间标记，让事件时间更完整
- 增加低价值文本过滤，默认压掉 `ICP备`、`举报电话`、`登录后查看更多快讯`、`TradingHero` 这类噪音
- 增加 `html_embedded_json`，适配 SSR / Next.js / 脚本灌数据页面
- 增加 JSONP 解析
- 增加 JS 对象赋值解析，适配同花顺这类 `var xxx = {...};` feed

## 四、真实联网验证结果

2026-04-11 执行：

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py --root .\_runtime_live_verify_20260411_v4 --disable-market-data event fetch --start-date 20260411 --end-date 20260411
```

结果：

- 总插入：`187`
- 错误数：`0`
- `wallstreetcn-live-global`: `13`
- `cls-telegraph`: `22`
- `jin10-home-flash`: `52`
- `eastmoney-kuaixun`: `50`
- `10jqka-realtime-news`: `50`

这说明当前 5 个展示优先新闻源都已经可以在真实联网环境下直接产出事件流。

## 五、推荐启用方式

不要直接改 `runtime.example.json`。

建议在：

- `finance-journal-orchestrator/config/runtime.local.json`

里只保留你要启用的 adapters，并把 `enabled` 设成 `true`。

当前仓库默认已经启用：

- `wallstreetcn-live-global`
- `cls-telegraph`
- `jin10-home-flash`
- `eastmoney-kuaixun`
- `10jqka-realtime-news`

## 六、轮询与晨报节奏建议

推荐的 `schedules` 配置：

```json
{
  "event_fetch_times": ["07:55", "12:30", "15:10", "20:30"],
  "fetch_events_before_morning_brief": true,
  "morning_brief_time": "08:00"
}
```

这样可以做到：

1. 盘前先抓一轮快讯
2. 晨报前再保证一次补抓
3. 盘中 / 盘后继续累积展示素材

## 七、快速验证命令

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url `
  --url "https://www.cls.cn/telegraph" `
  --type macro `
  --source cls `
  --mode html_timeline `
  --trade-date 20260411
```

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url `
  --url "https://np-weblist.eastmoney.com/comm/web/getFastNewsZhibo?client=web&biz=web_724&pageSize=50" `
  --type macro `
  --source eastmoney `
  --mode json_list `
  --trade-date 20260411 `
  --items-path data.fastNewsList `
  --headline-path title `
  --summary-path summary `
  --published-path showTime
```

```powershell
python .\finance-journal-orchestrator\scripts\finance_journal_cli.py event fetch-url `
  --url "http://stock.10jqka.com.cn/thsgd/ywjh.js" `
  --type macro `
  --source 10jqka `
  --mode json_list `
  --trade-date 20260411 `
  --items-path item `
  --headline-path title `
  --summary-path content `
  --published-path pubDate
```

## 八、后续扩展建议

如果未来新增别的站点，优先判断：

1. 是时间轴页，还是链接列表页
2. 是否存在公开 RSS / JSON
3. 页面是否严重依赖前端渲染
4. 是否需要登录态 / cookie / 浏览器态

然后再决定用：

- `html_timeline`
- `html_list`
- `rss`
- `json_list`
- `html_embedded_json`

还是单独做站点专用适配。
