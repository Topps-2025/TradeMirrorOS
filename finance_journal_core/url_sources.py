from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

from .market_data import normalize_datetime_text, normalize_trade_date, normalize_ts_code


WHITESPACE_RE = re.compile(r"\s+")
HIGH_PRIORITY_WORDS = ("业绩", "预告", "合同", "停牌", "复牌", "减持", "增持", "监管", "问询", "CPI", "PPI", "降准", "美联储")
DATE_PATTERNS = (
    re.compile(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)"),
    re.compile(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})"),
    re.compile(r"(20\d{6}\d{6})"),
    re.compile(r"(20\d{6})"),
)
TIMELINE_TIME_RE = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")
TIMELINE_DATE_RE = re.compile(r"^(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2})$")
PARTIAL_TIMELINE_DATE_RE = re.compile(r"^(?P<month>\d{1,2})[-/](?P<day>\d{1,2})$")
CHARSET_RE = re.compile(r"charset\s*=\s*['\"]?(?P<charset>[A-Za-z0-9._-]+)", re.IGNORECASE)
SCRIPT_BLOCK_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.IGNORECASE | re.DOTALL)
SCRIPT_ASSIGN_RE = re.compile(r"(?:window|self|globalThis)?\.?[A-Za-z_$][\w$\.]*\s*=\s*", re.MULTILINE)
JS_OBJECT_KEY_RE = re.compile(r'([{\[,]\s*)([A-Za-z_$][\w$]*)(\s*:)')
TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
MOJIBAKE_HINTS = ("锟斤拷", "锟", "鈥", "銆", "鍗", "闄", "鐨", "\ufffd")
LOW_VALUE_PATTERNS = (
    re.compile(r"^(?:打开|下载).{0,12}APP", re.IGNORECASE),
    re.compile(r"^(?:登录后|登录即可|注册后).{0,16}(?:查看|查看更多|阅读全文|快讯|内容)", re.IGNORECASE),
    re.compile(r"^(?:登录|注册|订阅|详情|更多|返回首页|点击查看更多|查看更多快讯)$", re.IGNORECASE),
    re.compile(r"(?:ICP备|版权|版权所有|互联网新闻信息服务许可证|举报电话|客服邮箱|联系我们|隐私政策|用户协议|免责声明|关于我们|广告合作)"),
    re.compile(r"^(?:TradingHero|Home|Prev|Next|Live|Telegraph|Flash|More|Detail|Details)$", re.IGNORECASE),
    re.compile(r"^(?:分享|收藏|相关链接|推荐阅读|换一批|扫描添加|提交|阅)$"),
    re.compile(r"^跟踪.+动态$"),
    re.compile(r"^[（）()]+$"),
    re.compile(r"^解锁直达[>＞]+$"),
    re.compile(r"^点击查看全文$"),
    re.compile(r"^©\s*\d{4}"),
)


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return ""


def _text(value: Any) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "")).strip()


def _fold_text(value: Any) -> str:
    return _text(value).casefold()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_patterns(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(item) for item in re.split(r"[,\n|;；]+", str(value)) if _text(item)]


def _contains_pattern(text: str, patterns: list[str]) -> bool:
    lowered = _fold_text(text)
    return any(_fold_text(pattern) in lowered for pattern in patterns if _fold_text(pattern))


def _guess_priority(headline: str, summary: str, default_priority: str = "normal") -> str:
    combined = f"{headline} {summary}"
    if any(word in combined for word in HIGH_PRIORITY_WORDS):
        return "high"
    return default_priority or "normal"


def _looks_like_json(text: str, content_type: str) -> bool:
    body = text.lstrip()
    if "json" in content_type.lower():
        return True
    return body.startswith("{") or body.startswith("[")


def _looks_like_xml(text: str, content_type: str) -> bool:
    body = text.lstrip().lower()
    if any(token in content_type.lower() for token in ("xml", "rss", "atom")):
        return True
    return body.startswith("<?xml") or body.startswith("<rss") or body.startswith("<feed")


def _header_charset(content_type: str) -> str:
    match = CHARSET_RE.search(content_type or "")
    return _text(match.group("charset")) if match else ""


def _meta_charset(payload: bytes) -> str:
    head = payload[:4096].decode("ascii", errors="ignore")
    match = CHARSET_RE.search(head)
    return _text(match.group("charset")) if match else ""


def _decode_quality_score(text: str) -> float:
    sample = text[:12000]
    cjk = sum(1 for char in sample if "\u4e00" <= char <= "\u9fff")
    printable = sum(1 for char in sample if char.isprintable())
    weird = sum(sample.count(token) for token in MOJIBAKE_HINTS)
    return float(printable + cjk * 2 - weird * 20)


def _decode_payload(payload: bytes, content_type: str) -> str:
    candidates = []
    for encoding in (_header_charset(content_type), _meta_charset(payload), "utf-8", "utf-8-sig", "gb18030", "gbk", "big5"):
        normalized = _text(encoding).lower()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    best_text = ""
    best_score = float("-inf")
    for encoding in candidates:
        try:
            decoded = payload.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
        score = _decode_quality_score(decoded)
        if score > best_score:
            best_text = decoded
            best_score = score
    if best_text:
        return best_text
    fallback = candidates[0] if candidates else "utf-8"
    return payload.decode(fallback, errors="replace")


def _load_json_loose(text: str) -> Any:
    body = _text(text)
    if not body:
        raise json.JSONDecodeError("empty json payload", text, 0)
    try:
        return json.loads(body)
    except json.JSONDecodeError as first_error:
        start = _first_json_start(body)
        snippet = _extract_balanced_json(body, start)
        candidates: list[str] = []
        if snippet:
            candidates.append(snippet)
            normalized = JS_OBJECT_KEY_RE.sub(r'\1"\2"\3', snippet)
            normalized = TRAILING_COMMA_RE.sub(r"\1", normalized)
            normalized = re.sub(r"\bundefined\b", "null", normalized)
            if normalized != snippet:
                candidates.append(normalized)
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise first_error


def _coalesce_path(item: Any, paths: list[str]) -> Any:
    for path in paths:
        value = _extract_path(item, path)
        if value not in (None, "", [], {}):
            return value
    return ""


def _extract_path(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current: Any = payload
    for raw_token in str(path).split("."):
        token = raw_token.strip()
        if not token:
            continue
        if token == "[]":
            if not isinstance(current, list):
                return []
            return current
        match = re.fullmatch(r"([^\[\]]+)(?:\[(\d+)\])?", token)
        if not match:
            return None
        key = match.group(1)
        index = match.group(2)
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if index is not None:
            if not isinstance(current, list):
                return None
            idx = int(index)
            if idx >= len(current):
                return None
            current = current[idx]
    return current


def _normalize_url(base_url: str, href: str) -> str:
    href_text = _text(href)
    if not href_text:
        return ""
    if href_text.startswith(("javascript:", "mailto:", "#")):
        return ""
    return urllib.parse.urljoin(base_url, href_text)


def _guess_datetime(*values: Any) -> str:
    for value in values:
        if isinstance(value, (int, float)) and value:
            return _epoch_to_datetime_text(int(value))
        text = _text(value)
        if not text:
            continue
        if text.isdigit() and len(text) in {10, 13}:
            raw = int(text)
            if len(text) == 13:
                raw //= 1000
            return _epoch_to_datetime_text(raw)
        for pattern in DATE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            candidate = match.group(1).replace("T", " ").replace("/", "-")
            return normalize_datetime_text(candidate)
    return ""


def _epoch_to_datetime_text(timestamp: int) -> str:
    shanghai = timezone(timedelta(hours=8))
    return datetime.fromtimestamp(int(timestamp), tz=shanghai).strftime("%Y-%m-%d %H:%M:%S")


def _strip_source_prefix(text: str) -> str:
    value = _text(text)
    patterns = [
        r"^(财联社|金十数据|华尔街见闻|东方财富|同花顺)[0-9一二三四五六七八九十月日\-\.:：\s]*[电讯日讯快讯，,:： ]*",
        r"^(来源[:：]\s*[^ ]+)\s*",
    ]
    for pattern in patterns:
        value = re.sub(pattern, "", value)
    return _text(value)


def _site_specific_cleanup(source: str, headline: str, summary: str) -> tuple[str, str]:
    src = _text(source).lower()
    clean_headline = _text(headline)
    clean_summary = _text(summary)

    bracket_match = re.match(r"^[\[【〖](.+?)[\]】〗]\s*(.*)$", clean_headline)
    if bracket_match:
        clean_headline = _text(bracket_match.group(1))
        trailing = _strip_source_prefix(bracket_match.group(2))
        if trailing:
            clean_summary = _text(f"{trailing} {clean_summary}")

    if src in {"cls", "jin10", "wallstreetcn", "eastmoney", "10jqka"}:
        clean_headline = _strip_source_prefix(clean_headline)
        clean_summary = _strip_source_prefix(clean_summary)

    if clean_headline.endswith(("。", "；", ";")):
        clean_headline = clean_headline.rstrip("。；; ")
    if clean_summary == clean_headline:
        clean_summary = ""
    elif clean_summary.startswith(f"{clean_headline} "):
        clean_summary = _text(clean_summary[len(clean_headline) :])

    return clean_headline, clean_summary


def _normalize_timeline_date(value: str, fallback_trade_date: str) -> str:
    token = _text(value)
    if not token:
        return normalize_trade_date(fallback_trade_date) if fallback_trade_date else ""
    if re.fullmatch(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", token):
        return normalize_trade_date(token)
    match = PARTIAL_TIMELINE_DATE_RE.fullmatch(token)
    fallback = normalize_trade_date(fallback_trade_date) if fallback_trade_date else ""
    if not match or not fallback:
        return fallback
    return f"{fallback[:4]}{int(match.group('month')):02d}{int(match.group('day')):02d}"


def _combine_timeline_datetime(date_token: str, time_token: str, fallback_trade_date: str) -> str:
    normalized_date = _normalize_timeline_date(date_token, fallback_trade_date)
    normalized_time = _text(time_token)
    if normalized_date and TIMELINE_TIME_RE.fullmatch(normalized_time):
        if len(normalized_time) == 5:
            normalized_time = f"{normalized_time}:00"
        return normalize_datetime_text(
            f"{normalized_date[:4]}-{normalized_date[4:6]}-{normalized_date[6:8]} {normalized_time}"
        )
    if normalized_date:
        return normalize_datetime_text(normalized_date)
    return _guess_datetime(date_token, time_token, fallback_trade_date)


def _first_json_start(text: str, start: int = 0) -> int:
    for index in range(max(start, 0), len(text)):
        if text[index] in "{[":
            return index
    return -1


def _extract_balanced_json(text: str, start: int) -> str:
    if start < 0 or start >= len(text) or text[start] not in "{[":
        return ""
    stack = [text[start]]
    in_string = False
    quote_char = ""
    escaped = False
    pairs = {"{": "}", "[": "]"}
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote_char:
                in_string = False
            continue
        if char in {'"', "'"}:
            in_string = True
            quote_char = char
            continue
        if char in "{[":
            stack.append(char)
            continue
        if char in "}]":
            if not stack:
                return ""
            opener = stack.pop()
            if pairs.get(opener) != char:
                return ""
            if not stack:
                return text[start : index + 1]
    return ""


class _SimpleHTMLCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.anchors: list[dict[str, str]] = []
        self.times: list[str] = []
        self.paragraphs: list[str] = []
        self.text_chunks: list[str] = []
        self._in_title = False
        self._current_anchor_href = ""
        self._current_anchor_text: list[str] = []
        self._current_time_text: list[str] = []
        self._current_paragraph_text: list[str] = []
        self._in_time = False
        self._in_paragraph = False
        self._skip_text_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._skip_text_depth += 1
            return
        if self._skip_text_depth:
            return
        if lowered == "title":
            self._in_title = True
        elif lowered == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if key:
                self.meta[key] = _text(attr_map.get("content", ""))
        elif lowered == "a":
            self._current_anchor_href = attr_map.get("href", "")
            self._current_anchor_text = []
        elif lowered == "time":
            self._in_time = True
            self._current_time_text = []
            if attr_map.get("datetime"):
                self.times.append(_text(attr_map.get("datetime")))
        elif lowered in {"p", "li", "article"}:
            self._in_paragraph = True
            self._current_paragraph_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            if self._skip_text_depth:
                self._skip_text_depth -= 1
            return
        if self._skip_text_depth:
            return
        if lowered == "title":
            self._in_title = False
        elif lowered == "a":
            headline = _text("".join(self._current_anchor_text))
            if headline:
                self.anchors.append({"href": self._current_anchor_href, "text": headline})
            self._current_anchor_href = ""
            self._current_anchor_text = []
        elif lowered == "time":
            self._in_time = False
            content = _text("".join(self._current_time_text))
            if content:
                self.times.append(content)
            self._current_time_text = []
        elif lowered in {"p", "li", "article"}:
            self._in_paragraph = False
            content = _text("".join(self._current_paragraph_text))
            if content:
                self.paragraphs.append(content)
            self._current_paragraph_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_text_depth:
            return
        chunk = _text(data)
        if chunk and not self._in_title:
            self.text_chunks.append(chunk)
        if self._in_title:
            self.title_parts.append(data)
        if self._current_anchor_href:
            self._current_anchor_text.append(data)
        if self._in_time:
            self._current_time_text.append(data)
        if self._in_paragraph:
            self._current_paragraph_text.append(data)

    @property
    def title(self) -> str:
        return _text("".join(self.title_parts))


class UrlEventFetcher:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def _headers(self) -> dict[str, str]:
        user_agent = str(self.config.get("user_agent") or "Mozilla/5.0 (FinanceJournalBot)")
        return {
            "User-Agent": user_agent,
            "Accept": "text/html,application/json,application/xml,text/xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        }

    def fetch_text(self, url: str) -> tuple[str, str, str]:
        timeout = int(self.config.get("timeout_seconds") or 20)
        request = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            content_type = str(response.headers.get("Content-Type") or "")
            text = _decode_payload(payload, content_type)
            return text, response.geturl(), content_type

    def fetch_url_events(self, url: str, adapter: dict[str, Any], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        text, final_url, content_type = self.fetch_text(url)
        parser_cfg = dict(adapter.get("parser") or {})
        mode = str(parser_cfg.get("mode") or adapter.get("mode") or "auto").strip().lower()
        if mode == "auto":
            if _looks_like_json(text, content_type):
                mode = "json_list"
            elif _looks_like_xml(text, content_type):
                mode = "rss"
            else:
                mode = "html_list" if _as_bool(parser_cfg.get("prefer_list"), default=True) else "html_article"
        rows = self._parse_events_by_mode(text, final_url, adapter, context or {}, mode)
        fallback_mode = str(parser_cfg.get("fallback_mode") or "").strip().lower()
        if rows or not fallback_mode or fallback_mode == mode:
            return rows
        fallback_parser = dict(parser_cfg)
        fallback_parser.update(dict(parser_cfg.get("fallback_parser") or {}))
        fallback_parser["mode"] = fallback_mode
        fallback_adapter = {**adapter, "parser": fallback_parser}
        return self._parse_events_by_mode(text, final_url, fallback_adapter, context or {}, fallback_mode)

    def _parse_events_by_mode(
        self,
        text: str,
        source_url: str,
        adapter: dict[str, Any],
        context: dict[str, Any],
        mode: str,
    ) -> list[dict[str, Any]]:
        if mode == "json_list":
            return self._parse_json_list(text, source_url, adapter, context)
        if mode == "rss":
            return self._parse_rss(text, source_url, adapter, context)
        if mode == "html_timeline":
            return self._parse_html_timeline(text, source_url, adapter, context)
        if mode == "html_article":
            return self._parse_html_article(text, source_url, adapter, context)
        if mode == "html_embedded_json":
            return self._parse_html_embedded_json(text, source_url, adapter, context)
        return self._parse_html_list(text, source_url, adapter, context)

    def fetch_configured_events(
        self,
        adapters: list[dict[str, Any]],
        watchlist: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        results = {
            "attempted": 0,
            "fetched": 0,
            "errors": [],
            "adapter_results": [],
            "events": [],
        }
        for adapter in adapters:
            if not _as_bool(adapter.get("enabled"), default=True):
                continue
            contexts = self._expand_contexts(adapter, watchlist, keywords, start_date, end_date)
            adapter_name = str(adapter.get("name") or adapter.get("source") or adapter.get("event_type") or "url_adapter")
            adapter_total = 0
            adapter_errors = 0
            for context in contexts:
                rendered_url = self._render_url(adapter, context)
                if not rendered_url:
                    continue
                results["attempted"] += 1
                try:
                    events = self.fetch_url_events(rendered_url, adapter, context=context)
                    results["events"].extend(events)
                    results["fetched"] += len(events)
                    adapter_total += len(events)
                except Exception as exc:
                    adapter_errors += 1
                    label = context.get("label") or context.get("keyword") or context.get("ts_code") or rendered_url
                    results["errors"].append(f"url_adapter:{adapter_name}:{label} -> {exc}")
            results["adapter_results"].append(
                {
                    "name": adapter_name,
                    "attempted": len(contexts),
                    "fetched": adapter_total,
                    "errors": adapter_errors,
                }
            )
        return results

    def _expand_contexts(
        self,
        adapter: dict[str, Any],
        watchlist: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        kind = str(adapter.get("kind") or "static").strip().lower()
        base_context = self._base_context({}, start_date, end_date)
        if kind == "watchlist":
            return [self._base_context(item, start_date, end_date) for item in watchlist]
        if kind == "keyword":
            return [self._base_context(item, start_date, end_date) for item in keywords]
        if kind == "macro":
            return [self._base_context({"label": "macro"}, start_date, end_date)]
        contexts = adapter.get("contexts") or [{}]
        if isinstance(contexts, dict):
            contexts = [contexts]
        return [self._base_context(item, start_date, end_date) for item in contexts] or [base_context]

    def _base_context(self, item: dict[str, Any], start_date: str, end_date: str) -> dict[str, Any]:
        ts_code = normalize_ts_code(item.get("ts_code") or "") if item.get("ts_code") else ""
        symbol = ts_code.split(".", 1)[0] if ts_code else _text(item.get("symbol"))
        keyword = _text(item.get("keyword"))
        name = _text(item.get("name"))
        now_ms = str(int(datetime.now(tz=timezone(timedelta(hours=8))).timestamp() * 1000))
        context = {
            "ts_code": ts_code,
            "symbol": symbol,
            "name": name,
            "keyword": keyword,
            "label": _text(item.get("label") or keyword or name or ts_code),
            "start_date": normalize_trade_date(start_date),
            "end_date": normalize_trade_date(end_date),
            "trade_date": normalize_trade_date(end_date),
            "now_ms": now_ms,
        }
        for key, value in list(context.items()):
            if isinstance(value, str):
                context[f"{key}_q"] = urllib.parse.quote(value)
        return context

    def _render_url(self, adapter: dict[str, Any], context: dict[str, Any]) -> str:
        template = str(adapter.get("url_template") or adapter.get("url") or "").strip()
        if not template:
            return ""
        return template.format_map(_SafeFormatDict(context))

    def _parse_json_list(self, text: str, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        payload = _load_json_loose(text)
        return self._parse_json_payload(payload, source_url, adapter, context)

    def _parse_json_payload(self, payload: Any, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        parser_cfg = dict(adapter.get("parser") or {})
        items_path = str(parser_cfg.get("items_path") or "").strip()
        item_url_template = str(parser_cfg.get("item_url_template") or "").strip()
        items = _extract_path(payload, items_path) if items_path else payload
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        rows: list[dict[str, Any]] = []
        limit = int(parser_cfg.get("limit") or 20)
        for item in items[: max(limit, 0)]:
            headline_paths = [path for path in [str(parser_cfg.get("headline_path") or "").strip(), "headline", "title", "name"] if path]
            summary_paths = [path for path in [str(parser_cfg.get("summary_path") or "").strip(), "summary", "content", "desc", "abstract"] if path]
            published_paths = [
                path
                for path in [
                    str(parser_cfg.get("published_path") or "").strip(),
                    "published_at",
                    "pub_time",
                    "datetime",
                    "date",
                    "time",
                ]
                if path
            ]
            url_paths = [path for path in [str(parser_cfg.get("url_path") or "").strip(), "url", "link", "article_url"] if path]
            headline = _text(
                _coalesce_path(
                    item,
                    headline_paths,
                )
            )
            if not headline:
                continue
            summary = _text(
                _coalesce_path(
                    item,
                    summary_paths,
                )
            )
            published = _guess_datetime(
                _coalesce_path(item, published_paths)
            )
            event_url = _text(
                _coalesce_path(
                    item,
                    url_paths,
                )
            )
            if not event_url and item_url_template and isinstance(item, dict):
                event_url = _normalize_url(
                    source_url,
                    item_url_template.format_map(
                        _SafeFormatDict(
                            {
                                key: _text(value) if not isinstance(value, (dict, list)) else value
                                for key, value in item.items()
                            }
                        )
                    ),
                )
            if event_url:
                event_url = _normalize_url(source_url, event_url)
            row = self._build_event_row(
                adapter=adapter,
                context=context,
                headline=headline,
                summary=summary,
                published_at=published,
                source_url=event_url or source_url,
                raw_payload=item,
            )
            rows.append(row)
        return rows

    def _parse_rss(self, text: str, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        root = ET.fromstring(text)
        entries = root.findall(".//item")
        if not entries:
            entries = root.findall(".//{*}entry")
        rows: list[dict[str, Any]] = []
        limit = int((adapter.get("parser") or {}).get("limit") or 20)
        for entry in entries[: max(limit, 0)]:
            title = _text(entry.findtext("title") or entry.findtext("{*}title"))
            if not title:
                continue
            summary = _text(
                entry.findtext("description")
                or entry.findtext("{*}summary")
                or entry.findtext("{*}content")
            )
            published = _guess_datetime(
                entry.findtext("pubDate"),
                entry.findtext("{*}published"),
                entry.findtext("{*}updated"),
            )
            link = _text(entry.findtext("link") or entry.findtext("{*}link"))
            if not link:
                link_node = entry.find("{*}link")
                if link_node is not None:
                    link = _text(link_node.attrib.get("href"))
            rows.append(
                self._build_event_row(
                    adapter=adapter,
                    context=context,
                    headline=title,
                    summary=summary,
                    published_at=published,
                    source_url=_normalize_url(source_url, link) or source_url,
                    raw_payload={"title": title, "summary": summary, "published": published, "link": link},
                )
            )
        return rows

    def _parse_html_article(self, text: str, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        collector = _SimpleHTMLCollector()
        collector.feed(text)
        parser_cfg = dict(adapter.get("parser") or {})
        ignore_tokens = self._timeline_ignore_tokens(parser_cfg)
        drop_patterns = _split_patterns(parser_cfg.get("drop_patterns"))
        headline = _text(
            collector.meta.get("og:title")
            or collector.meta.get("twitter:title")
            or collector.title
        )
        if self._is_low_value_chunk(headline, ignore_tokens, drop_patterns):
            return []
        paragraphs = [
            chunk
            for chunk in collector.paragraphs
            if not self._is_low_value_chunk(chunk, ignore_tokens, drop_patterns)
        ]
        if not headline:
            return []
        summary = _text(
            collector.meta.get("description")
            or collector.meta.get("og:description")
            or " ".join(paragraphs[:2])
        )
        published = _guess_datetime(
            collector.meta.get("article:published_time"),
            collector.meta.get("og:published_time"),
            collector.meta.get("publishdate"),
            collector.meta.get("pubdate"),
            collector.meta.get("date"),
            " ".join(collector.times[:3]),
        )
        return [
            self._build_event_row(
                adapter=adapter,
                context=context,
                headline=headline,
                summary=summary,
                published_at=published,
                source_url=source_url,
                raw_payload={
                    "title": collector.title,
                    "meta": collector.meta,
                    "times": collector.times[:5],
                },
            )
        ]

    def _script_matches_markers(self, attrs: str, body: str, markers: list[str]) -> bool:
        if not markers:
            return True
        haystack = _fold_text(f"{attrs} {body}")
        return any(_fold_text(marker) in haystack for marker in markers if _fold_text(marker))

    def _extract_json_snippets_from_script(self, attrs: str, body: str, markers: list[str]) -> list[str]:
        snippets: list[str] = []
        seen: set[str] = set()
        if not self._script_matches_markers(attrs, body, markers):
            return []

        def append_candidate(start_pos: int) -> None:
            start = _first_json_start(body, start_pos)
            if start < 0:
                return
            snippet = _extract_balanced_json(body, start)
            if snippet and snippet not in seen:
                seen.add(snippet)
                snippets.append(snippet)

        if "application/json" in attrs.casefold():
            append_candidate(0)

        folded_body = _fold_text(body)
        for marker in markers:
            token = _fold_text(marker)
            if not token:
                continue
            position = folded_body.find(token)
            while position >= 0:
                append_candidate(position + len(token))
                position = folded_body.find(token, position + len(token))

        for match in SCRIPT_ASSIGN_RE.finditer(body):
            append_candidate(match.end())

        if not snippets:
            append_candidate(0)
        return snippets

    def _parse_html_embedded_json(self, text: str, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        parser_cfg = dict(adapter.get("parser") or {})
        markers = _split_patterns(parser_cfg.get("script_markers"))
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        limit = int(parser_cfg.get("limit") or 20)
        for match in SCRIPT_BLOCK_RE.finditer(text):
            attrs = match.group("attrs") or ""
            body = match.group("body") or ""
            for snippet in self._extract_json_snippets_from_script(attrs, body, markers):
                try:
                    payload = json.loads(snippet)
                except json.JSONDecodeError:
                    continue
                for row in self._parse_json_payload(payload, source_url, adapter, context):
                    identity = (_text(row.get("headline")), _text(row.get("url")))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    rows.append(row)
                    if len(rows) >= limit:
                        return rows
        return rows

    def _timeline_ignore_tokens(self, parser_cfg: dict[str, Any]) -> set[str]:
        tokens = {
            "APP",
            "Open",
            "Download",
            "More",
            "Live",
            "Telegraph",
            "News",
            "Flash",
            "Details",
            "Detail",
            "Share",
            "Login",
            "Register",
            "Home",
            "Back",
            "Prev",
            "Next",
        }
        tokens.update(_split_patterns(parser_cfg.get("ignore_tokens")))
        return {item for item in (_fold_text(token) for token in tokens) if item}

    def _is_low_value_chunk(self, text: str, ignore_tokens: set[str] | None = None, drop_patterns: list[str] | None = None) -> bool:
        value = _text(text)
        if not value:
            return True
        folded = value.casefold()
        if ignore_tokens and folded in ignore_tokens:
            return True
        if drop_patterns and _contains_pattern(value, drop_patterns):
            return True
        return any(pattern.search(value) for pattern in LOW_VALUE_PATTERNS)

    def _looks_like_timeline_marker(self, chunk: str) -> bool:
        text = _text(chunk)
        if not text:
            return False
        return bool(TIMELINE_TIME_RE.fullmatch(text) or TIMELINE_DATE_RE.fullmatch(text))

    def _timeline_headline_ok(
        self,
        chunk: str,
        include_patterns: list[str],
        exclude_patterns: list[str],
        min_length: int,
        ignore_tokens: set[str],
        drop_patterns: list[str],
    ) -> bool:
        text = _text(chunk)
        if len(text) < min_length:
            return False
        if TIMELINE_TIME_RE.fullmatch(text) or TIMELINE_DATE_RE.fullmatch(text):
            return False
        if self._is_low_value_chunk(text, ignore_tokens, drop_patterns):
            return False
        if include_patterns and not _contains_pattern(text, include_patterns):
            return False
        if exclude_patterns and _contains_pattern(text, exclude_patterns):
            return False
        return True

    def _looks_like_summary_chunk(
        self,
        chunk: str,
        headline: str,
        include_patterns: list[str],
        exclude_patterns: list[str],
        min_length: int,
        ignore_tokens: set[str],
        drop_patterns: list[str],
    ) -> bool:
        text = _text(chunk)
        if not text or text == headline or self._looks_like_timeline_marker(text):
            return False
        if self._is_low_value_chunk(text, ignore_tokens, drop_patterns):
            return False
        if text.endswith(("。", "！", "？", "；", ";", ".", "!", "?")):
            return True
        if len(text) >= max(min_length * 2, 24):
            return True
        if "：" in text or ":" in text:
            return True
        if include_patterns and not _contains_pattern(text, include_patterns) and not (exclude_patterns and _contains_pattern(text, exclude_patterns)):
            return True
        return False

    def _parse_html_timeline(self, text: str, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        collector = _SimpleHTMLCollector()
        collector.feed(text)
        parser_cfg = dict(adapter.get("parser") or {})
        include_patterns = _split_patterns(parser_cfg.get("include_patterns"))
        exclude_patterns = _split_patterns(parser_cfg.get("exclude_patterns"))
        drop_patterns = _split_patterns(parser_cfg.get("drop_patterns"))
        ignore_tokens = self._timeline_ignore_tokens(parser_cfg)
        min_length = int(parser_cfg.get("min_headline_length") or 8)
        summary_lines = int(parser_cfg.get("summary_lines") or 2)
        limit = int(parser_cfg.get("limit") or 20)
        chunks = [_text(item) for item in collector.text_chunks if _text(item)]
        rows: list[dict[str, Any]] = []
        fallback_trade_date = normalize_trade_date(context.get("trade_date") or context.get("end_date") or "")
        current_date = fallback_trade_date
        current_time = ""
        index = 0
        while index < len(chunks):
            chunk = chunks[index]
            if self._looks_like_timeline_marker(chunk):
                if TIMELINE_TIME_RE.fullmatch(chunk):
                    current_time = chunk
                else:
                    current_date = _normalize_timeline_date(chunk, current_date or fallback_trade_date)
                index += 1
                continue
            if self._is_low_value_chunk(chunk, ignore_tokens, drop_patterns):
                index += 1
                continue
            if not self._timeline_headline_ok(chunk, include_patterns, exclude_patterns, min_length, ignore_tokens, drop_patterns):
                index += 1
                continue
            headline = chunk
            summary_bits: list[str] = []
            look_ahead = index + 1
            while look_ahead < len(chunks):
                next_chunk = chunks[look_ahead]
                if self._looks_like_timeline_marker(next_chunk):
                    break
                if self._is_low_value_chunk(next_chunk, ignore_tokens, drop_patterns) or next_chunk == headline:
                    look_ahead += 1
                    continue
                if self._looks_like_summary_chunk(
                    next_chunk,
                    headline,
                    include_patterns,
                    exclude_patterns,
                    min_length,
                    ignore_tokens,
                    drop_patterns,
                ):
                    if len(summary_bits) < summary_lines and next_chunk not in summary_bits:
                        summary_bits.append(next_chunk)
                    look_ahead += 1
                    continue
                if self._timeline_headline_ok(next_chunk, include_patterns, exclude_patterns, min_length, ignore_tokens, drop_patterns):
                    break
                if len(summary_bits) < summary_lines and next_chunk not in summary_bits:
                    summary_bits.append(next_chunk)
                look_ahead += 1
            published = _combine_timeline_datetime(current_date, current_time, fallback_trade_date)
            rows.append(
                self._build_event_row(
                    adapter=adapter,
                    context=context,
                    headline=headline,
                    summary=" ".join(summary_bits[:summary_lines]),
                    published_at=published,
                    source_url=source_url,
                    raw_payload={
                        "headline": headline,
                        "summary": summary_bits[:summary_lines],
                        "time_marker": current_time,
                    },
                )
            )
            index = look_ahead if look_ahead > index else index + 1
            if len(rows) >= limit:
                break
        return rows

    def _parse_html_list(self, text: str, source_url: str, adapter: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        collector = _SimpleHTMLCollector()
        collector.feed(text)
        parser_cfg = dict(adapter.get("parser") or {})
        include_patterns = _split_patterns(parser_cfg.get("include_patterns"))
        exclude_patterns = _split_patterns(parser_cfg.get("exclude_patterns"))
        drop_patterns = _split_patterns(parser_cfg.get("drop_patterns"))
        ignore_tokens = self._timeline_ignore_tokens(parser_cfg)
        same_domain_only = _as_bool(parser_cfg.get("same_domain_only"), default=False)
        follow_article = _as_bool(parser_cfg.get("follow_article"), default=False)
        min_length = int(parser_cfg.get("min_headline_length") or 6)
        limit = int(parser_cfg.get("limit") or 20)
        base_netloc = urllib.parse.urlparse(source_url).netloc
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for anchor in collector.anchors:
            headline = _text(anchor.get("text"))
            if len(headline) < min_length:
                continue
            if self._is_low_value_chunk(headline, ignore_tokens, drop_patterns):
                continue
            if include_patterns and not _contains_pattern(headline, include_patterns):
                continue
            if exclude_patterns and _contains_pattern(headline, exclude_patterns):
                continue
            link = _normalize_url(source_url, anchor.get("href", ""))
            if same_domain_only and link:
                if urllib.parse.urlparse(link).netloc not in {"", base_netloc}:
                    continue
            identity = (headline, link)
            if identity in seen:
                continue
            seen.add(identity)
            if follow_article and link:
                try:
                    article_rows = self.fetch_url_events(
                        link,
                        {
                            **adapter,
                            "parser": {
                                **parser_cfg,
                                "mode": "html_article",
                            },
                        },
                        context=context,
                    )
                    if article_rows:
                        rows.extend(article_rows[:1])
                        if len(rows) >= limit:
                            break
                        continue
                except Exception:
                    pass
            row = self._build_event_row(
                adapter=adapter,
                context=context,
                headline=headline,
                summary="",
                published_at=_guess_datetime(" ".join(collector.times[:3])),
                source_url=link or source_url,
                raw_payload={"headline": headline, "url": link or source_url},
            )
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def _build_event_row(
        self,
        adapter: dict[str, Any],
        context: dict[str, Any],
        headline: str,
        summary: str,
        published_at: str,
        source_url: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        adapter_name = _text(adapter.get("name") or adapter.get("source") or adapter.get("event_type") or "url_adapter")
        event_type = _text(adapter.get("event_type") or "news")
        source = _text(adapter.get("source") or urllib.parse.urlparse(source_url).netloc or adapter_name)
        clean_headline, clean_summary = _site_specific_cleanup(source, headline, summary)
        if not clean_headline:
            clean_headline = _text(headline)
        if not clean_summary:
            clean_summary = _text(summary)
        priority = _guess_priority(clean_headline, clean_summary, default_priority=_text(adapter.get("priority") or "normal"))
        published = normalize_datetime_text(published_at or context.get("end_date") or context.get("trade_date") or "")
        tags = [event_type, adapter_name, "url_fetch"]
        if context.get("keyword"):
            tags.append(_text(context["keyword"]))
        return {
            "event_type": event_type,
            "headline": clean_headline,
            "summary": clean_summary,
            "ts_code": normalize_ts_code(context.get("ts_code") or "") if context.get("ts_code") else "",
            "name": _text(context.get("name")),
            "source": source,
            "priority": priority,
            "published_at": published,
            "trade_date": normalize_trade_date((published[:10] if published else "") or context.get("trade_date") or context.get("end_date")),
            "tags": [item for item in tags if item],
            "url": source_url,
            "raw_payload": {
                "adapter": adapter_name,
                "context": {
                    "ts_code": context.get("ts_code") or "",
                    "symbol": context.get("symbol") or "",
                    "name": context.get("name") or "",
                    "keyword": context.get("keyword") or "",
                    "start_date": context.get("start_date") or "",
                    "end_date": context.get("end_date") or "",
                },
                "payload": raw_payload,
            },
        }
