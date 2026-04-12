from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .market_data import normalize_trade_date, normalize_ts_code


ENTRY_KEYWORDS = {
    "plan": ("计划", "打算", "准备", "预案", "如果", "想等", "想在", "计划买", "计划卖"),
    "trade": ("买了", "卖了", "买入", "卖出", "开仓", "平仓", "低吸了", "追高了", "止盈", "止损", "清仓"),
}

LOGIC_RULES = [
    (r"(龙头首阴|首阴)", "龙头首阴"),
    (r"(低吸|低位吸|回踩吸)", "低吸"),
    (r"(半路|追涨|追板)", "半路追涨"),
    (r"(题材|主线|热点)", "题材驱动"),
    (r"(基本面|业绩|财报)", "基本面"),
    (r"(反包)", "反包"),
    (r"(补涨)", "补涨"),
    (r"(趋势|波段)", "趋势跟随"),
]

PATTERN_RULES = [
    (r"(均线回踩|回踩5日线|回踩十日线|5日线回踩)", "均线回踩"),
    (r"(箱体突破|平台突破|突破平台)", "箱体突破"),
    (r"(超跌反弹|跌深反弹)", "超跌反弹"),
    (r"(放量突破|放量过前高)", "放量突破"),
    (r"(缩量回踩)", "缩量回踩"),
    (r"(首板|二板|连板)", "连板形态"),
    (r"(分时均线|黄线)", "分时均线"),
]

ENV_RULES = [
    (r"(震荡|横盘)", "震荡市"),
    (r"(主升|强势上涨|强更强)", "主升浪"),
    (r"(高位分歧|分歧)", "高位分歧"),
    (r"(冰点|冰点试错)", "冰点试错"),
    (r"(退潮|弱势下跌)", "弱势下跌市"),
    (r"(修复|回流)", "修复回流"),
]

MISTAKE_RULES = [
    (r"(追高|冲动)", "冲动追高"),
    (r"(拿不住|拿不稳|提前卖)", "拿不稳"),
    (r"(不止损|扛单)", "止损拖延"),
    (r"(计划外|临时起意)", "计划外交易"),
    (r"(满仓|重仓)", "仓位过重"),
    (r"(犹豫|错过)", "犹豫错失"),
]

EMOTION_KEYWORDS = (
    "急",
    "慌",
    "怕",
    "冲动",
    "犹豫",
    "上头",
    "贪",
    "后悔",
    "自信",
)

BUY_HINTS = ("买", "开仓", "上车", "低吸", "建仓", "进了", "进场", "买入")
SELL_HINTS = ("卖", "止盈", "止损", "减仓", "清仓", "卖出", "平仓")
SELL_ZONE_HINTS = ("卖", "止盈", "减仓", "清仓", "卖出", "平仓")
LOGIC_CANDIDATES = ("题材驱动", "技术形态", "基本面", "趋势跟随", "低吸", "半路追涨", "龙头首阴", "补涨")
PATTERN_CANDIDATES = ("均线回踩", "箱体突破", "超跌反弹", "放量突破", "缩量回踩", "分时均线")
ENV_CANDIDATES = ("震荡市", "主升浪", "高位分歧", "冰点试错", "弱势下跌市", "修复回流")
MISTAKE_CANDIDATES = ("冲动追高", "拿不稳", "止损拖延", "计划外交易", "仓位过重", "犹豫错失")
FOCUS_CANDIDATES = ("大盘", "板块", "龙头股", "分时", "盘口", "新闻/公告")
SIGNAL_CANDIDATES = ("跌不动了", "板块企稳", "放量突破", "分时承接增强", "回踩均线不破", "消息催化落地")
POSITION_REASON_CANDIDATES = ("试错仓", "确定性更高", "分批建仓", "摊低成本", "怕错过先上车", "严格控仓")
THESIS_HINTS = (
    "逻辑",
    "理由",
    "博弈",
    "预期",
    "因为",
    "回流",
    "反弹",
    "修复",
    "突破",
    "回踩",
    "低吸",
    "首阴",
    "反包",
    "补涨",
    "趋势",
    "题材",
    "业绩",
    "均线",
    "分歧",
    "cpo",
    "ai",
)
FOCUS_ITEM_PATTERNS = (
    re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{1,12}(?:板块|概念|题材|指数|方向|链)"),
    re.compile(r"(?:大盘|上证|创业板|沪深300|北证50|科创50)"),
    re.compile(r"(?:盘口|分时|均线|量能|成交量|股息率|估值|公告|新闻|研报)"),
)
SIGNAL_HINTS = (
    "抗跌",
    "企稳",
    "止跌",
    "跌不动",
    "放量",
    "缩量",
    "突破",
    "回踩",
    "承接",
    "大单",
    "黄线",
    "翻红",
    "新高",
    "新低",
    "股息率",
    "估值",
    "板块",
    "大盘",
    "公告",
    "新闻",
    "消息",
)
POSITION_REASON_HINTS = (
    "仓位",
    "试错仓",
    "轻仓",
    "重仓",
    "半仓",
    "满仓",
    "确定性",
    "摊低成本",
    "网格",
    "分批",
    "观察仓",
    "底仓",
    "先上一笔",
    "先买一点",
    "怕错过",
)
FOLLOW_UP_MAP = {
    "ts_code": "这笔记录对应哪只股票？请补充 6 位代码或标准 TS 代码。",
    "direction": "这是买入计划、卖出计划，还是做 T 计划？",
    "thesis": "这笔交易/计划最核心的逻辑是什么？请用一句话概括。",
    "stop_loss": "你的止损条件是什么？最好给出价格或触发条件。",
    "buy_date": "实际买入日期是什么？",
    "buy_price": "实际买入价格是多少？",
    "sell_date": "实际卖出日期是什么？",
    "sell_price": "实际卖出价格是多少？",
}
SOFT_STRUCTURE_NOTE = "这些标签只用于索引、检索和统计，不用于自动下单或替代你的主观判断。"
FIELD_PURPOSES = {
    "ts_code": "先锁定标的，避免后续标签和复盘关联错对象。",
    "direction": "区分这是买入计划、卖出计划还是做 T，方便后续统计计划类型。",
    "thesis": "保留这笔交易当时最核心的一句话逻辑，供后续检索、对比和自进化使用。",
    "stop_loss": "记录纪律边界，后续可用于分析止损执行和计划偏离。",
    "buy_date": "补齐买入事实时间，便于和市场环境、计划、回顾关联。",
    "buy_price": "补齐买入事实价格，便于落账、算收益和衡量执行偏差。",
    "sell_date": "补齐卖出事实时间，便于闭环回顾和卖点验证。",
    "sell_price": "补齐卖出事实价格，便于闭环收益、卖飞/逃顶分析。",
    "buy_zone": "记录计划中的理想买点区间，用于计划执行偏差分析。",
    "sell_zone": "记录计划中的理想卖点区间，用于卖点执行偏差分析。",
    "logic_tags": "这是软结构标签，只为后续检索“你常做哪类思路”和做条件统计。",
    "pattern_tags": "这是软结构标签，只为后续检索相似形态，不会自动变成交易规则。",
    "environment_tags": "标记当时市场背景，方便把同一思路放回到正确环境里比较。",
    "user_focus": "记录你当时主动盯着哪些标的、板块、指标或信息源，保留你的认知镜头。",
    "observed_signals": "记录真正触发你行动的市场切片，例如板块企稳、分时承接、放量突破等。",
    "position_reason": "记录为什么这次要轻仓、重仓、试错或分批，方便复盘仓位是否匹配当时认知。",
    "position_confidence": "记录你当时主观把握度，方便回看“高信心是否真的更有效”。",
    "stress_level": "记录你当时的紧张/焦虑程度，方便识别情绪和执行偏差的关系。",
    "mistake_tags": "沉淀重复犯错的模式，让自进化提醒能在下次提前拦你一下。",
    "emotion_notes": "保留当时的主观状态，方便识别情绪和执行问题的耦合关系。",
}
FIELD_EXAMPLES = {
    "ts_code": ["603083", "603083.SH"],
    "direction": ["买入计划", "卖出计划", "做T"],
    "thesis": ["题材回流叠加龙头首阴", "回踩5日线想做低吸"],
    "stop_loss": ["40", "跌破 40 止损"],
    "buy_date": ["20260410", "4月10日"],
    "buy_price": ["43.2", "成本 43.2"],
    "sell_date": ["20260415", "4月15日"],
    "sell_price": ["46.8", "卖在 46.8"],
    "buy_zone": ["42.5-43.0", "42.5 到 43"],
    "sell_zone": ["46-47", "46 到 47"],
    "user_focus": ["贵州茅台,消费板块", "大盘,分时,公告"],
    "observed_signals": ["跌不动了,板块企稳", "分时承接变强,放量突破"],
    "position_reason": ["先上试错仓", "确定性高所以比平时更重"],
    "position_confidence": ["7", "把握 7 分"],
    "stress_level": ["3", "焦虑 3 分"],
}
FIELD_PARSE_HINTS = {
    "ts_code": "优先提取 6 位代码或标准 TS 代码；如果用户回复股票简称，也可尝试结合本地上下文解析。",
    "direction": "优先识别买入 / 卖出 / 做 T；若回复是否定修正，也允许覆盖上一轮方向判断。",
    "thesis": "允许用户用一句很口语的话概括，不要求量化规则，只要能表达当时为什么出手。",
    "stop_loss": "既可接收纯价格，也可接收“跌破某位止损”这类自然语句。",
    "buy_date": "优先接受绝对日期，也兼容“今天 / 昨天 / 4月10日”之类相对表达。",
    "buy_price": "既可接受纯数字，也可接受“成本 43.2 / 43.2 买的”这类自然表达。",
    "sell_date": "优先接受绝对日期，也兼容“今天 / 昨天 / 4月15日”之类相对表达。",
    "sell_price": "既可接受纯数字，也可接受“46.8 卖的 / 卖在 46.8”这类自然表达。",
    "user_focus": "重点识别用户明确提到的标的、板块、指数、盘口、分时、公告、新闻等关注对象。",
    "observed_signals": "提取真正触发行动的短句，不求全面，只保留用户当时最在意的市场切片。",
    "position_reason": "优先提取带有轻仓、重仓、试错仓、分批、确定性、怕错过等表述的原因句。",
    "position_confidence": "优先识别“信心/把握/确定性 X 分”这类 1-10 打分。",
    "stress_level": "优先识别“焦虑/紧张/慌/怕 X 分”这类 1-10 打分。",
}


def _dedupe_texts(values: list[str], limit: int = 6) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip(" ：:，,。；;")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _extract_tags(text: str, rules: list[tuple[str, str]]) -> list[str]:
    tags: list[str] = []
    for pattern, tag in rules:
        if re.search(pattern, text, flags=re.IGNORECASE):
            tags.append(tag)
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _extract_prices(text: str) -> dict[str, float]:
    prices: dict[str, float] = {}
    price_token = r"(?<!\d)(\d{1,5}(?:\.\d+)?)(?!\d)"
    buy_patterns = [
        rf"(?:买(?:入)?|开仓|建仓|低吸|上车|成本(?:价)?|进(?:了|场)?)(?:在|于|价|到|@)?\s*{price_token}",
        rf"{price_token}\s*(?:买(?:的|入)?|开仓|建仓|上车)",
    ]
    sell_patterns = [
        rf"(?:卖(?:出)?|平仓|清仓|减仓)(?:在|于|价|到|@)?\s*{price_token}",
        rf"{price_token}\s*(?:卖(?:的|出)?|平仓|清仓)",
    ]
    for pattern in buy_patterns:
        match = re.search(pattern, text)
        if match:
            prices["buy_price"] = float(match.group(1))
            break
    for pattern in sell_patterns:
        match = re.search(pattern, text)
        if match:
            prices["sell_price"] = float(match.group(1))
            break
    stop_match = re.search(r"(?:止损|跌破)\s*(?<!\d)(\d{1,5}(?:\.\d+)?)(?!\d)", text)
    if stop_match:
        prices["stop_loss"] = float(stop_match.group(1))
    range_match = re.search(
        r"(?<!\d)(\d{1,5}(?:\.\d+)?)\s*[-~至到]\s*(\d{1,5}(?:\.\d+)?)(?!\d)",
        text,
    )
    if range_match:
        low = min(float(range_match.group(1)), float(range_match.group(2)))
        high = max(float(range_match.group(1)), float(range_match.group(2)))
        prices["range_low"] = low
        prices["range_high"] = high
    return prices


def _extract_position_pct(text: str) -> float | None:
    pct_match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text)
    if pct_match:
        return float(pct_match.group(1))
    cheng_match = re.search(r"([1-9](?:\.\d+)?)\s*成仓", text)
    if cheng_match:
        return round(float(cheng_match.group(1)) * 10, 2)
    return None


def _extract_date_tokens(text: str, anchor_date: str) -> list[str]:
    year = int(anchor_date[:4])
    tokens: list[str] = []
    compact_pattern = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
    full_pattern = re.compile(
        r"(?<!\d)(20\d{2})[-/年](0?[1-9]|1[0-2])[-/月](0?[1-9]|[12]\d|3[01])(?:日)?(?!\d)"
    )
    month_day_pattern = re.compile(r"(?<!\d)(0?[1-9]|1[0-2])(?:/|-|月)(0?[1-9]|[12]\d|3[01])(?:日)?(?!\d)")
    for match in compact_pattern.finditer(text):
        tokens.append(normalize_trade_date(f"{match.group(1)}{match.group(2)}{match.group(3)}"))
    for match in full_pattern.finditer(text):
        tokens.append(normalize_trade_date(f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"))
    for match in month_day_pattern.finditer(text):
        month = int(match.group(1))
        day = int(match.group(2))
        tokens.append(normalize_trade_date(f"{year}-{month:02d}-{day:02d}"))
    lowered = text.lower()
    if "今天" in text or "today" in lowered:
        tokens.append(normalize_trade_date(anchor_date))
    if "昨天" in text or "yesterday" in lowered:
        dt = datetime.strptime(normalize_trade_date(anchor_date), "%Y%m%d")
        tokens.append((dt - timedelta(days=1)).strftime("%Y%m%d"))
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _extract_symbol(text: str, symbol_index: dict[str, str]) -> dict[str, str]:
    code_match = re.search(r"(?<!\d)(\d{6}(?:\.(?:SH|SZ|BJ))?)(?!\d)", text, flags=re.IGNORECASE)
    if code_match:
        ts_code = normalize_ts_code(code_match.group(1))
        name = symbol_index.get(ts_code, "")
        return {"ts_code": ts_code, "name": name}
    for key in sorted(symbol_index, key=len, reverse=True):
        if not key or key.upper().endswith((".SH", ".SZ", ".BJ")):
            continue
        if key in text:
            return {"ts_code": symbol_index[key], "name": key}
    return {"ts_code": "", "name": ""}


def _extract_thesis(text: str) -> str:
    for pattern in (
        r"(?:因为|逻辑是|理由是|想着|判断是|看的是)([^。；;\n]+)",
        r"(?:博弈|赌|看)([^。；;\n]+)",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(" ：:，,。；;")
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:60]


def _extract_emotion_excerpt(text: str) -> str:
    sentences = re.split(r"[。；;\n]", text)
    chosen = [line.strip() for line in sentences if any(keyword in line for keyword in EMOTION_KEYWORDS)]
    return "；".join(chosen[:2])


def _extract_focus_items(text: str, symbol_index: dict[str, str]) -> list[str]:
    items: list[str] = []
    symbol_info = _extract_symbol(text, symbol_index)
    if symbol_info.get("name"):
        items.append(str(symbol_info["name"]))
    elif symbol_info.get("ts_code"):
        items.append(str(symbol_info["ts_code"]))
    for pattern in FOCUS_ITEM_PATTERNS:
        items.extend(match.group(0) for match in pattern.finditer(text))
    return _dedupe_texts(items, limit=6)


def _extract_signal_clauses(text: str) -> list[str]:
    clauses = re.split(r"[，,。；;！!\?\n]", text)
    selected = [
        clause.strip()
        for clause in clauses
        if clause.strip() and any(hint in clause for hint in SIGNAL_HINTS)
    ]
    return _dedupe_texts(selected, limit=4)


def _extract_position_reason(text: str) -> str:
    clauses = re.split(r"[。；;\n]", text)
    for clause in clauses:
        value = clause.strip(" ：:，,。；;")
        if value and any(hint in value for hint in POSITION_REASON_HINTS):
            return value
    return ""


def _extract_scored_value(text: str, keywords: tuple[str, ...]) -> int | None:
    stripped = str(text or "").strip()
    for keyword in keywords:
        match = re.search(rf"{re.escape(keyword)}[^\d]{{0,6}}([1-9]|10)\s*分", stripped)
        if match:
            return int(match.group(1))
    return None


def _has_meaningful_thesis(raw_text: str, thesis: str) -> bool:
    value = str(thesis or "").strip(" ：:，,。；;")
    if not value:
        return False
    lowered = value.lower()
    if any(hint in lowered for hint in THESIS_HINTS):
        return True
    compact = re.sub(r"\d{6}(?:\.(?:sh|sz|bj))?", "", lowered)
    compact = re.sub(r"\d+(?:\.\d+)?", "", compact)
    compact = re.sub(r"[，,。；;、\s\-_/]+", "", compact)
    if len(compact) < 6:
        return False
    generic_hits = sum(1 for hint in ("今天", "昨天", "买", "卖", "开仓", "平仓") if hint in value)
    return generic_hits <= 2 and compact != re.sub(r"[，,。；;、\s\-_/]+", "", str(raw_text or "").lower())


def required_fields_for_kind(journal_kind: str) -> list[str]:
    if journal_kind == "plan":
        return ["ts_code", "direction", "thesis", "stop_loss"]
    if journal_kind == "close_only":
        return ["ts_code", "sell_date", "sell_price"]
    if journal_kind == "closed_trade":
        return ["ts_code", "buy_date", "buy_price", "sell_date", "sell_price", "thesis"]
    return ["ts_code", "buy_date", "buy_price", "thesis"]


def build_follow_up_questions(missing_fields: list[str]) -> list[str]:
    return [FOLLOW_UP_MAP[item] for item in missing_fields if item in FOLLOW_UP_MAP]


def build_reflection_prompts(fields: dict[str, Any], journal_kind: str, missing_fields: list[str]) -> list[dict[str, Any]]:
    prompts: list[dict[str, Any]] = []
    if "thesis" in missing_fields or not fields.get("thesis"):
        prompts.append(
            {
                "field": "thesis",
                "question": "如果只能保留一句话，这笔交易/计划最核心的逻辑是什么？",
                "options": ["题材回流", "均线回踩", "情绪修复", "业绩催化"],
            }
        )
    if not fields.get("user_focus"):
        prompts.append(
            {
                "field": "user_focus",
                "question": "你当时主要盯着哪些对象或信息切片？比如个股、板块、大盘、盘口、新闻。",
                "options": list(FOCUS_CANDIDATES),
            }
        )
    if not fields.get("observed_signals"):
        prompts.append(
            {
                "field": "observed_signals",
                "question": "真正触发你出手/离场的那个信号是什么？尽量描述你当时看到的市场状态。",
                "options": list(SIGNAL_CANDIDATES[:4]),
            }
        )
    if journal_kind in {"plan", "open_trade", "closed_trade"} and not fields.get("position_reason"):
        prompts.append(
            {
                "field": "position_reason",
                "question": "这次仓位为什么这样配？是试错仓、确定性更高，还是怕错过先上一笔？",
                "options": list(POSITION_REASON_CANDIDATES[:4]),
            }
        )
    if not fields.get("logic_tags"):
        prompts.append(
            {
                "field": "logic_tags",
                "question": "这笔更偏哪类思路？先粗分类就够。",
                "options": list(LOGIC_CANDIDATES[:4]),
            }
        )
    if not fields.get("environment_tags"):
        prompts.append(
            {
                "field": "environment_tags",
                "question": "当时的市场背景更像哪一种？",
                "options": list(ENV_CANDIDATES[:4]),
            }
        )
    if journal_kind == "plan" and not fields.get("holding_period"):
        prompts.append(
            {
                "field": "holding_period",
                "question": "这份计划预期准备拿多久？先给一个粗区间就够。",
                "options": ["日内", "1-3天", "3-5天", "一周左右"],
            }
        )
    if journal_kind == "plan" and not fields.get("sell_zone"):
        prompts.append(
            {
                "field": "sell_zone",
                "question": "如果顺利走出来，你大致打算在哪个区间分批兑现？",
                "options": ["先不设", "前高附近", "按分时走弱", "分批止盈"],
            }
        )
    if journal_kind in {"open_trade", "closed_trade", "close_only"} and not fields.get("mistake_tags"):
        prompts.append(
            {
                "field": "mistake_tags",
                "question": "如果这笔里有一个最值得反思的执行问题，更像哪一种？",
                "options": list(MISTAKE_CANDIDATES[:4]),
            }
        )
    if journal_kind in {"open_trade", "closed_trade"} and not fields.get("emotion_notes"):
        prompts.append(
            {
                "field": "emotion_notes",
                "question": "下单时你的主观状态更接近哪一种？",
                "options": ["平静", "急躁", "犹豫", "害怕错过"],
            }
        )
    if journal_kind in {"plan", "open_trade", "closed_trade"} and fields.get("position_confidence") in (None, ""):
        prompts.append(
            {
                "field": "position_confidence",
                "question": "如果用 1-10 分给这次把握度打分，你会给几分？",
                "options": ["4", "6", "8", "10"],
            }
        )
    return prompts[:6]


def build_standardized_record(fields: dict[str, Any], journal_kind: str) -> dict[str, Any]:
    identity = fields.get("name") or fields.get("ts_code") or "未识别标的"
    summary_parts = [f"类型={journal_kind}", f"标的={identity}"]
    if fields.get("buy_date"):
        summary_parts.append(f"买入日={fields['buy_date']}")
    if fields.get("buy_price") is not None:
        summary_parts.append(f"买价={fields['buy_price']}")
    if fields.get("sell_date"):
        summary_parts.append(f"卖出日={fields['sell_date']}")
    if fields.get("sell_price") is not None:
        summary_parts.append(f"卖价={fields['sell_price']}")
    if fields.get("buy_zone"):
        summary_parts.append(f"买入区间={fields['buy_zone']}")
    if fields.get("stop_loss"):
        summary_parts.append(f"止损={fields['stop_loss']}")
    if fields.get("logic_tags"):
        summary_parts.append(f"逻辑标签={','.join(fields['logic_tags'])}")
    if fields.get("pattern_tags"):
        summary_parts.append(f"形态标签={','.join(fields['pattern_tags'])}")
    if fields.get("environment_tags"):
        summary_parts.append(f"环境标签={','.join(fields['environment_tags'])}")
    if fields.get("user_focus"):
        summary_parts.append(f"关注切片={','.join(fields['user_focus'][:3])}")
    if fields.get("observed_signals"):
        summary_parts.append(f"触发信号={','.join(fields['observed_signals'][:2])}")
    if fields.get("position_reason"):
        summary_parts.append(f"仓位理由={fields['position_reason']}")
    if fields.get("mistake_tags"):
        summary_parts.append(f"失误标签={','.join(fields['mistake_tags'])}")
    if fields.get("thesis"):
        summary_parts.append(f"核心逻辑={fields['thesis']}")
    return {
        "summary": " | ".join(summary_parts),
        "index_fields": {
            "journal_kind": journal_kind,
            "ts_code": fields.get("ts_code") or "",
            "name": fields.get("name") or "",
            "logic_tags": fields.get("logic_tags", []),
            "pattern_tags": fields.get("pattern_tags", []),
            "environment_tags": fields.get("environment_tags", []),
            "user_focus": fields.get("user_focus", []),
            "observed_signals": fields.get("observed_signals", []),
            "mistake_tags": fields.get("mistake_tags", []),
        },
        "soft_structure_note": SOFT_STRUCTURE_NOTE,
    }


def _axis_ready(fields: dict[str, Any], candidates: list[str]) -> bool:
    return any(fields.get(name) not in (None, "", [], {}) for name in candidates)


def _build_decision_axes(fields: dict[str, Any], journal_kind: str) -> list[dict[str, Any]]:
    axes = [
        {
            "axis": "selection",
            "label": "选股/关注对象",
            "field": "user_focus",
            "filled": _axis_ready(fields, ["ts_code", "user_focus", "thesis"]),
            "question": "你当时主要看向哪里？先说个股、板块、指数或新闻源即可。",
        },
        {
            "axis": "timing",
            "label": "择时/触发信号",
            "field": "observed_signals",
            "filled": _axis_ready(fields, ["observed_signals", "buy_zone", "sell_zone"]),
            "question": "真正触发动作的那个市场状态是什么？例如跌不动、企稳、放量、承接增强。",
        },
        {
            "axis": "position",
            "label": "仓位/边界",
            "field": "position_reason",
            "filled": _axis_ready(fields, ["position_reason", "position_size_pct", "stop_loss", "position_confidence"]),
            "question": "这次仓位为什么这样配？如果有纪律边界，也一起说。",
        },
        {
            "axis": "emotion",
            "label": "情绪/纪律",
            "field": "emotion_notes",
            "filled": _axis_ready(fields, ["emotion_notes", "mistake_tags", "stress_level"]),
            "question": "下单时的主观状态更像什么？急、慌、稳，还是怕错过？",
        },
    ]
    if journal_kind == "close_only":
        axes[1]["question"] = "真正触发你卖出的变化是什么？例如破位、到目标位、消息面变化。"
    return axes


def _build_bundle_item_map(
    missing_queue: list[dict[str, Any]],
    reflection_queue: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for queue_item in missing_queue:
        field_name = str(queue_item.get("field") or "")
        if not field_name:
            continue
        items[field_name] = dict(queue_item)
    for prompt in reflection_queue:
        field_name = str(prompt.get("field") or "")
        if not field_name or field_name in items:
            continue
        items[field_name] = {
            "field": field_name,
            "question": str(prompt.get("question") or ""),
            "examples": list(prompt.get("options", []))[:4],
            "purpose": str(prompt.get("purpose") or FIELD_PURPOSES.get(field_name, "")),
        }
    return items


def _build_shared_context_hints(
    bundle_items: dict[str, dict[str, Any]],
    journal_kind: str,
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []

    market_fields = [name for name in ("environment_tags", "observed_signals", "user_focus") if name in bundle_items]
    if market_fields:
        hints.append(
            {
                "scope": "trade_date",
                "label": "同日市场环境",
                "reusable_fields": market_fields,
                "reuse_when": "同一交易日整体市场看法没有明显变化时，可只回答一次。",
                "question": "如果今天整体环境判断一致，可一次说明市场阶段、环境标签和关键触发信号，后续同日记录复用。",
            }
        )

    symbol_fields = [name for name in ("thesis", "user_focus", "observed_signals", "position_reason") if name in bundle_items]
    if len(symbol_fields) >= 2:
        hints.append(
            {
                "scope": "symbol",
                "label": "同票主线 / 做T 复用",
                "reusable_fields": symbol_fields,
                "reuse_when": "如果只是同一只票反复做 T、核心选股思路没变，可合并回答。",
                "question": "如果这几笔只是同一只票做 T，可一次说明为什么持续盯它、核心逻辑和触发条件。",
            }
        )

    strategy_fields = [name for name in ("thesis", "position_reason", "position_confidence", "environment_tags") if name in bundle_items]
    if strategy_fields and journal_kind in {"plan", "open_trade", "closed_trade"}:
        hints.append(
            {
                "scope": "strategy",
                "label": "量化 / 半量化策略条线",
                "reusable_fields": strategy_fields,
                "reuse_when": "同一策略条线、因子组或参数版本持续启用时，可集中补一次。",
                "question": "如果这是量化或半量化策略，可一次说明策略条线、核心因子、启用原因，再把执行记录分开落账。",
            }
        )
    return hints[:3]


def _build_parallel_question_groups(bundle_items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    fact_fields = [name for name in ("ts_code", "direction", "buy_date", "buy_price", "sell_date", "sell_price", "stop_loss") if name in bundle_items]
    if len(fact_fields) >= 2:
        groups.append(
            {
                "group": "fact_block",
                "label": "事实快填",
                "scope": "record",
                "fields": fact_fields[:4],
                "question": "这些事实字段可以一条一起回答，减少来回补问。",
            }
        )

    market_fields = [name for name in ("user_focus", "environment_tags", "observed_signals") if name in bundle_items]
    if len(market_fields) >= 2:
        groups.append(
            {
                "group": "market_context_block",
                "label": "同日环境并行补问",
                "scope": "trade_date",
                "fields": market_fields,
                "question": "如果同一天市场看法一致，可一次回答关注对象、环境标签和触发信号。",
            }
        )

    symbol_fields = [name for name in ("thesis", "user_focus", "observed_signals", "position_reason") if name in bundle_items]
    if len(symbol_fields) >= 2:
        groups.append(
            {
                "group": "symbol_context_block",
                "label": "单票主线并行补问",
                "scope": "symbol",
                "fields": symbol_fields,
                "question": "如果只是同一只票做 T 或沿同一主线反复交易，可把选股逻辑、信号和仓位理由一次补齐。",
            }
        )

    strategy_fields = [name for name in ("thesis", "position_reason", "position_confidence", "environment_tags") if name in bundle_items]
    if len(strategy_fields) >= 2:
        groups.append(
            {
                "group": "strategy_context_block",
                "label": "量化条线并行补问",
                "scope": "strategy",
                "fields": strategy_fields,
                "question": "如果这是量化 / 半量化策略，可把策略条线、因子与启用原因作为一个上下文块一起补。",
            }
        )
    return groups[:4]


def build_polling_bundle(
    fields: dict[str, Any],
    journal_kind: str,
    missing_fields: list[str],
    follow_up_questions: list[str],
    reflection_prompts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reflection_queue: list[dict[str, Any]] = []
    for prompt in reflection_prompts or []:
        prompt_copy = dict(prompt)
        field_name = str(prompt_copy.get("field") or "")
        prompt_copy["purpose"] = FIELD_PURPOSES.get(field_name, "用于补充软结构索引，让后续复盘和自进化更可复用。")
        reflection_queue.append(prompt_copy)

    next_field = missing_fields[0] if missing_fields else (str(reflection_queue[0].get("field") or "") if reflection_queue else "")
    next_question = follow_up_questions[0] if follow_up_questions else (str(reflection_queue[0].get("question") or "") if reflection_queue else "")
    candidate_tags: dict[str, list[str]] = {}
    if next_field == "thesis":
        candidate_tags["logic_tags"] = list(LOGIC_CANDIDATES)
        candidate_tags["pattern_tags"] = list(PATTERN_CANDIDATES)
        candidate_tags["environment_tags"] = list(ENV_CANDIDATES)
    elif next_field == "mistake_tags":
        candidate_tags["mistake_tags"] = list(MISTAKE_CANDIDATES)
    missing_queue: list[dict[str, Any]] = []
    for field_name, question in zip(missing_fields, follow_up_questions):
        queue_item = {
            "field": field_name,
            "question": question,
            "examples": list(FIELD_EXAMPLES.get(field_name, [])),
            "purpose": FIELD_PURPOSES.get(field_name, ""),
        }
        parser_hint = FIELD_PARSE_HINTS.get(field_name, "")
        if parser_hint:
            queue_item["parser_hint"] = parser_hint
        missing_queue.append(queue_item)
    required_total = len(required_fields_for_kind(journal_kind))
    required_missing = len(missing_fields)
    decision_axes = _build_decision_axes(fields, journal_kind)
    next_axis = next((item["axis"] for item in decision_axes if not item["filled"]), "")
    bundle_items = _build_bundle_item_map(missing_queue, reflection_queue)
    shared_context_hints = _build_shared_context_hints(bundle_items, journal_kind)
    parallel_question_groups = _build_parallel_question_groups(bundle_items)
    return {
        "journal_kind": journal_kind,
        "next_field": next_field,
        "next_question": next_question,
        "examples": list(FIELD_EXAMPLES.get(next_field, [])),
        "candidate_tags": candidate_tags,
        "reply_strategy": [
            "默认先把用户下一条回复当作 next_field 的候选答案。",
            "如果回复里顺带补了其他字段，再整体重跑解析器并一并吸收。",
            "先补事实字段，再补软结构标签；标签只用于索引和统计，不等于自动规则。",
            "围绕“选股关注 -> 择时触发 -> 仓位边界 -> 情绪纪律”四个轴补齐，优先保留你当时看到的市场切片。",
            "如果同一交易日的市场环境判断一致，可把日期级环境问题合并一次回答。",
            "如果同一只票只是反复做 T，可把选股主线、触发信号和仓位理由一次说明，减少重复轮询。",
            "如果是量化 / 半量化策略，可把策略条线、因子选择和启用原因单独成块补充。",
        ],
        "missing_field_queue": missing_queue,
        "reflection_queue": reflection_queue[:4],
        "decision_axes": decision_axes,
        "next_axis": next_axis,
        "shared_context_hints": shared_context_hints,
        "parallel_question_groups": parallel_question_groups,
        "completion_progress": {
            "required_total": required_total,
            "required_filled": required_total - required_missing,
            "required_missing": required_missing,
        },
        "soft_structure_note": SOFT_STRUCTURE_NOTE,
    }


def evaluate_journal_fields(fields: dict[str, Any], journal_kind: str) -> dict[str, Any]:
    required_fields = required_fields_for_kind(journal_kind)
    missing_fields = [key for key in required_fields if fields.get(key) in (None, "", [])]
    action_ready = not missing_fields
    suggested_command = ""
    if action_ready:
        if journal_kind == "plan":
            suggested_command = "plan create"
        elif journal_kind == "close_only":
            suggested_command = "trade close"
        else:
            suggested_command = "trade log"
    return {
        "required_fields": required_fields,
        "missing_fields": missing_fields,
        "follow_up_questions": build_follow_up_questions(missing_fields),
        "action_ready": action_ready,
        "suggested_command": suggested_command,
    }


def extract_field_value(
    field_name: str,
    text: str,
    symbol_index: dict[str, str] | None = None,
    anchor_date: str | None = None,
) -> Any:
    raw_text = str(text or "").strip()
    if not raw_text:
        return None
    normalized_text = raw_text.replace("\u3000", " ").strip()
    symbol_index = symbol_index or {}
    anchor = normalize_trade_date(anchor_date or datetime.now().strftime("%Y%m%d"))
    stripped = normalized_text.strip(" ：:，,。；;")

    if field_name == "ts_code":
        symbol_info = _extract_symbol(normalized_text, symbol_index)
        if symbol_info.get("ts_code"):
            return symbol_info
        return None
    if field_name == "direction":
        lowered = normalized_text.lower()
        if "t" in lowered and "做t" in lowered:
            return "t"
        if any(token in normalized_text for token in SELL_HINTS + ("卖出计划",)):
            return "sell"
        if any(token in normalized_text for token in BUY_HINTS + ("买入计划",)):
            return "buy"
        return None
    if field_name in {"buy_date", "sell_date"}:
        dates = _extract_date_tokens(normalized_text, anchor)
        return dates[0] if dates else None
    if field_name in {"buy_price", "sell_price", "stop_loss"}:
        prices = _extract_prices(normalized_text)
        if field_name in prices:
            return prices[field_name]
        standalone = re.fullmatch(r"\s*(\d{1,5}(?:\.\d+)?)\s*", normalized_text)
        if standalone:
            return float(standalone.group(1))
        return None
    if field_name in {"buy_zone", "sell_zone"}:
        prices = _extract_prices(normalized_text)
        if "range_low" in prices and "range_high" in prices:
            return f"{prices['range_low']}-{prices['range_high']}"
        range_match = re.fullmatch(r"\s*(\d{1,5}(?:\.\d+)?)\s*[-~至到]\s*(\d{1,5}(?:\.\d+)?)\s*", normalized_text)
        if range_match:
            low = min(float(range_match.group(1)), float(range_match.group(2)))
            high = max(float(range_match.group(1)), float(range_match.group(2)))
            return f"{low}-{high}"
        return None
    if field_name == "thesis":
        thesis = _extract_thesis(normalized_text)
        if _has_meaningful_thesis(normalized_text, thesis):
            return thesis
        if len(stripped) >= 4 and any(hint in stripped.lower() for hint in THESIS_HINTS):
            return stripped
        return None
    if field_name == "user_focus":
        items = _extract_focus_items(normalized_text, symbol_index)
        return items or None
    if field_name == "observed_signals":
        signals = _extract_signal_clauses(normalized_text)
        return signals or None
    if field_name == "position_reason":
        reason = _extract_position_reason(normalized_text)
        return reason or None
    if field_name == "position_confidence":
        return _extract_scored_value(normalized_text, ("信心", "把握", "确定性"))
    if field_name == "stress_level":
        return _extract_scored_value(normalized_text, ("焦虑", "紧张", "慌", "害怕", "怕"))
    if field_name == "holding_period":
        if re.search(r"\d+(?:\.\d+)?\s*(?:天|日|周)", normalized_text):
            return stripped
        return None
    return None


def infer_mode(text: str, preferred_mode: str = "auto") -> str:
    if preferred_mode in {"trade", "plan"}:
        return preferred_mode
    if any(keyword in text for keyword in ENTRY_KEYWORDS["plan"]):
        return "plan"
    return "trade"


def parse_freeform_journal(
    text: str,
    symbol_index: dict[str, str] | None = None,
    preferred_mode: str = "auto",
    anchor_date: str | None = None,
) -> dict[str, Any]:
    raw_text = str(text or "").strip()
    anchor = normalize_trade_date(anchor_date or datetime.now().strftime("%Y%m%d"))
    index = symbol_index or {}
    normalized_text = raw_text.replace("\u3000", " ").strip()
    mode = infer_mode(normalized_text, preferred_mode=preferred_mode)
    symbol_info = _extract_symbol(normalized_text, index)
    prices = _extract_prices(normalized_text)
    dates = _extract_date_tokens(normalized_text, anchor)
    logic_tags = _extract_tags(normalized_text, LOGIC_RULES)
    pattern_tags = _extract_tags(normalized_text, PATTERN_RULES)
    environment_tags = _extract_tags(normalized_text, ENV_RULES)
    mistake_tags = _extract_tags(normalized_text, MISTAKE_RULES)
    emotion_excerpt = _extract_emotion_excerpt(normalized_text)
    thesis = _extract_thesis(normalized_text)
    if not _has_meaningful_thesis(normalized_text, thesis):
        thesis = ""
    user_focus = _extract_focus_items(normalized_text, index)
    observed_signals = _extract_signal_clauses(normalized_text)
    position_reason = _extract_position_reason(normalized_text)
    position_confidence = _extract_scored_value(normalized_text, ("信心", "把握", "确定性"))
    stress_level = _extract_scored_value(normalized_text, ("焦虑", "紧张", "慌", "害怕", "怕"))
    position_pct = _extract_position_pct(normalized_text)

    has_buy = any(hint in normalized_text for hint in BUY_HINTS) or "buy_price" in prices
    has_sell = any(hint in normalized_text for hint in SELL_HINTS) or "sell_price" in prices
    journal_kind = "plan"
    if mode == "trade":
        if has_buy and has_sell:
            journal_kind = "closed_trade"
        elif has_sell and not has_buy:
            journal_kind = "close_only"
        else:
            journal_kind = "open_trade"

    inferred_direction = "buy"
    if journal_kind == "close_only":
        inferred_direction = "sell"
    elif mode == "plan" and has_sell and not has_buy:
        inferred_direction = "sell"
    fields: dict[str, Any] = {
        "ts_code": symbol_info.get("ts_code") or "",
        "name": symbol_info.get("name") or "",
        "direction": inferred_direction,
        "thesis": thesis,
        "logic_tags": logic_tags,
        "pattern_tags": pattern_tags,
        "environment_tags": environment_tags,
        "user_focus": user_focus,
        "observed_signals": observed_signals,
        "position_reason": position_reason,
        "position_confidence": position_confidence,
        "stress_level": stress_level,
        "mistake_tags": mistake_tags,
        "emotion_notes": emotion_excerpt,
        "lessons_learned": "",
        "position_size_pct": position_pct,
        "buy_date": dates[0] if dates else anchor,
        "sell_date": dates[1] if len(dates) > 1 else (dates[0] if journal_kind == "close_only" and dates else ""),
        "buy_price": prices.get("buy_price"),
        "sell_price": prices.get("sell_price"),
        "buy_zone": "",
        "sell_zone": "",
        "stop_loss": str(prices["stop_loss"]) if "stop_loss" in prices else "",
        "holding_period": "",
        "valid_from": anchor,
        "valid_to": "",
        "notes": raw_text,
    }
    if "range_low" in prices and "range_high" in prices:
        range_text = f"{prices['range_low']}-{prices['range_high']}"
        if mode == "plan":
            fields["buy_zone"] = range_text if any(hint in normalized_text for hint in BUY_HINTS + ("买", "低吸", "回踩")) else ""
            if any(hint in normalized_text for hint in SELL_ZONE_HINTS):
                fields["sell_zone"] = range_text
        else:
            if fields.get("buy_price") is None:
                fields["buy_zone"] = range_text
    if mode == "plan" and not fields["valid_to"]:
        fields["valid_to"] = anchor

    evaluation = evaluate_journal_fields(fields, journal_kind)

    confidence = 0.35
    if fields["ts_code"]:
        confidence += 0.2
    if fields["thesis"]:
        confidence += 0.15
    if fields["buy_price"] is not None or fields["sell_price"] is not None:
        confidence += 0.15
    if logic_tags or pattern_tags or environment_tags:
        confidence += 0.15
    confidence = min(round(confidence, 2), 0.95)

    reflection_prompts = build_reflection_prompts(fields, journal_kind, evaluation["missing_fields"])
    return {
        "raw_text": raw_text,
        "mode": mode,
        "journal_kind": journal_kind,
        "confidence": confidence,
        "fields": fields,
        "required_fields": evaluation["required_fields"],
        "missing_fields": evaluation["missing_fields"],
        "follow_up_questions": evaluation["follow_up_questions"],
        "action_ready": evaluation["action_ready"],
        "suggested_command": evaluation["suggested_command"],
        "standardized_record": build_standardized_record(fields, journal_kind),
        "reflection_prompts": reflection_prompts,
        "polling_bundle": build_polling_bundle(
            fields,
            journal_kind,
            evaluation["missing_fields"],
            evaluation["follow_up_questions"],
            reflection_prompts=reflection_prompts,
        ),
        "tag_candidates": {
            "logic_tags": logic_tags,
            "pattern_tags": pattern_tags,
            "environment_tags": environment_tags,
            "mistake_tags": mistake_tags,
        },
    }
