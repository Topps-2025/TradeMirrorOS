from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

from .market_data import normalize_trade_date, to_date
from .storage import json_loads


TAG_SPLIT_RE = re.compile(r"[，,、/|；;]+")
EMOTION_RULES = [
    (r"急|急躁", "急躁"),
    (r"慌|慌张", "慌张"),
    (r"怕|害怕", "害怕"),
    (r"冲动", "冲动"),
    (r"犹豫", "犹豫"),
    (r"上头", "上头"),
    (r"贪|贪心", "贪心"),
    (r"后悔", "后悔"),
]


def split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(split_tags(item))
        return result
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in TAG_SPLIT_RE.split(text) if item.strip()]


def parse_numeric_range(text: Any) -> tuple[float, float] | None:
    if text in (None, ""):
        return None
    values = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(text))]
    if not values:
        return None
    if len(values) == 1:
        return (values[0], values[0])
    low, high = values[0], values[1]
    return (min(low, high), max(low, high))


def compute_return_pct(start_price: float | None, end_price: float | None) -> float | None:
    if not start_price or end_price is None:
        return None
    return round((end_price / start_price - 1) * 100, 2)


def compute_zone_deviation(price: float | None, zone_text: Any) -> dict[str, Any] | None:
    bounds = parse_numeric_range(zone_text)
    if price is None or not bounds:
        return None
    low, high = bounds
    if low <= price <= high:
        return {"in_zone": True, "distance_pct": 0.0, "low": low, "high": high}
    reference = low if price < low else high
    return {
        "in_zone": False,
        "distance_pct": round((price / reference - 1) * 100, 2),
        "low": low,
        "high": high,
        "reference": reference,
    }


def calculate_plan_execution_deviation(plan_row: dict[str, Any] | None, buy_price: float | None, sell_price: float | None) -> dict[str, Any]:
    if not plan_row:
        return {}
    result: dict[str, Any] = {}
    buy_deviation = compute_zone_deviation(buy_price, plan_row.get("buy_zone"))
    if buy_deviation is not None:
        result["buy"] = buy_deviation
    sell_deviation = compute_zone_deviation(sell_price, plan_row.get("sell_zone"))
    if sell_deviation is not None:
        result["sell"] = sell_deviation
    stop_loss = parse_numeric_range(plan_row.get("stop_loss"))
    if stop_loss and buy_price:
        result["stop_loss_pct_from_buy"] = round((stop_loss[1] / buy_price - 1) * 100, 2)
    return result


def parse_holding_days(text: Any) -> float | None:
    if text in (None, ""):
        return None
    values = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(text))]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def similarity_score(
    trade_row: dict[str, Any],
    logic_tags: Iterable[str] | None,
    market_stage: str | None,
    environment_tags: Iterable[str] | None,
) -> float:
    requested_logic = set(split_tags(list(logic_tags or [])))
    requested_env = set(split_tags(list(environment_tags or [])))
    trade_logic = set(split_tags(json_loads(trade_row.get("logic_type_tags_json"), [])))
    trade_logic.update(split_tags(json_loads(trade_row.get("pattern_tags_json"), [])))
    trade_env = set(split_tags(json_loads(trade_row.get("environment_tags_json"), [])))

    score = 0.0
    if requested_logic:
        score += 2.0 * len(trade_logic & requested_logic)
    if requested_env:
        score += 1.0 * len(trade_env & requested_env)
    if market_stage and trade_row.get("market_stage_tag") == market_stage:
        score += 1.5
    theme = str(trade_row.get("theme") or "")
    if theme and requested_logic and any(tag in theme for tag in requested_logic):
        score += 0.5
    return score


def _top_tags(trades: list[dict[str, Any]], positive: bool) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for trade in trades:
        pnl = trade.get("actual_return_pct")
        if pnl is None:
            continue
        if positive and pnl <= 0:
            continue
        if not positive and pnl >= 0:
            continue
        tags = split_tags(json_loads(trade.get("logic_type_tags_json"), []))
        tags += split_tags(json_loads(trade.get("pattern_tags_json"), []))
        counter.update(tags)
    return [{"tag": tag, "count": count} for tag, count in counter.most_common(5)]


def build_reference_report(
    trades: list[dict[str, Any]],
    logic_tags: Iterable[str] | None,
    market_stage: str | None,
    environment_tags: Iterable[str] | None,
    lookback_days: int,
) -> dict[str, Any]:
    filtered: list[dict[str, Any]] = []
    for trade in trades:
        score = similarity_score(trade, logic_tags, market_stage, environment_tags)
        if logic_tags or market_stage or environment_tags:
            if score < 2.0:
                continue
        trade_copy = dict(trade)
        trade_copy["similarity_score"] = round(score, 2)
        filtered.append(trade_copy)

    filtered.sort(key=lambda item: (item.get("similarity_score") or 0, item.get("sell_date") or item.get("buy_date") or ""), reverse=True)
    sample = filtered[:30]
    realized = [item for item in sample if item.get("actual_return_pct") is not None]
    wins = [item for item in realized if item["actual_return_pct"] > 0]
    losses = [item for item in realized if item["actual_return_pct"] <= 0]
    avg_return = round(sum(item["actual_return_pct"] for item in realized) / len(realized), 2) if realized else None
    alpha_values = [item["timing_alpha_pct"] for item in realized if item.get("timing_alpha_pct") is not None]
    avg_alpha = round(sum(alpha_values) / len(alpha_values), 2) if alpha_values else None
    benchmark_values = [item["benchmark_return_pct"] for item in realized if item.get("benchmark_return_pct") is not None]
    avg_benchmark = round(sum(benchmark_values) / len(benchmark_values), 2) if benchmark_values else None
    win_rate = round(len(wins) / len(realized) * 100, 2) if realized else None
    best = max(realized, key=lambda item: item["actual_return_pct"], default=None)
    worst = min(realized, key=lambda item: item["actual_return_pct"], default=None)
    insufficient = len(realized) < 3

    query_bits = []
    if logic_tags:
        query_bits.append(" + ".join(split_tags(list(logic_tags))))
    if market_stage:
        query_bits.append(market_stage)
    if environment_tags:
        query_bits.append(" + ".join(split_tags(list(environment_tags))))
    query_text = " | ".join(query_bits) if query_bits else "全部已闭环交易"

    if insufficient:
        narrative = f"样本不足 3 笔，当前仅找到 {len(realized)} 笔相似历史，建议继续积累数据。"
    else:
        narrative = f"基于最近 {lookback_days} 天内的 {len(realized)} 笔相似历史"
        if win_rate is not None:
            narrative += f"，胜率 {win_rate:.2f}%"
        if avg_return is not None:
            narrative += f"，平均实际收益 {avg_return:.2f}%"
        if avg_alpha is not None:
            narrative += f"，平均操作绩效差值 {avg_alpha:.2f}%"
        narrative += "。"

    markdown_lines = [
        f"# 搭档参考 | {query_text}",
        "",
        f"- 样本窗口: 最近 {lookback_days} 天",
        f"- 匹配样本: {len(realized)} 笔已闭环交易",
        f"- 胜率: {f'{win_rate:.2f}%' if win_rate is not None else 'N/A'}",
        f"- 平均实际收益: {f'{avg_return:.2f}%' if avg_return is not None else 'N/A'}",
        f"- 平均选股基准收益: {f'{avg_benchmark:.2f}%' if avg_benchmark is not None else 'N/A'}",
        f"- 平均操作绩效差值: {f'{avg_alpha:.2f}%' if avg_alpha is not None else 'N/A'}",
        "",
        narrative,
        "",
    ]
    if best:
        markdown_lines.append(f"- 最佳样本: {best.get('name') or best.get('ts_code')} {best['actual_return_pct']:.2f}%")
    if worst:
        markdown_lines.append(f"- 最弱样本: {worst.get('name') or worst.get('ts_code')} {worst['actual_return_pct']:.2f}%")
    profitable_tags = _top_tags(sample, positive=True)
    loss_tags = _top_tags(sample, positive=False)
    if profitable_tags:
        markdown_lines.append("")
        markdown_lines.append("## 更常见于盈利样本的标签")
        for item in profitable_tags:
            markdown_lines.append(f"- {item['tag']}: {item['count']} 次")
    if loss_tags:
        markdown_lines.append("")
        markdown_lines.append("## 更常见于亏损样本的标签")
        for item in loss_tags:
            markdown_lines.append(f"- {item['tag']}: {item['count']} 次")

    return {
        "query": {
            "logic_tags": split_tags(list(logic_tags or [])),
            "market_stage": market_stage or "",
            "environment_tags": split_tags(list(environment_tags or [])),
        },
        "lookback_days": lookback_days,
        "sample_size": len(realized),
        "insufficient_sample": insufficient,
        "win_rate_pct": win_rate,
        "avg_actual_return_pct": avg_return,
        "avg_benchmark_return_pct": avg_benchmark,
        "avg_timing_alpha_pct": avg_alpha,
        "best_trade": best,
        "worst_trade": worst,
        "dominant_profitable_tags": profitable_tags,
        "dominant_loss_tags": loss_tags,
        "matched_trades": sample,
        "narrative": narrative,
        "markdown": "\n".join(markdown_lines).strip() + "\n",
    }


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    haystack = str(text or "")
    for needle in needles:
        if needle and needle in haystack:
            return True
    return False


def _trade_feature_sets(trade: dict[str, Any]) -> dict[str, list[str] | str]:
    return {
        "logic": split_tags(json_loads(trade.get("logic_type_tags_json"), [])),
        "pattern": split_tags(json_loads(trade.get("pattern_tags_json"), [])),
        "environment": split_tags(json_loads(trade.get("environment_tags_json"), [])),
        "mistake": split_tags(json_loads(trade.get("mistake_tags_json"), [])),
        "stage": str(trade.get("market_stage_tag") or "").strip(),
    }


def _is_effective_trade(trade: dict[str, Any]) -> bool:
    pnl = trade.get("actual_return_pct")
    alpha = trade.get("timing_alpha_pct")
    if pnl is None or pnl <= 0:
        return False
    if alpha is not None and alpha < 0:
        return False
    return True


def _emotion_tags(trade: dict[str, Any]) -> list[str]:
    text = str(trade.get("emotion_notes") or "")
    tags: list[str] = []
    for pattern, label in EMOTION_RULES:
        if re.search(pattern, text):
            tags.append(label)
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _execution_tokens(trade: dict[str, Any]) -> list[tuple[str, str, str]]:
    tokens: list[tuple[str, str, str]] = []
    deviation = json_loads(trade.get("plan_execution_deviation_json"), {}) or {}
    buy = deviation.get("buy") or {}
    sell = deviation.get("sell") or {}
    if buy:
        if buy.get("in_zone") is True:
            tokens.append(("execution:buy_in_plan", "纪律", "买点在计划内"))
        elif buy.get("in_zone") is False:
            tokens.append(("execution:buy_off_plan", "纪律", "买点偏离计划"))
    if sell:
        if sell.get("in_zone") is True:
            tokens.append(("execution:sell_in_plan", "纪律", "卖点在计划内"))
        elif sell.get("in_zone") is False:
            tokens.append(("execution:sell_off_plan", "纪律", "卖点偏离计划"))
    return tokens


def _review_tokens(reviews_by_trade: dict[str, list[dict[str, Any]]], trade_id: str) -> list[tuple[str, str, str]]:
    tokens: list[tuple[str, str, str]] = []
    for review in reviews_by_trade.get(trade_id, []):
        review_type = str(review.get("review_type") or "")
        if review_type == "sell_fly":
            tokens.append(("review:sell_fly", "回顾", "卖飞回顾触发"))
        elif review_type == "good_exit":
            tokens.append(("review:good_exit", "回顾", "有效保护卖出"))
    return tokens


def _review_feedback_specs(reviews_by_trade: dict[str, list[dict[str, Any]]], trade_id: str) -> list[tuple[str, str, str]]:
    tokens: list[tuple[str, str, str]] = []
    for review in reviews_by_trade.get(trade_id, []):
        review_type = str(review.get("review_type") or "")
        feedback = str(review.get("feedback") or "")
        weight_action = str(review.get("weight_action") or "")
        combined = f"{feedback} {weight_action}"
        if review_type == "sell_fly":
            if _contains_any(combined, ("降低", "下调", "过早", "卖早", "确认卖飞")):
                tokens.append(("review_feedback:sell_fly_confirmed", "回顾反馈", "确认卖飞"))
            elif _contains_any(combined, ("否", "纪律", "遵守", "保留", "不过早")):
                tokens.append(("review_feedback:discipline_kept", "回顾反馈", "纪律性卖出被确认"))
        elif review_type == "good_exit":
            if _contains_any(combined, ("提升", "保留", "有效", "正确", "遵守")):
                tokens.append(("review_feedback:good_exit_confirmed", "回顾反馈", "有效卖出被确认"))
    return tokens


def _token_specs(
    trade: dict[str, Any],
    reviews_by_trade: dict[str, list[dict[str, Any]]] | None = None,
) -> list[tuple[str, str, str]]:
    features = _trade_feature_sets(trade)
    specs: list[tuple[str, str, str]] = []
    for tag in features["logic"]:
        specs.append((f"logic:{tag}", "逻辑", tag))
    for tag in features["pattern"]:
        specs.append((f"pattern:{tag}", "形态", tag))
    stage = str(features["stage"] or "")
    if stage:
        specs.append((f"stage:{stage}", "市场阶段", stage))
    for tag in features["environment"]:
        specs.append((f"environment:{tag}", "环境", tag))
    for tag in features["mistake"]:
        specs.append((f"mistake:{tag}", "失误", tag))
    for tag in _emotion_tags(trade):
        specs.append((f"emotion:{tag}", "情绪", tag))
    specs.extend(_execution_tokens(trade))
    if reviews_by_trade:
        specs.extend(_review_tokens(reviews_by_trade, str(trade.get("trade_id") or "")))
        specs.extend(_review_feedback_specs(reviews_by_trade, str(trade.get("trade_id") or "")))
    deduped: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for key, kind, label in specs:
        if key in seen:
            continue
        seen.add(key)
        deduped.append((key, kind, label))
    return deduped


def _quality_path_components(
    trade: dict[str, Any],
    reviews_by_trade: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    features = _trade_feature_sets(trade)
    components: list[str] = []
    logic = features["logic"]
    pattern = features["pattern"]
    environment = features["environment"]
    stage = str(features["stage"] or "")
    if logic:
        components.append(f"逻辑={logic[0]}")
    if pattern:
        components.append(f"形态={pattern[0]}")
    if stage:
        components.append(f"阶段={stage}")
    for tag in environment[:2]:
        components.append(f"环境={tag}")
    for _, _, label in _execution_tokens(trade):
        if label in {"买点在计划内", "卖点在计划内"}:
            components.append(f"纪律={label}")
            break
    return components


def _bucket_summary(bucket: dict[str, Any]) -> dict[str, Any]:
    sample_size = len(bucket["returns"])
    win_rate = round(bucket["wins"] / sample_size * 100, 2) if sample_size else None
    avg_return = _avg(bucket["returns"])
    avg_alpha = _avg(bucket["alphas"])
    avg_holding = _avg(bucket["holding_days"])
    positive_edge_score = round(
        (win_rate or 0.0)
        + (avg_return or 0.0) * 2
        + (avg_alpha or 0.0)
        + bucket["effective_count"] * 8
        - bucket["losses"] * 5,
        2,
    )
    return {
        "sample_size": sample_size,
        "win_rate_pct": win_rate,
        "avg_actual_return_pct": avg_return,
        "avg_timing_alpha_pct": avg_alpha,
        "avg_holding_days": avg_holding,
        "effective_count": bucket["effective_count"],
        "loss_count": bucket["losses"],
        "positive_edge_score": positive_edge_score,
    }


def _bandit_metrics(summary: dict[str, Any], total_samples: int, risk: bool = False) -> dict[str, Any]:
    sample_size = int(summary.get("sample_size") or 0)
    loss_count = int(summary.get("loss_count") or 0)
    win_count = max(sample_size - loss_count, 0)
    effective_count = int(summary.get("effective_count") or 0)
    posterior_alpha = 1.0 + win_count + max(effective_count - win_count, 0)
    posterior_beta = 1.0 + loss_count
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)
    exploration_bonus = math.sqrt(2.0 * math.log(max(total_samples, 1) + 2.0) / (sample_size + 1.0))
    avg_return = float(summary.get("avg_actual_return_pct") or 0.0)
    avg_alpha = float(summary.get("avg_timing_alpha_pct") or 0.0)
    reward_component = max(avg_return, 0.0) / 20.0 + max(avg_alpha, 0.0) / 25.0
    ucb_score = posterior_mean + 0.35 * exploration_bonus + reward_component
    conservative_score = posterior_mean - 0.2 * exploration_bonus + reward_component * 0.5
    payload = {
        "posterior_alpha": round(posterior_alpha, 3),
        "posterior_beta": round(posterior_beta, 3),
        "posterior_mean": round(posterior_mean, 4),
        "exploration_bonus": round(exploration_bonus, 4),
        "ucb_score": round(ucb_score, 4),
        "conservative_score": round(conservative_score, 4),
    }
    if risk:
        risk_penalty_score = max(-avg_return, 0.0) / 12.0 + loss_count / max(sample_size or 1, 1) + exploration_bonus * 0.2
        payload["risk_penalty_score"] = round(risk_penalty_score, 4)
    return payload


def _is_risk_token(token_key: str) -> bool:
    if token_key.startswith("mistake:"):
        return True
    if token_key in {
        "execution:buy_off_plan",
        "execution:sell_off_plan",
        "review:sell_fly",
        "review_feedback:sell_fly_confirmed",
    }:
        return True
    if token_key in {
        "emotion:急躁",
        "emotion:慌张",
        "emotion:冲动",
        "emotion:上头",
        "emotion:贪心",
        "emotion:害怕",
    }:
        return True
    return False


def _is_positive_token(token_key: str) -> bool:
    return token_key in {
        "execution:buy_in_plan",
        "execution:sell_in_plan",
        "review:good_exit",
        "review_feedback:discipline_kept",
        "review_feedback:good_exit_confirmed",
    }


def _reflection_prompt_for_gene(item: dict[str, Any], source: str) -> dict[str, Any]:
    token_key = str(item.get("token_key") or "")
    gene_type = str(item.get("gene_type") or "")
    gene_label = str(item.get("gene_label") or "")
    prompt_map = {
        "execution:buy_off_plan": ("纪律", "这次买点是否已经偏离原计划？如果偏离，触发你出手的那一刻到底看到了什么？"),
        "execution:sell_off_plan": ("纪律", "这次卖点是否偏离原计划？是风险变化、情绪波动，还是临盘被价格牵着走？"),
        "mistake:冲动追高": ("失误", "这次是否又有‘怕错过就放宽标准’的冲动追高痕迹？"),
        "mistake:拿不稳": ("失误", "这次若提前离场，你最担心失去的是什么？是利润回撤，还是对波动的不适？"),
        "emotion:急躁": ("情绪", "这次出手前，你是否因为着急而跳过了原本要确认的条件？"),
        "emotion:慌张": ("情绪", "这次决策里，是否有因为怕跌、怕错、怕回撤而被动动作的成分？"),
        "emotion:害怕": ("情绪", "这次是否因为害怕错过或害怕回撤，导致动作变形？"),
        "emotion:冲动": ("情绪", "这次如果回放下单前 30 秒，你觉得自己更像是执行计划还是情绪推动？"),
        "review:sell_fly": ("回顾", "这次卖出后，如果后面继续涨，你会把原因归结为纪律执行，还是过早离场？"),
        "review_feedback:sell_fly_confirmed": ("回顾反馈", "历史上你已经多次确认过‘卖飞’，这次卖点要不要先写下离场依据，再决定是否兑现？"),
        "review_feedback:discipline_kept": ("回顾反馈", "历史经验显示你有些卖点虽然少赚，但纪律是有效的；这次是否也属于‘该走就走’？"),
    }
    topic, question = prompt_map.get(
        token_key,
        (
            gene_type or "复盘",
            f"这次是否又出现了“{gene_label}”？如果出现，它更像环境问题、执行问题，还是情绪问题？",
        ),
    )
    return {
        "source": source,
        "token_key": token_key,
        "gene_type": gene_type,
        "gene_label": gene_label,
        "topic": topic,
        "question": question,
    }


def _checklist_item_for_path(item: dict[str, Any]) -> str:
    return f"复核：如果想复用“{item['path_key']}”，这次是否真的满足其中至少两个关键条件？"


def _checklist_item_for_gene(item: dict[str, Any], risk: bool = False) -> str:
    gene_label = str(item.get("gene_label") or "")
    if risk:
        return f"风控复核：这次是否又出现“{gene_label}”这类老问题？如果有，先把偏离原因记下来。"
    return f"复核：若想复用“{gene_label}”，请确认这次不是标签相似但条件已变形。"


def build_evolution_report(
    trades: list[dict[str, Any]],
    reviews: list[dict[str, Any]] | None,
    lookback_days: int,
    min_samples: int = 2,
) -> dict[str, Any]:
    closed = [item for item in trades if item.get("status") == "closed" and item.get("actual_return_pct") is not None]
    reviews_by_trade: dict[str, list[dict[str, Any]]] = {}
    for review in reviews or []:
        trade_id = str(review.get("trade_id") or "")
        if not trade_id:
            continue
        reviews_by_trade.setdefault(trade_id, []).append(review)
    token_buckets: dict[str, dict[str, Any]] = {}
    path_buckets: dict[str, dict[str, Any]] = {}

    for trade in closed:
        pnl = float(trade.get("actual_return_pct") or 0.0)
        alpha = trade.get("timing_alpha_pct")
        holding = trade.get("holding_days")
        effective = _is_effective_trade(trade)
        for key, kind, label in _token_specs(trade, reviews_by_trade=reviews_by_trade):
            bucket = token_buckets.setdefault(
                key,
                {
                    "token_key": key,
                    "gene_type": kind,
                    "gene_label": label,
                    "returns": [],
                    "alphas": [],
                    "holding_days": [],
                    "wins": 0,
                    "losses": 0,
                    "effective_count": 0,
                    "trade_ids": [],
                },
            )
            bucket["returns"].append(pnl)
            if alpha is not None:
                bucket["alphas"].append(float(alpha))
            if holding is not None:
                bucket["holding_days"].append(float(holding))
            bucket["wins"] += 1 if pnl > 0 else 0
            bucket["losses"] += 1 if pnl <= 0 else 0
            bucket["effective_count"] += 1 if effective else 0
            bucket["trade_ids"].append(trade.get("trade_id"))

        components = _quality_path_components(trade, reviews_by_trade=reviews_by_trade)
        if len(components) >= 2:
            path_key = " | ".join(components)
            bucket = path_buckets.setdefault(
                path_key,
                {
                    "path_key": path_key,
                    "components": components,
                    "returns": [],
                    "alphas": [],
                    "holding_days": [],
                    "wins": 0,
                    "losses": 0,
                    "effective_count": 0,
                    "examples": [],
                },
            )
            bucket["returns"].append(pnl)
            if alpha is not None:
                bucket["alphas"].append(float(alpha))
            if holding is not None:
                bucket["holding_days"].append(float(holding))
            bucket["wins"] += 1 if pnl > 0 else 0
            bucket["losses"] += 1 if pnl <= 0 else 0
            bucket["effective_count"] += 1 if effective else 0
            bucket["examples"].append(
                {
                    "trade_id": trade.get("trade_id"),
                    "name": trade.get("name") or trade.get("ts_code"),
                    "actual_return_pct": trade.get("actual_return_pct"),
                    "timing_alpha_pct": trade.get("timing_alpha_pct"),
                }
            )

    reusable_genes: list[dict[str, Any]] = []
    risk_genes: list[dict[str, Any]] = []
    for bucket in token_buckets.values():
        summary = _bucket_summary(bucket)
        payload = {
            "token_key": bucket["token_key"],
            "gene_type": bucket["gene_type"],
            "gene_label": bucket["gene_label"],
            "sample_trade_ids": bucket["trade_ids"][:10],
            **summary,
        }
        if summary["sample_size"] < min_samples:
            continue
        if _is_risk_token(bucket["token_key"]) or (summary["avg_actual_return_pct"] is not None and summary["avg_actual_return_pct"] < 0):
            risk_genes.append(payload)
        elif _is_positive_token(bucket["token_key"]) or (
            (summary["win_rate_pct"] or 0.0) >= 60 and (summary["avg_actual_return_pct"] or 0.0) > 0
        ):
            reusable_genes.append(payload)

    quality_paths: list[dict[str, Any]] = []
    for bucket in path_buckets.values():
        summary = _bucket_summary(bucket)
        if summary["sample_size"] < min_samples:
            continue
        if (summary["win_rate_pct"] or 0.0) < 60 or (summary["avg_actual_return_pct"] or 0.0) <= 0:
            continue
        quality_paths.append(
            {
                "path_key": bucket["path_key"],
                "components": bucket["components"],
                "examples": bucket["examples"][:5],
                **summary,
            }
        )

    reusable_genes.sort(
        key=lambda item: (
            item.get("positive_edge_score") or 0.0,
            item.get("avg_actual_return_pct") or 0.0,
            item.get("sample_size") or 0,
        ),
        reverse=True,
    )
    risk_genes.sort(
        key=lambda item: (
            item.get("sample_size") or 0,
            -(item.get("avg_actual_return_pct") or 0.0),
            item.get("loss_count") or 0,
        ),
        reverse=True,
    )
    quality_paths.sort(
        key=lambda item: (
            item.get("positive_edge_score") or 0.0,
            item.get("avg_actual_return_pct") or 0.0,
            item.get("sample_size") or 0,
        ),
        reverse=True,
    )
    total_samples = len(closed)
    for item in reusable_genes:
        item.update(_bandit_metrics(item, total_samples, risk=False))
    for item in risk_genes:
        item.update(_bandit_metrics(item, total_samples, risk=True))
    for item in quality_paths:
        item.update(_bandit_metrics(item, total_samples, risk=False))

    bandit_candidates: list[dict[str, Any]] = []
    for item in quality_paths:
        bandit_candidates.append(
            {
                "arm_type": "path",
                "arm_label": item["path_key"],
                "path_key": item["path_key"],
                "sample_size": item["sample_size"],
                "posterior_mean": item["posterior_mean"],
                "ucb_score": item["ucb_score"],
                "conservative_score": item["conservative_score"],
                "exploration_bonus": item["exploration_bonus"],
            }
        )
    for item in reusable_genes:
        bandit_candidates.append(
            {
                "arm_type": "gene",
                "arm_label": item["gene_label"],
                "token_key": item["token_key"],
                "gene_type": item["gene_type"],
                "sample_size": item["sample_size"],
                "posterior_mean": item["posterior_mean"],
                "ucb_score": item["ucb_score"],
                "conservative_score": item["conservative_score"],
                "exploration_bonus": item["exploration_bonus"],
            }
        )
    bandit_candidates.sort(
        key=lambda item: (
            item.get("ucb_score") or 0.0,
            item.get("posterior_mean") or 0.0,
            item.get("sample_size") or 0,
        ),
        reverse=True,
    )
    risk_bandit_arms = [
        {
            "arm_type": "risk_gene",
            "arm_label": item["gene_label"],
            "token_key": item["token_key"],
            "gene_type": item["gene_type"],
            "sample_size": item["sample_size"],
            "risk_penalty_score": item.get("risk_penalty_score"),
            "posterior_mean": item["posterior_mean"],
        }
        for item in risk_genes
    ]
    risk_bandit_arms.sort(
        key=lambda item: (
            item.get("risk_penalty_score") or 0.0,
            -(item.get("posterior_mean") or 0.0),
            item.get("sample_size") or 0,
        ),
        reverse=True,
    )
    policy_stack = {
        "recommended_mode": "contextual_bandit",
        "why": "当前样本是交易级闭环记录，更适合先做上下文匹配 + bandit 排序，而不是直接上全量强化学习策略。",
        "future_upgrade": "等后续补齐更细粒度的盘中状态、动作和回报轨迹，再升级到 offline RL / trajectory policy。",
        "top_exploit_arm": bandit_candidates[0] if bandit_candidates else {},
        "top_risk_arm": risk_bandit_arms[0] if risk_bandit_arms else {},
    }

    markdown_lines = [
        f"# 自进化报告 | 最近 {lookback_days} 天",
        "",
        f"- 闭环样本数: {len(closed)}",
        f"- 可复用优质路径数: {len(quality_paths)}",
        f"- 正向可复用基因数: {len(reusable_genes)}",
        f"- 风险基因数: {len(risk_genes)}",
        "",
        "## 优质路径",
    ]
    if quality_paths:
        for item in quality_paths[:8]:
            markdown_lines.append(
                f"- {item['path_key']} | 样本 {item['sample_size']} | 胜率 {item['win_rate_pct']}% | "
                f"平均收益 {item['avg_actual_return_pct']}% | 平均 alpha {item['avg_timing_alpha_pct']}%"
            )
    else:
        markdown_lines.append("- 暂无达到阈值的优质路径。")
    markdown_lines.extend(["", "## 可复用基因"])
    if reusable_genes:
        for item in reusable_genes[:10]:
            markdown_lines.append(
                f"- {item['gene_type']}:{item['gene_label']} | 样本 {item['sample_size']} | 胜率 {item['win_rate_pct']}% | "
                f"平均收益 {item['avg_actual_return_pct']}% | 平均 alpha {item['avg_timing_alpha_pct']}%"
            )
    else:
        markdown_lines.append("- 暂无达到阈值的正向基因。")
    markdown_lines.extend(["", "## 风险基因"])
    if risk_genes:
        for item in risk_genes[:10]:
            markdown_lines.append(
                f"- {item['gene_type']}:{item['gene_label']} | 样本 {item['sample_size']} | 胜率 {item['win_rate_pct']}% | "
                f"平均收益 {item['avg_actual_return_pct']}%"
            )
    else:
        markdown_lines.append("- 暂无显著风险基因。")
    markdown_lines.extend(["", "## Bandit 视角"])
    if bandit_candidates:
        for item in bandit_candidates[:5]:
            markdown_lines.append(
                f"- {item['arm_type']}:{item['arm_label']} | posterior {item['posterior_mean']} | "
                f"ucb {item['ucb_score']} | 探索奖励 {item['exploration_bonus']}"
            )
    else:
        markdown_lines.append("- 当前样本仍不足以形成稳定的 bandit 排序。")
    if risk_bandit_arms:
        markdown_lines.append("- 风险优先规避：" + "、".join(item["arm_label"] for item in risk_bandit_arms[:3]))
    markdown_lines.append(
        "- 当前建议先用 contextual bandit 做提醒排序；若未来补齐更细粒度状态/动作轨迹，再升级到 offline RL。"
    )
    markdown_lines.append("")
    markdown_lines.append("这些结果只基于你的历史轨迹，用于提醒你复用优质路径、规避重复犯错。")

    return {
        "lookback_days": lookback_days,
        "sample_size": len(closed),
        "quality_paths": quality_paths,
        "reusable_genes": reusable_genes,
        "risk_genes": risk_genes,
        "bandit_candidates": bandit_candidates[:8],
        "risk_bandit_arms": risk_bandit_arms[:8],
        "policy_stack": policy_stack,
        "markdown": "\n".join(markdown_lines).strip() + "\n",
    }


def build_evolution_reminder(
    trades: list[dict[str, Any]],
    reviews: list[dict[str, Any]] | None,
    logic_tags: Iterable[str] | None,
    pattern_tags: Iterable[str] | None,
    market_stage: str | None,
    environment_tags: Iterable[str] | None,
    lookback_days: int,
    min_samples: int = 2,
) -> dict[str, Any]:
    report = build_evolution_report(trades, reviews=reviews, lookback_days=lookback_days, min_samples=min_samples)
    query_logic = split_tags(list(logic_tags or []))
    query_pattern = split_tags(list(pattern_tags or []))
    query_environment = split_tags(list(environment_tags or []))
    query_tokens: set[str] = set()
    query_tokens.update(f"logic:{tag}" for tag in query_logic)
    query_tokens.update(f"pattern:{tag}" for tag in query_pattern)
    query_tokens.update(f"environment:{tag}" for tag in query_environment)
    if market_stage:
        query_tokens.add(f"stage:{market_stage}")

    matched_paths: list[dict[str, Any]] = []
    for item in report["quality_paths"]:
        path_tokens: set[str] = set()
        for component in item["components"]:
            if component.startswith("逻辑="):
                path_tokens.add(f"logic:{component.split('=', 1)[1]}")
            elif component.startswith("形态="):
                path_tokens.add(f"pattern:{component.split('=', 1)[1]}")
            elif component.startswith("阶段="):
                path_tokens.add(f"stage:{component.split('=', 1)[1]}")
            elif component.startswith("环境="):
                path_tokens.add(f"environment:{component.split('=', 1)[1]}")
        overlap = len(path_tokens & query_tokens)
        if overlap >= 2 or (overlap >= 1 and len(query_tokens) <= 2):
            path_copy = dict(item)
            path_copy["overlap_count"] = overlap
            matched_paths.append(path_copy)

    matched_genes = [item for item in report["reusable_genes"] if item["token_key"] in query_tokens]
    matched_risks = [item for item in report["risk_genes"] if item["token_key"] in query_tokens]
    habit_risks = [
        item
        for item in report["risk_genes"]
        if item.get("gene_type") in {"纪律", "情绪", "失误", "回顾"}
    ][:3]
    matched_paths.sort(
        key=lambda item: (
            item.get("overlap_count") or 0,
            item.get("ucb_score") or 0.0,
            item.get("positive_edge_score") or 0.0,
        ),
        reverse=True,
    )
    matched_genes.sort(key=lambda item: (item.get("ucb_score") or 0.0, item.get("sample_size") or 0), reverse=True)
    matched_risks.sort(key=lambda item: (item.get("risk_penalty_score") or 0.0, item.get("sample_size") or 0), reverse=True)

    reminders: list[str] = []
    for item in matched_paths[:3]:
        reminders.append(
            f"优质路径提醒：你过去在“{item['path_key']}”下有 {item['sample_size']} 笔样本，"
            f"胜率 {item['win_rate_pct']}%，平均收益 {item['avg_actual_return_pct']}%。"
        )
    for item in matched_genes[:3]:
        reminders.append(
            f"可复用基因提醒：{item['gene_type']}“{item['gene_label']}”历史样本 {item['sample_size']} 笔，"
            f"平均收益 {item['avg_actual_return_pct']}%，可核对这次是否仍满足同类条件。"
        )
    for item in matched_risks[:2]:
        reminders.append(
            f"风险提醒：{item['gene_type']}“{item['gene_label']}”历史表现偏弱，"
            f"样本 {item['sample_size']} 笔，平均收益 {item['avg_actual_return_pct']}%。"
        )
    for item in habit_risks[:2]:
        if item in matched_risks:
            continue
        reminders.append(
            f"习惯风险提醒：你历史上在“{item['gene_type']}:{item['gene_label']}”上反复吃亏，"
            f"样本 {item['sample_size']} 笔，平均收益 {item['avg_actual_return_pct']}%。"
        )
    if not reminders:
        reminders.append("当前标签与既有优质路径重合度不高，优先按计划记录，本次也会成为新的训练样本。")

    reflection_prompts: list[dict[str, Any]] = []
    for source_name, items in (("matched_risk", matched_risks[:3]), ("habit_risk", habit_risks[:3])):
        for item in items:
            reflection_prompts.append(_reflection_prompt_for_gene(item, source=source_name))
    deduped_prompts: list[dict[str, Any]] = []
    seen_prompt_keys: set[str] = set()
    for prompt in reflection_prompts:
        token_key = str(prompt.get("token_key") or "")
        if token_key in seen_prompt_keys:
            continue
        seen_prompt_keys.add(token_key)
        deduped_prompts.append(prompt)
    reflection_prompts = deduped_prompts[:4]

    pre_trade_checklist: list[str] = []
    for item in matched_paths[:2]:
        pre_trade_checklist.append(_checklist_item_for_path(item))
    for item in matched_genes[:2]:
        pre_trade_checklist.append(_checklist_item_for_gene(item, risk=False))
    for item in matched_risks[:2]:
        pre_trade_checklist.append(_checklist_item_for_gene(item, risk=True))
    if not pre_trade_checklist and habit_risks:
        pre_trade_checklist.append(_checklist_item_for_gene(habit_risks[0], risk=True))
    if not pre_trade_checklist:
        pre_trade_checklist.append("若暂无足够相似路径，先把本次计划、理由和止损边界记清楚，把它沉淀成下一笔样本。")

    adaptive_policy = {
        "recommended_mode": report.get("policy_stack", {}).get("recommended_mode") or "contextual_bandit",
        "top_exploit": matched_paths[0] if matched_paths else (matched_genes[0] if matched_genes else {}),
        "top_risk": matched_risks[0] if matched_risks else (habit_risks[0] if habit_risks else {}),
        "decision_bias": "exploit" if matched_paths or matched_genes else "observe",
    }

    markdown_lines = [
        "# 自进化提醒",
        "",
        f"- 查询逻辑: {', '.join(query_logic) or '-'}",
        f"- 查询形态: {', '.join(query_pattern) or '-'}",
        f"- 查询阶段: {market_stage or '-'}",
        f"- 查询环境: {', '.join(query_environment) or '-'}",
        "",
    ]
    for item in reminders:
        markdown_lines.append(f"- {item}")
    if pre_trade_checklist:
        markdown_lines.extend(["", "## 复核清单"])
        for item in pre_trade_checklist[:5]:
            markdown_lines.append(f"- {item}")
    if reflection_prompts:
        markdown_lines.extend(["", "## 反思追问"])
        for item in reflection_prompts:
            markdown_lines.append(f"- [{item['topic']}] {item['question']}")
    if adaptive_policy["top_exploit"] or adaptive_policy["top_risk"]:
        markdown_lines.extend(["", "## 自适应策略视角"])
        if adaptive_policy["top_exploit"]:
            exploit = adaptive_policy["top_exploit"]
            label = exploit.get("path_key") or exploit.get("gene_label") or exploit.get("arm_label") or ""
            markdown_lines.append(
                f"- 当前更值得优先复核的历史臂是“{label}”，bandit 分数 {exploit.get('ucb_score') or exploit.get('posterior_mean') or '-'}。"
            )
        if adaptive_policy["top_risk"]:
            risk = adaptive_policy["top_risk"]
            label = risk.get("gene_label") or risk.get("arm_label") or ""
            markdown_lines.append(
                f"- 当前最该压制的风险臂是“{label}”，风险分数 {risk.get('risk_penalty_score') or risk.get('posterior_mean') or '-'}。"
            )
    markdown_lines.extend(["", "这些路径和基因只是你的历史索引，不是自动交易规则。"])

    return {
        "query": {
            "logic_tags": query_logic,
            "pattern_tags": query_pattern,
            "market_stage": market_stage or "",
            "environment_tags": query_environment,
        },
        "sample_size": report["sample_size"],
        "matched_quality_paths": matched_paths[:5],
        "matched_reusable_genes": matched_genes[:5],
        "matched_risk_genes": matched_risks[:5],
        "habit_risk_genes": habit_risks,
        "reminders": reminders,
        "pre_trade_checklist": pre_trade_checklist[:5],
        "reflection_prompts": reflection_prompts,
        "adaptive_policy": adaptive_policy,
        "soft_structure_note": "这些路径和基因只用于提醒你复用经验、识别风险，不用于自动下单。",
        "markdown": "\n".join(markdown_lines).strip() + "\n",
    }


def _counter_payload(counter: Counter[str], limit: int = 5) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def _stage_counter(trades: list[dict[str, Any]], positive: bool) -> Counter[str]:
    counter: Counter[str] = Counter()
    for trade in trades:
        pnl = trade.get("actual_return_pct")
        if pnl is None:
            continue
        if positive and pnl <= 0:
            continue
        if not positive and pnl >= 0:
            continue
        stage = str(trade.get("market_stage_tag") or "").strip()
        if stage:
            counter.update([stage])
    return counter


def _execution_profile(trades: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for trade in trades:
        for token_key, _, _ in _execution_tokens(trade):
            counter.update([token_key])
    buy_in_plan = counter.get("execution:buy_in_plan", 0)
    buy_off_plan = counter.get("execution:buy_off_plan", 0)
    sell_in_plan = counter.get("execution:sell_in_plan", 0)
    sell_off_plan = counter.get("execution:sell_off_plan", 0)
    total_buy = buy_in_plan + buy_off_plan
    total_sell = sell_in_plan + sell_off_plan
    buy_in_plan_rate = round(buy_in_plan / total_buy * 100, 2) if total_buy else None
    sell_in_plan_rate = round(sell_in_plan / total_sell * 100, 2) if total_sell else None
    return {
        "buy_in_plan_count": buy_in_plan,
        "buy_off_plan_count": buy_off_plan,
        "sell_in_plan_count": sell_in_plan,
        "sell_off_plan_count": sell_off_plan,
        "buy_in_plan_rate_pct": buy_in_plan_rate,
        "sell_in_plan_rate_pct": sell_in_plan_rate,
    }


def build_style_portrait(
    trades: list[dict[str, Any]],
    reviews: list[dict[str, Any]] | None,
    lookback_days: int,
    min_samples: int = 2,
) -> dict[str, Any]:
    closed = [item for item in trades if item.get("status") == "closed" and item.get("actual_return_pct") is not None]
    evolution = build_evolution_report(closed, reviews=reviews, lookback_days=lookback_days, min_samples=min_samples)
    profitable_tags = _top_tags(closed, positive=True)
    losing_tags = _top_tags(closed, positive=False)
    profitable_stages = _counter_payload(_stage_counter(closed, positive=True), limit=3)
    losing_stages = _counter_payload(_stage_counter(closed, positive=False), limit=3)
    emotion_counter: Counter[str] = Counter()
    mistake_counter: Counter[str] = Counter()
    for trade in closed:
        emotion_counter.update(_emotion_tags(trade))
        mistake_counter.update(split_tags(json_loads(trade.get("mistake_tags_json"), [])))
    emotions = _counter_payload(emotion_counter, limit=5)
    mistakes = _counter_payload(mistake_counter, limit=5)
    execution_profile = _execution_profile(closed)
    adaptive_policy_profile = {
        "recommended_mode": evolution.get("policy_stack", {}).get("recommended_mode") or "contextual_bandit",
        "top_exploit_arms": evolution.get("bandit_candidates", [])[:3],
        "top_risk_arms": evolution.get("risk_bandit_arms", [])[:3],
    }

    portrait_summary: list[str] = []
    if evolution["quality_paths"]:
        top_path = evolution["quality_paths"][0]
        portrait_summary.append(
            f"你的优势更常集中在“{top_path['path_key']}”，当前样本 {top_path['sample_size']} 笔，平均收益 {top_path['avg_actual_return_pct']}%。"
        )
    if profitable_tags:
        portrait_summary.append(
            "盈利侧更常出现的标签是：" + "、".join(item["tag"] for item in profitable_tags[:3]) + "。"
        )
    if evolution["risk_genes"]:
        top_risk = evolution["risk_genes"][0]
        portrait_summary.append(
            f"当前最明显的风险基因是“{top_risk['gene_label']}”，样本 {top_risk['sample_size']} 笔，平均收益 {top_risk['avg_actual_return_pct']}%。"
        )
    if execution_profile.get("buy_in_plan_rate_pct") is not None:
        portrait_summary.append(
            f"你的买点计划内执行率约为 {execution_profile['buy_in_plan_rate_pct']}%，这通常决定了节奏是否稳定。"
        )
    if adaptive_policy_profile["top_exploit_arms"]:
        portrait_summary.append(
            f"从 bandit 视角看，你当前最稳的可复用臂更偏向“{adaptive_policy_profile['top_exploit_arms'][0]['arm_label']}”。"
        )
    if not portrait_summary:
        portrait_summary.append("当前闭环样本仍偏少，先继续积累真实记录，再逐步形成更稳定的风格画像。")

    reflection_prompts: list[dict[str, Any]] = []
    for item in evolution["risk_genes"][:3]:
        reflection_prompts.append(_reflection_prompt_for_gene(item, source="style_portrait"))
    if execution_profile.get("buy_in_plan_rate_pct") is not None and execution_profile["buy_in_plan_rate_pct"] < 50:
        reflection_prompts.append(
            {
                "source": "style_portrait",
                "token_key": "execution:buy_plan_rate",
                "gene_type": "纪律",
                "gene_label": "买点计划内执行率偏低",
                "topic": "纪律",
                "question": "你最容易在哪种情况下放宽买点标准？是怕错过、情绪上头，还是临盘被板块拉升带走？",
            }
        )
    deduped_prompts: list[dict[str, Any]] = []
    seen_prompt_keys: set[str] = set()
    for prompt in reflection_prompts:
        token_key = str(prompt.get("token_key") or "")
        if token_key in seen_prompt_keys:
            continue
        seen_prompt_keys.add(token_key)
        deduped_prompts.append(prompt)
    reflection_prompts = deduped_prompts[:5]

    markdown_lines = [
        f"# 个人风格画像 | 最近 {lookback_days} 天",
        "",
        f"- 闭环样本数: {len(closed)}",
        f"- 优质路径数: {len(evolution['quality_paths'])}",
        f"- 可复用基因数: {len(evolution['reusable_genes'])}",
        f"- 风险基因数: {len(evolution['risk_genes'])}",
        "",
        "## 一句话画像",
    ]
    for item in portrait_summary:
        markdown_lines.append(f"- {item}")
    markdown_lines.extend(["", "## 优势区域"])
    if evolution["quality_paths"]:
        for item in evolution["quality_paths"][:3]:
            markdown_lines.append(
                f"- {item['path_key']} | 样本 {item['sample_size']} | 胜率 {item['win_rate_pct']}% | 平均收益 {item['avg_actual_return_pct']}%"
            )
    else:
        markdown_lines.append("- 暂无足够稳定的优势路径。")
    if profitable_tags:
        markdown_lines.append("- 盈利标签聚焦：" + "、".join(f"{item['tag']}({item['count']})" for item in profitable_tags[:5]))
    if profitable_stages:
        markdown_lines.append("- 更常赚钱的市场阶段：" + "、".join(f"{item['label']}({item['count']})" for item in profitable_stages))
    markdown_lines.extend(["", "## 风险区域"])
    if evolution["risk_genes"]:
        for item in evolution["risk_genes"][:5]:
            markdown_lines.append(
                f"- {item['gene_type']}:{item['gene_label']} | 样本 {item['sample_size']} | 平均收益 {item['avg_actual_return_pct']}%"
            )
    else:
        markdown_lines.append("- 暂无显著风险基因。")
    if losing_tags:
        markdown_lines.append("- 亏损标签聚焦：" + "、".join(f"{item['tag']}({item['count']})" for item in losing_tags[:5]))
    if losing_stages:
        markdown_lines.append("- 更常失手的市场阶段：" + "、".join(f"{item['label']}({item['count']})" for item in losing_stages))
    markdown_lines.extend(["", "## 情绪与纪律画像"])
    if emotions:
        markdown_lines.append("- 高频情绪词：" + "、".join(f"{item['label']}({item['count']})" for item in emotions))
    else:
        markdown_lines.append("- 高频情绪词：样本不足。")
    if mistakes:
        markdown_lines.append("- 高频失误词：" + "、".join(f"{item['label']}({item['count']})" for item in mistakes))
    else:
        markdown_lines.append("- 高频失误词：样本不足。")
    markdown_lines.append(
        f"- 买点计划内执行率：{_format_pct(execution_profile.get('buy_in_plan_rate_pct'))} | 卖点计划内执行率：{_format_pct(execution_profile.get('sell_in_plan_rate_pct'))}"
    )
    if adaptive_policy_profile["top_exploit_arms"]:
        markdown_lines.extend(["", "## 自适应策略画像"])
        markdown_lines.append(
            "- 更值得优先复核的臂：" + "、".join(item["arm_label"] for item in adaptive_policy_profile["top_exploit_arms"])
        )
    if adaptive_policy_profile["top_risk_arms"]:
        markdown_lines.append(
            "- 更该先压制的风险臂：" + "、".join(item["arm_label"] for item in adaptive_policy_profile["top_risk_arms"])
        )
    if reflection_prompts:
        markdown_lines.extend(["", "## 下次值得先问自己的问题"])
        for item in reflection_prompts:
            markdown_lines.append(f"- [{item['topic']}] {item['question']}")
    markdown_lines.extend(["", "以上画像只基于你的历史轨迹，用于帮助你识别自己的风格和边界，不构成交易建议。"])

    return {
        "lookback_days": lookback_days,
        "sample_size": len(closed),
        "portrait_summary": portrait_summary,
        "advantage_paths": evolution["quality_paths"][:5],
        "advantage_tags": profitable_tags,
        "risk_genes": evolution["risk_genes"][:8],
        "risk_tags": losing_tags,
        "emotion_profile": emotions,
        "mistake_profile": mistakes,
        "profitable_stages": profitable_stages,
        "losing_stages": losing_stages,
        "execution_profile": execution_profile,
        "adaptive_policy_profile": adaptive_policy_profile,
        "reflection_prompts": reflection_prompts,
        "evolution_report": {
            "quality_paths": evolution["quality_paths"][:5],
            "reusable_genes": evolution["reusable_genes"][:8],
            "risk_genes": evolution["risk_genes"][:8],
            "bandit_candidates": evolution.get("bandit_candidates", [])[:8],
            "risk_bandit_arms": evolution.get("risk_bandit_arms", [])[:8],
        },
        "soft_structure_note": "这份画像是对你历史轨迹的描述性压缩，不是策略代码，也不是自动规则。",
        "markdown": "\n".join(markdown_lines).strip() + "\n",
    }


def _format_pct(value: float | None) -> str:
    return f"{value:.2f}%" if value is not None else "N/A"


def _round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _logic_focus(trades: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {"profitable": _top_tags(trades, positive=True), "losing": _top_tags(trades, positive=False)}


def _position_change_after_loss_streak(trades: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [item for item in trades if item.get("actual_return_pct") is not None]
    closed.sort(key=lambda item: (item.get("sell_date") or item.get("buy_date") or "", item.get("trade_id") or ""))
    alerts: list[dict[str, Any]] = []
    streak = 0
    for index, trade in enumerate(closed):
        pnl = trade.get("actual_return_pct")
        if pnl is None:
            continue
        if pnl <= 0:
            streak += 1
            continue
        if streak >= 3 and index > 0:
            history = closed[max(0, index - streak):index]
            sizes = [item.get("position_size_pct") for item in history if item.get("position_size_pct") is not None]
            next_size = trade.get("position_size_pct")
            baseline = sum(sizes) / len(sizes) if sizes else None
            if baseline is not None and next_size is not None:
                alerts.append(
                    {
                        "trade_id": trade.get("trade_id"),
                        "baseline_position_pct": round(baseline, 2),
                        "next_position_pct": round(next_size, 2),
                        "expanded": next_size > baseline * 1.2,
                    }
                )
        streak = 0
    expanded = [item for item in alerts if item.get("expanded")]
    return {"evaluated_cases": len(alerts), "expanded_cases": len(expanded), "cases": alerts}


def _post_big_win_frequency(trades: list[dict[str, Any]], period_start: str, period_end: str) -> dict[str, Any]:
    closed = [item for item in trades if item.get("buy_date") and item.get("actual_return_pct") is not None]
    if not closed:
        return {"trigger_count": 0, "avg_follow_up_count": None, "baseline_three_day_count": None, "cases": []}
    span_days = max((to_date(period_end) - to_date(period_start)).days + 1, 1)
    baseline = len(closed) / span_days * 3
    cases = []
    for trade in closed:
        if (trade.get("actual_return_pct") or 0) <= 10:
            continue
        anchor = to_date(trade.get("sell_date") or trade.get("buy_date"))
        follow_ups = 0
        for other in closed:
            if other.get("trade_id") == trade.get("trade_id"):
                continue
            buy_token = other.get("buy_date")
            if not buy_token:
                continue
            delta = (to_date(buy_token) - anchor).days
            if 0 < delta <= 3:
                follow_ups += 1
        cases.append({"trade_id": trade.get("trade_id"), "follow_up_count": follow_ups, "actual_return_pct": trade.get("actual_return_pct")})
    avg_follow_up = sum(item["follow_up_count"] for item in cases) / len(cases) if cases else None
    return {
        "trigger_count": len(cases),
        "avg_follow_up_count": _round_or_none(avg_follow_up),
        "baseline_three_day_count": _round_or_none(baseline),
        "cases": cases,
    }


def generate_health_report_payload(
    plans: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    valid_plans = plans
    executed_plans = [item for item in valid_plans if item.get("status") == "executed"]
    closed_trades = [item for item in trades if item.get("status") == "closed"]
    linked_trades = [item for item in closed_trades if item.get("plan_id")]
    off_plan_trades = [item for item in closed_trades if not item.get("plan_id")]
    plan_execution_rate = round(len(executed_plans) / len(valid_plans) * 100, 2) if valid_plans else None
    off_plan_ratio = round(len(off_plan_trades) / len(closed_trades) * 100, 2) if closed_trades else None

    actual_holding_values = [float(item["holding_days"]) for item in linked_trades if item.get("holding_days") is not None]
    avg_actual_holding = round(sum(actual_holding_values) / len(actual_holding_values), 2) if actual_holding_values else None
    plan_map = {item["plan_id"]: item for item in valid_plans if item.get("plan_id")}
    planned_holding_values = []
    for trade in linked_trades:
        plan = plan_map.get(trade.get("plan_id"))
        if not plan:
            continue
        value = parse_holding_days(plan.get("holding_period"))
        if value is not None:
            planned_holding_values.append(value)
    avg_planned_holding = round(sum(planned_holding_values) / len(planned_holding_values), 2) if planned_holding_values else None
    holding_bias_pct = None
    if avg_actual_holding is not None and avg_planned_holding not in (None, 0):
        holding_bias_pct = round((avg_actual_holding - avg_planned_holding) / avg_planned_holding * 100, 2)

    stop_loss_candidates = []
    stop_loss_executed = 0
    for trade in linked_trades:
        plan = plan_map.get(trade.get("plan_id"))
        if not plan:
            continue
        stop_bounds = parse_numeric_range(plan.get("stop_loss"))
        if not stop_bounds or trade.get("sell_price") is None:
            continue
        stop_loss_candidates.append(trade)
        sell_reason = f"{trade.get('sell_reason') or ''} {trade.get('sell_position') or ''}"
        stop_price = stop_bounds[1]
        if "止损" in sell_reason or float(trade["sell_price"]) <= stop_price * 1.01:
            stop_loss_executed += 1
    stop_loss_execution_rate = round(stop_loss_executed / len(stop_loss_candidates) * 100, 2) if stop_loss_candidates else None

    loss_streak = _position_change_after_loss_streak(closed_trades)
    big_win_frequency = _post_big_win_frequency(closed_trades, period_start, period_end)
    logic_focus = _logic_focus(closed_trades)
    sell_fly_reviews = [item for item in reviews if item.get("review_type") == "sell_fly"]

    metrics = {
        "plan_execution_rate_pct": plan_execution_rate,
        "off_plan_trade_ratio_pct": off_plan_ratio,
        "avg_actual_holding_days": avg_actual_holding,
        "avg_planned_holding_days": avg_planned_holding,
        "holding_bias_pct": holding_bias_pct,
        "stop_loss_execution_rate_pct": stop_loss_execution_rate,
        "stop_loss_sample_size": len(stop_loss_candidates),
        "loss_streak_position_behavior": loss_streak,
        "post_big_win_frequency": big_win_frequency,
        "logic_focus": logic_focus,
        "sell_fly_review_count": len(sell_fly_reviews),
    }

    lines = [
        f"# 交易行为体检报告 | {period_start}-{period_end}",
        "",
        f"本期闭环交易 {len(closed_trades)} 笔，关联有效计划 {len(valid_plans)} 份。",
        "",
        f"- 计划执行率: {_format_pct(plan_execution_rate)}",
        f"- 计划外交易占比: {_format_pct(off_plan_ratio)}",
        f"- 实际平均持仓天数: {avg_actual_holding if avg_actual_holding is not None else 'N/A'}",
        f"- 计划平均持仓天数: {avg_planned_holding if avg_planned_holding is not None else 'N/A'}",
        f"- 持仓周期偏离: {_format_pct(holding_bias_pct)}",
        f"- 止损执行率(近似): {_format_pct(stop_loss_execution_rate)}",
        f"- 卖飞回顾触发数: {len(sell_fly_reviews)}",
        "",
    ]
    if plan_execution_rate is not None:
        if plan_execution_rate >= 60:
            lines.append(f"计划纪律相对稳定，执行率为 {plan_execution_rate:.2f}%。")
        else:
            lines.append(f"计划执行率偏低，仅 {plan_execution_rate:.2f}%，盘中临时决策可能偏多。")
    if holding_bias_pct is not None:
        if holding_bias_pct <= -30:
            lines.append(f"实际持仓显著短于计划，偏离 {holding_bias_pct:.2f}%，存在提前离场倾向。")
        elif holding_bias_pct >= 30:
            lines.append(f"实际持仓显著长于计划，偏离 {holding_bias_pct:.2f}%，需要关注拖延止盈或止损。")
    if stop_loss_execution_rate is not None and stop_loss_execution_rate < 70:
        lines.append("止损执行率偏低，建议结合计划止损位与卖出理由复盘。")
    if loss_streak.get("expanded_cases"):
        lines.append(f"连续亏损后共有 {loss_streak['expanded_cases']} 次加大仓位的迹象，警惕报复性交易。")
    if big_win_frequency.get("trigger_count"):
        avg_follow_up = big_win_frequency.get("avg_follow_up_count")
        baseline = big_win_frequency.get("baseline_three_day_count")
        if avg_follow_up is not None and baseline is not None and avg_follow_up > baseline * 1.5:
            lines.append("大赚后交易频率显著提升，注意过度自信导致的计划外交易。")
    profitable_tags = logic_focus.get("profitable") or []
    losing_tags = logic_focus.get("losing") or []
    if profitable_tags:
        lines.append("盈利侧更常见标签: " + ", ".join(f"{item['tag']}({item['count']})" for item in profitable_tags[:5]))
    if losing_tags:
        lines.append("亏损侧更常见标签: " + ", ".join(f"{item['tag']}({item['count']})" for item in losing_tags[:5]))
    lines.append("以上结论仅基于个人历史记录，不构成任何交易建议。")

    return {
        "period_start": normalize_trade_date(period_start),
        "period_end": normalize_trade_date(period_end),
        "trade_count": len(closed_trades),
        "plan_count": len(valid_plans),
        "review_count": len(reviews),
        "metrics": metrics,
        "markdown": "\n".join(lines).strip() + "\n",
    }
