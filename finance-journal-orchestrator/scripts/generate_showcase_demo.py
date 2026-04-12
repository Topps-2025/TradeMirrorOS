#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_journal_core.app import create_app
from finance_journal_core.market_data import normalize_trade_date, shift_calendar_date


SHOWCASE_UNIVERSE = [
    {"ts_code": "603083", "theme": "CPO光模块"},
    {"ts_code": "300308", "theme": "算力链"},
    {"ts_code": "002281", "theme": "光模块"},
    {"ts_code": "300059", "theme": "互联网金融"},
    {"ts_code": "000977", "theme": "服务器算力"},
    {"ts_code": "002230", "theme": "AI应用"},
    {"ts_code": "000063", "theme": "通信设备"},
    {"ts_code": "002475", "theme": "消费电子"},
    {"ts_code": "600519", "theme": "白马消费"},
    {"ts_code": "601318", "theme": "金融权重"},
]

SHOWCASE_KEYWORDS = ["CPO", "算力", "AI应用", "机器人", "券商", "消费"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate showcase demo runtime with real Tushare prices and simulated reasons.")
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT / "_runtime_showcase_202602_202604"),
        help="Runtime root for the generated showcase dataset",
    )
    parser.add_argument("--start-date", default="20260203")
    parser.add_argument("--end-date", default="20260410")
    parser.add_argument("--brief-date", default="20260411")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--max-trades", type=int, default=14)
    return parser


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _trade_profile(bars: list[dict[str, Any]], entry_idx: int, theme: str) -> dict[str, Any]:
    bar = bars[entry_idx]
    prev_close = _float(bars[entry_idx - 1].get("close")) if entry_idx > 0 else _float(bar.get("close"))
    close_price = _float(bar.get("close"))
    pct_chg = _float(bar.get("pct_chg"))
    ma5 = _avg([_float(item.get("close")) for item in bars[max(0, entry_idx - 4): entry_idx + 1]])

    if pct_chg >= 4.0:
        return {
            "logic_tags": ["半路追涨"],
            "pattern_tags": ["放量突破"],
            "market_stage": "高位分歧",
            "environment_tags": [theme, "题材发酵"],
            "thesis": f"{theme} 方向临盘加速，模拟按强势扩散思路参与。",
            "buy_zone": f"{close_price * 0.97:.2f}-{close_price * 0.985:.2f}",
            "sell_zone": f"{close_price * 1.06:.2f}-{close_price * 1.09:.2f}",
            "holding_period": "2-4天",
            "emotion_notes": "盘中怕错过主线扩散，出手偏快。",
            "mistake_tags": ["冲动追高"],
            "lessons_if_loss": "强势追击也要等分时回踩确认，不能只看板块热度。",
            "lessons_if_win": "强势板块可以跟，但仍要把追涨边界写清楚。",
        }
    if close_price <= ma5 * 0.995 or close_price <= prev_close * 1.01:
        return {
            "logic_tags": ["低吸"],
            "pattern_tags": ["均线回踩"],
            "market_stage": "震荡市",
            "environment_tags": [theme, "修复回流"],
            "thesis": f"{theme} 方向出现分歧回踩，模拟按修复回流的低吸计划处理。",
            "buy_zone": f"{close_price * 0.985:.2f}-{close_price * 1.005:.2f}",
            "sell_zone": f"{close_price * 1.04:.2f}-{close_price * 1.08:.2f}",
            "holding_period": "3-5天",
            "emotion_notes": "整体能按预案执行，但盘中仍会担心修复力度不够。",
            "mistake_tags": ["拿不稳"],
            "lessons_if_loss": "低吸也要接受继续分歧，不能把回踩想成马上反转。",
            "lessons_if_win": "回踩低吸更适合分批兑现，不必急着一次性卖完。",
        }
    return {
        "logic_tags": ["低吸"],
        "pattern_tags": ["平台整理"],
        "market_stage": "震荡市",
        "environment_tags": [theme, "轮动修复"],
        "thesis": f"{theme} 方向处于轮动修复段，模拟按平台整理后的低位试错参与。",
        "buy_zone": f"{close_price * 0.99:.2f}-{close_price * 1.01:.2f}",
        "sell_zone": f"{close_price * 1.03:.2f}-{close_price * 1.06:.2f}",
        "holding_period": "2-4天",
        "emotion_notes": "相对平静，但对轮动持续性把握一般。",
        "mistake_tags": [],
        "lessons_if_loss": "轮动逻辑一旦弱化，要更早承认预期差。",
        "lessons_if_win": "震荡里的平台整理更适合按节奏滚动处理。",
    }


def _review_feedback(review: dict[str, Any]) -> tuple[str, str]:
    review_type = str(review.get("review_type") or "")
    max_gain = _float(review.get("max_gain_pct"))
    max_drawdown = _float(review.get("max_drawdown_pct"))
    if review_type == "sell_fly":
        if max_gain >= 10:
            return "是，卖得偏早，后面空间比预期大。", "降低该卖出理由权重"
        return "有卖早成分，但当时纪律并不算失真。", "轻微下调该卖点权重"
    if review_type == "good_exit":
        if max_drawdown <= -5:
            return "是，这次离场对回撤保护有效。", "保留该卖点权重"
        return "这次离场基本合格，纪律优先。", "保留该卖点权重"
    return "走势平淡，这次回顾更多用于保留样本。", "保持观察"


def _pick_entry_slots(trade_days: list[str], max_trades: int) -> list[str]:
    return trade_days[5: 5 + max_trades * 4: 4]


def _bars_by_code(app: Any, codes: list[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    bars: dict[str, list[dict[str, Any]]] = {}
    fetch_start = shift_calendar_date(start_date, -10)
    for code in codes:
        rows = app.market.get_daily_bars(code, start_date=fetch_start, end_date=end_date)
        rows.sort(key=lambda item: str(item.get("trade_date") or ""))
        bars[code] = rows
    return bars


def _classify_candidate(profile: dict[str, Any], actual_return: float) -> str:
    logic = profile["logic_tags"][0]
    pattern = profile["pattern_tags"][0]
    if logic == "低吸" and pattern in {"均线回踩", "平台整理"} and actual_return >= 4.0:
        return "positive"
    if logic == "半路追涨" and actual_return <= -3.0:
        return "negative"
    if actual_return <= -6.0:
        return "negative"
    if actual_return >= 6.0:
        return "positive"
    return "neutral"


def _build_trade_candidates(
    trade_days: list[str],
    code_bars: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    day_index = {day: idx for idx, day in enumerate(trade_days)}
    candidates: list[dict[str, Any]] = []
    for code_index, meta in enumerate(SHOWCASE_UNIVERSE):
        rows = code_bars.get(meta["ts_code"], [])
        for entry_idx in range(5, len(rows) - 5):
            entry_day = rows[entry_idx]["trade_date"]
            if entry_day not in day_index:
                continue
            hold_days = 2 + ((entry_idx + code_index) % 4)
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(rows):
                continue
            exit_day = rows[exit_idx]["trade_date"]
            if exit_day not in day_index:
                continue
            buy_price = _float(rows[entry_idx].get("close"))
            sell_price = _float(rows[exit_idx].get("close"))
            if not buy_price or not sell_price:
                continue
            actual_return = round((sell_price / buy_price - 1) * 100, 2)
            profile = _trade_profile(rows, entry_idx, meta["theme"])
            candidate = {
                "meta": meta,
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
                "entry_day": entry_day,
                "exit_day": exit_day,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "actual_return": actual_return,
                "profile": profile,
                "score_class": _classify_candidate(profile, actual_return),
                "trade_day_index": day_index[entry_day],
            }
            candidates.append(candidate)
    return candidates


def _select_showcase_candidates(candidates: list[dict[str, Any]], max_trades: int) -> list[dict[str, Any]]:
    positive = sorted(
        [item for item in candidates if item["score_class"] == "positive"],
        key=lambda item: (item["actual_return"], -item["trade_day_index"]),
        reverse=True,
    )
    negative = sorted(
        [item for item in candidates if item["score_class"] == "negative"],
        key=lambda item: (item["actual_return"], item["trade_day_index"]),
    )
    neutral = sorted(
        [item for item in candidates if item["score_class"] == "neutral"],
        key=lambda item: (abs(item["actual_return"]), -item["trade_day_index"]),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    selected_slots: list[int] = []
    selected_codes: dict[str, int] = {}

    def can_pick(item: dict[str, Any]) -> bool:
        slot = int(item["trade_day_index"])
        code = item["meta"]["ts_code"]
        if selected_codes.get(code, 0) >= 2:
            return False
        return all(abs(slot - existing) >= 3 for existing in selected_slots)

    def add_from(pool: list[dict[str, Any]], target: int) -> None:
        for item in pool:
            if len(selected) >= max_trades or target <= 0:
                break
            if not can_pick(item):
                continue
            selected.append(item)
            selected_slots.append(int(item["trade_day_index"]))
            selected_codes[item["meta"]["ts_code"]] = selected_codes.get(item["meta"]["ts_code"], 0) + 1
            target -= 1

    positive_target = min(max(4, max_trades // 2), len(positive))
    negative_target = min(max(3, max_trades // 3), len(negative))
    add_from(positive, positive_target)
    add_from(negative, negative_target)
    add_from(neutral, max_trades - len(selected))
    remaining = sorted(candidates, key=lambda item: (abs(item["actual_return"]), item["trade_day_index"]), reverse=True)
    add_from(remaining, max_trades - len(selected))
    selected.sort(key=lambda item: item["entry_day"])
    return selected[:max_trades]


def _bar_index(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {str(item.get("trade_date") or ""): index for index, item in enumerate(rows)}


def _ensure_market(app: Any, start_date: str, end_date: str) -> list[str]:
    if not app.market:
        raise RuntimeError("market data is disabled; showcase generation requires Tushare.")
    days = app.market.trade_days_between(start_date, end_date)
    if not days:
        raise RuntimeError(f"no trade days found between {start_date} and {end_date}")
    return days


def _decision_context(meta: dict[str, Any], profile: dict[str, Any], stage: str) -> dict[str, Any]:
    focus = [meta["theme"], profile["pattern_tags"][0]]
    signals: list[str]
    if profile["logic_tags"][0] == "半路追涨":
        signals = ["板块临盘加速", "个股放量突破"]
        position_reason = "展示模拟：强势场景下用中等偏轻仓位试错，避免把展示样本写成无脑重仓。"
        confidence = 6
        stress = 6
    elif profile["pattern_tags"][0] == "均线回踩":
        signals = ["分歧回踩到均线附近", "板块出现修复回流迹象"]
        position_reason = "展示模拟：按低吸预案分批参与，仓位比追涨样本更稳一些。"
        confidence = 7
        stress = 4
    else:
        signals = ["平台整理后波动收敛", "轮动修复但持续性仍需观察"]
        position_reason = "展示模拟：先放轻仓观察，不把震荡里的试错写成高确定性重仓。"
        confidence = 5
        stress = 3
    return {
        "capture_mode": "showcase_demo",
        "stage": stage,
        "user_focus": focus,
        "observed_signals": signals,
        "interpretation": profile["thesis"],
        "position_reason": position_reason,
        "position_confidence": confidence,
        "stress_level": stress,
    }


def _create_historical_showcase(app: Any, start_date: str, end_date: str, max_trades: int) -> dict[str, Any]:
    trade_days = _ensure_market(app, start_date, end_date)
    code_bars = _bars_by_code(app, [item["ts_code"] for item in SHOWCASE_UNIVERSE], start_date, end_date)
    candidates = _build_trade_candidates(trade_days, code_bars)
    selected = _select_showcase_candidates(candidates, max_trades)

    created_plans: list[dict[str, Any]] = []
    created_trades: list[dict[str, Any]] = []

    for index, candidate in enumerate(selected):
        meta = candidate["meta"]
        rows = code_bars.get(meta["ts_code"], [])
        entry_idx = int(candidate["entry_idx"])
        entry_bar = rows[entry_idx]
        profile = dict(candidate["profile"])
        plan_date = rows[entry_idx - 1]["trade_date"]
        entry_day = candidate["entry_day"]
        exit_date = candidate["exit_day"]
        buy_price = float(candidate["buy_price"])
        sell_price = float(candidate["sell_price"])
        actual_return = float(candidate["actual_return"])

        if actual_return > 0:
            profile["mistake_tags"] = []
        if actual_return >= 4 and profile["logic_tags"][0] == "低吸":
            profile["emotion_notes"] = "整体按计划执行，盘中更多是在确认修复节奏。"
        if actual_return <= -4 and profile["logic_tags"][0] == "低吸":
            profile["mistake_tags"] = ["拿不稳"]
        if actual_return <= -3 and profile["logic_tags"][0] == "半路追涨":
            profile["mistake_tags"] = ["冲动追高"]
        decision_context = _decision_context(meta, profile, stage="historical_showcase")

        plan = app.create_plan(
            ts_code=meta["ts_code"],
            name=app.market.resolve_stock(meta["ts_code"]).get("name"),
            direction="buy",
            thesis=profile["thesis"],
            logic_tags=profile["logic_tags"],
            market_stage=profile["market_stage"],
            environment_tags=profile["environment_tags"],
            buy_zone=profile["buy_zone"],
            sell_zone=profile["sell_zone"],
            stop_loss=f"{buy_price * 0.95:.2f}",
            holding_period=profile["holding_period"],
            valid_from=plan_date,
            valid_to=entry_day,
            decision_context=decision_context,
            notes=f"展示用模拟计划，价格与日期来自真实行情，逻辑描述为演示文案。主题：{meta['theme']}",
            with_reference=(index % 4 == 0),
            lookback_days=90,
        )
        created_plans.append(plan["plan"])

        trade = app.log_trade(
            ts_code=meta["ts_code"],
            name=plan["plan"]["name"],
            plan_id=plan["plan"]["plan_id"],
            buy_date=entry_day,
            buy_price=buy_price,
            sell_date=exit_date,
            sell_price=sell_price,
            thesis=profile["thesis"],
            buy_reason=f"展示模拟：围绕 {meta['theme']} 的 {profile['logic_tags'][0]} 交易。",
            sell_reason="达到预设止盈" if actual_return > 2 else "走势不及预期，先收缩风险",
            position_size_pct=25 + (index % 3) * 10,
            logic_type_tags=profile["logic_tags"],
            pattern_tags=profile["pattern_tags"],
            market_stage_tag=profile["market_stage"],
            environment_tags=profile["environment_tags"],
            emotion_notes=profile["emotion_notes"],
            mistake_tags=profile["mistake_tags"] if actual_return <= 0 else (["拿不稳"] if actual_return < 3 else []),
            lessons_learned=profile["lessons_if_win"] if actual_return > 0 else profile["lessons_if_loss"],
            decision_context=decision_context,
            notes=f"展示用模拟交易：买卖日期和价格来自真实行情，交易理由和反思为演示文本。实际收益 {actual_return:.2f}%。",
        )
        created_trades.append(trade)

        if index % 3 == 0:
            app.enrich_plan_from_text(
                plan["plan"]["plan_id"],
                f"补充：这笔展示样本主要用于演示 {meta['theme']} 在 {profile['market_stage']} 下的 {profile['pattern_tags'][0]} 场景。",
                trade_date=entry_day,
                lookback_days=90,
            )
        if index % 2 == 0:
            app.enrich_trade_from_text(
                trade["trade_id"],
                "补充：这笔记录刻意保留了情绪、失误和经验字段，方便展示后续自进化与体检报告如何沉淀。",
                trade_date=exit_date,
                lookback_days=90,
            )

    return {"plans": created_plans, "trades": created_trades, "trade_days": trade_days}


def _create_active_showcase_plans(app: Any, brief_date: str) -> list[dict[str, Any]]:
    chosen = SHOWCASE_UNIVERSE[:2]
    created: list[dict[str, Any]] = []
    for index, meta in enumerate(chosen):
        rows = app.market.get_daily_bars(meta["ts_code"], start_date=shift_calendar_date(brief_date, -12), end_date=shift_calendar_date(brief_date, -1))
        rows.sort(key=lambda item: str(item.get("trade_date") or ""))
        if not rows:
            continue
        ref_bar = rows[-1]
        close_price = _float(ref_bar.get("close"))
        profile = _trade_profile(rows, len(rows) - 1, meta["theme"])
        decision_context = _decision_context(meta, profile, stage="active_showcase")
        plan = app.create_plan(
            ts_code=meta["ts_code"],
            name=app.market.resolve_stock(meta["ts_code"]).get("name"),
            direction="buy",
            thesis=f"展示用待执行计划：{profile['thesis']}",
            logic_tags=profile["logic_tags"],
            market_stage=profile["market_stage"],
            environment_tags=profile["environment_tags"],
            buy_zone=f"{close_price * 0.99:.2f}-{close_price * 1.01:.2f}",
            sell_zone=f"{close_price * 1.04:.2f}-{close_price * 1.08:.2f}",
            stop_loss=f"{close_price * 0.95:.2f}",
            holding_period="2-4天",
            valid_from=brief_date,
            valid_to=shift_calendar_date(brief_date, 4 + index),
            decision_context=decision_context,
            notes="展示用途的当前有效计划，用于晨报和自进化提醒演示。",
            with_reference=True,
            lookback_days=90,
        )
        created.append(plan["plan"])
    return created


def _answer_reviews(app: Any) -> list[dict[str, Any]]:
    answered: list[dict[str, Any]] = []
    for review in app.list_reviews(status="pending", limit=200):
        feedback, weight_action = _review_feedback(review)
        answered.append(app.respond_review(review["review_id"], feedback=feedback, weight_action=weight_action))
    return answered


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Showcase Demo Summary",
        "",
        f"- 展示区间: {summary['period_start']} -> {summary['period_end']}",
        f"- 晨报日期: {summary['brief_date']}",
        f"- 展示计划数: {summary['counts']['plans']}",
        f"- 展示闭环交易数: {summary['counts']['closed_trades']}",
        f"- 有效待执行计划数: {summary['counts']['active_plans']}",
        f"- 回顾数: {summary['counts']['reviews']}",
        "",
        "## 关键产物",
        f"- 晨报: {summary['artifacts'].get('morning_brief_markdown') or '-'}",
        f"- 自进化报告: {summary['artifacts'].get('evolution_report_markdown') or '-'}",
        f"- 风格画像: {summary['artifacts'].get('style_portrait_markdown') or '-'}",
        f"- 体检报告: {summary['artifacts'].get('health_report_markdown') or '-'}",
        f"- Dashboard: {summary['artifacts'].get('dashboard_note') or '-'}",
        "",
        "## 说明",
        "- 这批展示数据的买卖日期、价格、收益与回顾窗口依赖真实行情数据。",
        "- 交易逻辑、情绪描述、买卖原因和经验总结为展示用途的模拟文案。",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    start_date = normalize_trade_date(args.start_date)
    end_date = normalize_trade_date(args.end_date)
    brief_date = normalize_trade_date(args.brief_date)

    app = create_app(Path(__file__).resolve(), runtime_root=str(root), enable_market_data=True)
    app.init_runtime()

    if not app.market:
        raise RuntimeError("Tushare market data is unavailable.")

    # Probe Tushare early so failures happen before we create partial demo data.
    app.market.get_trade_calendar(start_date, end_date, is_open=1)

    for item in SHOWCASE_UNIVERSE:
        app.add_watchlist(item["ts_code"], name=app.market.resolve_stock(item["ts_code"]).get("name"), source="showcase")
    for keyword in SHOWCASE_KEYWORDS:
        app.add_keyword(keyword, category="showcase")

    historical = _create_historical_showcase(app, start_date, end_date, max_trades=int(args.max_trades))
    active_plans = _create_active_showcase_plans(app, brief_date=brief_date)
    review_cycle = app.run_review_cycle(as_of_date=brief_date)
    answered_reviews = _answer_reviews(app)

    evolution = app.generate_evolution_report(
        lookback_days=int(args.lookback_days),
        trade_date=end_date,
        min_samples=2,
        write_artifact=True,
    )
    portrait = app.generate_style_portrait(
        lookback_days=int(args.lookback_days),
        trade_date=end_date,
        min_samples=2,
        write_artifact=True,
    )
    health_full = app.generate_health_report(start_date, end_date, period_kind="showcase")
    health_feb = app.generate_health_report("20260201", "20260228", period_kind="monthly")
    health_mar = app.generate_health_report("20260301", "20260331", period_kind="monthly")
    morning_brief = app.generate_morning_brief(trade_date=brief_date, fetch_events=True)
    sync_result = app.sync_vault(trade_date=brief_date, limit=500)
    dashboard_note = app.export_dashboard_note()

    summary = {
        "runtime_root": str(root),
        "period_start": start_date,
        "period_end": end_date,
        "brief_date": brief_date,
        "counts": {
            "plans": len(app.list_plans(status=None, active_only=False)),
            "closed_trades": len(app.list_trades(status="closed", limit=500)),
            "active_plans": len(app.list_plans(active_only=True, trade_date=brief_date)),
            "reviews": len(app.list_reviews(status=None, limit=500)),
            "answered_reviews": len(answered_reviews),
            "watchlist": len(app.list_watchlist()),
            "keywords": len(app.list_keywords()),
        },
        "outputs": {
            "historical_trade_ids": [item.get("trade_id") for item in historical["trades"]],
            "active_plan_ids": [item.get("plan_id") for item in active_plans],
            "review_cycle_created": len(review_cycle.get("created_reviews") or []),
            "morning_brief_fetch_errors": morning_brief.get("fetch_result", {}).get("errors", []),
        },
        "artifacts": {
            "morning_brief_markdown": morning_brief.get("artifact_paths", {}).get("markdown"),
            "evolution_report_markdown": evolution.get("artifact_paths", {}).get("markdown"),
            "style_portrait_markdown": portrait.get("artifact_paths", {}).get("markdown"),
            "health_report_markdown": health_full.get("artifact_paths", {}).get("markdown"),
            "health_feb_markdown": health_feb.get("artifact_paths", {}).get("markdown"),
            "health_mar_markdown": health_mar.get("artifact_paths", {}).get("markdown"),
            "dashboard_note": dashboard_note.get("path"),
            "vault_sync_count": len(sync_result.get("paths") or []),
        },
    }

    summary_path = root / "artifacts" / "daily" / brief_date / "showcase_demo_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = summary_path.with_suffix(".md")
    markdown_path.write_text(_summary_markdown(summary), encoding="utf-8")
    summary["artifacts"]["showcase_summary_json"] = str(summary_path)
    summary["artifacts"]["showcase_summary_markdown"] = str(markdown_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
