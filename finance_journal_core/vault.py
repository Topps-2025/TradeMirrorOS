from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import json_loads, safe_filename


VAULT_FOLDERS = {
    "dashboard": "00-dashboard",
    "plans": "01-plans",
    "trades": "02-trades",
    "reviews": "03-reviews",
    "reports": "04-reports",
    "daily": "05-daily",
}


def vault_dirs(vault_root: Path) -> dict[str, Path]:
    return {key: vault_root / value for key, value in VAULT_FOLDERS.items()}


def ensure_vault_dirs(vault_root: Path) -> dict[str, Path]:
    dirs = vault_dirs(vault_root)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def file_stem(prefix: str, *parts: str) -> str:
    compact = "_".join(part for part in parts if part)
    return safe_filename(f"{prefix}_{compact}" if compact else prefix)


def frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def format_tags(*tag_lists: Any) -> list[str]:
    tags: list[str] = []
    for value in tag_lists:
        if value is None:
            continue
        if isinstance(value, str):
            tags.append(value)
            continue
        if isinstance(value, (list, tuple, set)):
            tags.extend(str(item) for item in value if str(item).strip())
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        cleaned = str(tag).strip().replace(" ", "-")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def render_decision_context(context: dict[str, Any] | None) -> list[str]:
    payload = dict(context or {})
    if not payload:
        return ["- 暂无补充。"]
    focus = payload.get("user_focus") or []
    signals = payload.get("observed_signals") or []
    env_tags = payload.get("environment_tags") or []
    planned_zone = payload.get("planned_zone") if isinstance(payload.get("planned_zone"), dict) else {}
    strategy_context = payload.get("strategy_context") if isinstance(payload.get("strategy_context"), dict) else {}
    lines = [
        f"- 关注切片: {', '.join(str(item) for item in focus) if focus else '-'}",
        f"- 触发信号: {'；'.join(str(item) for item in signals) if signals else '-'}",
        f"- 当时解读: {payload.get('interpretation') or '-'}",
        f"- 市场阶段: {payload.get('market_stage') or '-'}",
        f"- 环境标签: {', '.join(str(item) for item in env_tags) if env_tags else '-'}",
        f"- 仓位理由: {payload.get('position_reason') or '-'}",
        f"- 仓位比例: {payload.get('position_size_pct') if payload.get('position_size_pct') not in (None, '') else '-'}",
        f"- 计划区间: 买={planned_zone.get('buy_zone') or '-'} / 卖={planned_zone.get('sell_zone') or '-'}",
        f"- 风险边界: {payload.get('risk_boundary') or '-'}",
        f"- 主观把握: {payload.get('position_confidence') if payload.get('position_confidence') not in (None, '') else '-'}",
        f"- 紧张程度: {payload.get('stress_level') if payload.get('stress_level') not in (None, '') else '-'}",
        f"- 情绪备注: {payload.get('emotion_notes') or '-'}",
        f"- 失误标签: {', '.join(str(item) for item in payload.get('mistake_tags') or []) or '-'}",
    ]
    if strategy_context:
        factor_list = strategy_context.get("factor_list") or []
        lines.extend(
            [
                f"- 策略条线: {strategy_context.get('strategy_line') or strategy_context.get('strategy_name') or strategy_context.get('strategy_id') or '-'}",
                f"- 策略家族: {strategy_context.get('strategy_family') or '-'}",
                f"- 核心因子: {', '.join(str(item) for item in factor_list) if factor_list else '-'}",
                f"- 因子选择理由: {strategy_context.get('factor_selection_reason') or '-'}",
                f"- 启用原因: {strategy_context.get('activation_reason') or '-'}",
                f"- 参数版本: {strategy_context.get('parameter_version') or '-'}",
                f"- 组合角色: {strategy_context.get('portfolio_role') or '-'}",
                f"- 主观覆盖: {strategy_context.get('subjective_override') or '-'}",
            ]
        )
    return lines


def render_plan_note(plan: dict[str, Any]) -> str:
    tags = format_tags(
        "trade-plan",
        json_loads(plan.get("logic_tags_json"), []),
        json_loads(plan.get("environment_tags_json"), []),
    )
    header = frontmatter(
        {
            "note_type": "trade_plan",
            "plan_id": plan.get("plan_id") or "",
            "ts_code": plan.get("ts_code") or "",
            "name": plan.get("name") or "",
            "status": plan.get("status") or "",
            "valid_from": plan.get("valid_from") or "",
            "valid_to": plan.get("valid_to") or "",
            "tags": tags,
        }
    )
    lines = [
        header,
        "",
        f"# 交易计划 | {plan.get('name') or plan.get('ts_code')}",
        "",
        "## 基本信息",
        f"- 标的: {plan.get('name') or '-'} ({plan.get('ts_code') or '-'})",
        f"- 方向: {plan.get('direction') or '-'}",
        f"- 状态: {plan.get('status') or '-'}",
        f"- 有效期: {plan.get('valid_from') or '-'} -> {plan.get('valid_to') or '-'}",
        f"- 提醒时间: {plan.get('reminder_time') or '-'}",
        "",
        "## 计划内容",
        f"- 核心逻辑: {plan.get('thesis') or '-'}",
        f"- 逻辑标签: {', '.join(json_loads(plan.get('logic_tags_json'), [])) or '-'}",
        f"- 环境标签: {', '.join(json_loads(plan.get('environment_tags_json'), [])) or '-'}",
        f"- 买入区间: {plan.get('buy_zone') or '-'}",
        f"- 卖出区间: {plan.get('sell_zone') or '-'}",
        f"- 止损条件: {plan.get('stop_loss') or '-'}",
        f"- 计划持仓周期: {plan.get('holding_period') or '-'}",
        "",
        "## 用户视角快照",
        *render_decision_context(json_loads(plan.get("decision_context_json"), {})),
        "",
        "## 纪律检查",
        "- 开仓前：这笔交易是否来自盘前计划？",
        "- 开仓时：实际买点是否偏离计划区间？",
        "- 卖出时：是按规则卖出，还是情绪卖出？",
        "",
        "## 备注",
        plan.get("notes") or "-",
        "",
    ]
    return "\n".join(lines)


def render_trade_note(trade: dict[str, Any], plan: dict[str, Any] | None = None, review_rows: list[dict[str, Any]] | None = None) -> str:
    logic_tags = json_loads(trade.get("logic_type_tags_json"), [])
    pattern_tags = json_loads(trade.get("pattern_tags_json"), [])
    env_tags = json_loads(trade.get("environment_tags_json"), [])
    mistake_tags = json_loads(trade.get("mistake_tags_json"), [])
    tags = format_tags("trade-journal", logic_tags, pattern_tags, env_tags, mistake_tags)
    header = frontmatter(
        {
            "note_type": "trade",
            "trade_id": trade.get("trade_id") or "",
            "ts_code": trade.get("ts_code") or "",
            "name": trade.get("name") or "",
            "status": trade.get("status") or "",
            "buy_date": trade.get("buy_date") or "",
            "sell_date": trade.get("sell_date") or "",
            "tags": tags,
        }
    )
    lines = [
        header,
        "",
        f"# 交易复盘 | {trade.get('name') or trade.get('ts_code')}",
        "",
        "## 事实记录",
        f"- 标的: {trade.get('name') or '-'} ({trade.get('ts_code') or '-'})",
        f"- 买入: {trade.get('buy_date') or '-'} @ {trade.get('buy_price') if trade.get('buy_price') is not None else '-'}",
        f"- 卖出: {trade.get('sell_date') or '-'} @ {trade.get('sell_price') if trade.get('sell_price') is not None else '-'}",
        f"- 持仓天数: {trade.get('holding_days') if trade.get('holding_days') is not None else '-'}",
        f"- 实际收益: {trade.get('actual_return_pct') if trade.get('actual_return_pct') is not None else '-'}%",
        f"- 选股基准收益: {trade.get('benchmark_return_pct') if trade.get('benchmark_return_pct') is not None else '-'}%",
        f"- 操作绩效差值: {trade.get('timing_alpha_pct') if trade.get('timing_alpha_pct') is not None else '-'}%",
        "",
        "## 计划对照",
        f"- 关联计划: {plan.get('plan_id') if plan else '-'}",
        f"- 计划逻辑: {plan.get('thesis') if plan else '-'}",
        f"- 买入偏离: {trade.get('plan_execution_deviation_json') or '-'}",
        "",
        "## 交易理由",
        f"- 买入理由: {trade.get('buy_reason') or trade.get('thesis') or '-'}",
        f"- 卖出理由: {trade.get('sell_reason') or '-'}",
        f"- 买入技术位置: {trade.get('buy_position') or '-'}",
        f"- 卖出技术位置: {trade.get('sell_position') or '-'}",
        f"- 逻辑标签: {', '.join(logic_tags) or '-'}",
        f"- 形态标签: {', '.join(pattern_tags) or '-'}",
        f"- 环境标签: {', '.join(env_tags) or '-'}",
        "",
        "## 用户视角快照",
        *render_decision_context(json_loads(trade.get("decision_context_json"), {})),
        "",
        "## 行为复盘",
        f"- 情绪备注: {trade.get('emotion_notes') or '-'}",
        f"- 失误标签: {', '.join(mistake_tags) or '-'}",
        f"- 经验沉淀: {trade.get('lessons_learned') or '-'}",
        f"- 其他备注: {trade.get('notes') or '-'}",
    ]
    if review_rows:
        lines.extend(["", "## 卖出后回顾"])
        for review in review_rows:
            lines.append(
                f"- {review.get('review_due_date') or '-'} | {review.get('review_type') or '-'} | "
                f"max_gain={review.get('max_gain_pct') if review.get('max_gain_pct') is not None else '-'}% | "
                f"max_drawdown={review.get('max_drawdown_pct') if review.get('max_drawdown_pct') is not None else '-'}% | "
                f"反馈={review.get('feedback') or '-'}"
            )
    lines.extend(
        [
            "",
            "## 手工补充",
            "- 这笔交易最值得重复的地方：",
            "- 这笔交易最需要纠正的地方：",
            "- 如果重来一次，我会怎么做：",
            "",
        ]
    )
    return "\n".join(lines)


def render_review_note(review: dict[str, Any], trade: dict[str, Any] | None = None) -> str:
    header = frontmatter(
        {
            "note_type": "post_exit_review",
            "review_id": review.get("review_id") or "",
            "trade_id": review.get("trade_id") or "",
            "ts_code": review.get("ts_code") or "",
            "status": review.get("status") or "",
            "tags": ["sell-review", review.get("review_type") or "review"],
        }
    )
    lines = [
        header,
        "",
        f"# 卖出回顾 | {review.get('name') or review.get('ts_code')}",
        "",
        "## 回顾摘要",
        f"- 卖出日: {review.get('sell_date') or '-'}",
        f"- 回顾到期日: {review.get('review_due_date') or '-'}",
        f"- 回顾类型: {review.get('review_type') or '-'}",
        f"- 卖出价: {review.get('sell_price') if review.get('sell_price') is not None else '-'}",
        f"- 窗口最高价: {review.get('highest_price') if review.get('highest_price') is not None else '-'}",
        f"- 窗口最低价: {review.get('lowest_price') if review.get('lowest_price') is not None else '-'}",
        f"- 最大后续涨幅: {review.get('max_gain_pct') if review.get('max_gain_pct') is not None else '-'}%",
        f"- 最大后续回撤: {review.get('max_drawdown_pct') if review.get('max_drawdown_pct') is not None else '-'}%",
        "",
        "## 当时卖出理由",
        f"- {trade.get('sell_reason') if trade else '-'}",
        "",
        "## 系统提问",
        review.get("prompt_text") or "-",
        "",
        "## 用户反馈",
        f"- 反馈: {review.get('feedback') or '-'}",
        f"- 权重动作: {review.get('weight_action') or '-'}",
        "",
        "## 手工补充",
        "- 这次卖出是纪律正确，还是处理过早？",
        "- 未来遇到同类图形时，我应该保留哪些判断条件？",
        "",
    ]
    return "\n".join(lines)


def render_health_report_note(report: dict[str, Any]) -> str:
    metrics = report.get("metrics") or {}
    header = frontmatter(
        {
            "note_type": "behavior_health_report",
            "report_id": report.get("report_id") or "",
            "period_kind": report.get("period_kind") or "",
            "period_start": report.get("period_start") or "",
            "period_end": report.get("period_end") or "",
            "tags": ["behavior-health", report.get("period_kind") or "report"],
        }
    )
    lines = [
        header,
        "",
        f"# 行为体检 | {report.get('period_start') or '-'} -> {report.get('period_end') or '-'}",
        "",
        f"- 闭环交易数: {report.get('trade_count') or 0}",
        f"- 有效计划数: {report.get('plan_count') or 0}",
        f"- 计划执行率: {metrics.get('plan_execution_rate_pct') if metrics.get('plan_execution_rate_pct') is not None else '-'}%",
        f"- 计划外交易占比: {metrics.get('off_plan_trade_ratio_pct') if metrics.get('off_plan_trade_ratio_pct') is not None else '-'}%",
        f"- 持仓周期偏离: {metrics.get('holding_bias_pct') if metrics.get('holding_bias_pct') is not None else '-'}%",
        f"- 止损执行率: {metrics.get('stop_loss_execution_rate_pct') if metrics.get('stop_loss_execution_rate_pct') is not None else '-'}%",
        "",
        "## 报告正文",
        report.get("markdown") or "-",
        "",
    ]
    return "\n".join(lines)


def render_daily_note(
    trade_date: str,
    plans: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> str:
    header = frontmatter(
        {
            "note_type": "daily_journal",
            "trade_date": trade_date,
            "tags": ["daily-journal", trade_date],
        }
    )
    lines = [
        header,
        "",
        f"# 每日交易复盘 | {trade_date}",
        "",
        "## 今日计划",
    ]
    if plans:
        for plan in plans:
            lines.append(
                f"- {plan.get('name') or plan.get('ts_code')}: {plan.get('thesis') or '-'} | 状态={plan.get('status') or '-'} | 有效期至 {plan.get('valid_to') or '-'}"
            )
    else:
        lines.append("- 今日无计划记录。")

    lines.extend(["", "## 今日交易"])
    if trades:
        for trade in trades:
            lines.append(
                f"- {trade.get('name') or trade.get('ts_code')}: 买 {trade.get('buy_price') if trade.get('buy_price') is not None else '-'} / "
                f"卖 {trade.get('sell_price') if trade.get('sell_price') is not None else '-'} / "
                f"收益 {trade.get('actual_return_pct') if trade.get('actual_return_pct') is not None else '-'}%"
            )
    else:
        lines.append("- 今日无交易记录。")

    lines.extend(["", "## 卖出回顾"])
    if reviews:
        for review in reviews:
            lines.append(
                f"- {review.get('name') or review.get('ts_code')}: {review.get('review_type') or '-'} | 反馈={review.get('feedback') or '-'}"
            )
    else:
        lines.append("- 今日无回顾记录。")

    lines.extend(["", "## 可选事件参考"])
    if events:
        for event in events[:10]:
            lines.append(f"- {event.get('headline') or '-'}")
    else:
        lines.append("- 今日未记录事件，或事件模块未启用。")

    lines.extend(
        [
            "",
            "## 手工复盘",
            "- 今天做对了什么：",
            "- 今天最大的计划偏离：",
            "- 今天最典型的情绪反应：",
            "- 明天必须执行的一条纪律：",
            "",
        ]
    )
    return "\n".join(lines)


def render_dashboard_note(recent_trades: list[dict[str, Any]], recent_reports: list[dict[str, Any]]) -> str:
    header = frontmatter({"note_type": "dashboard", "tags": ["dashboard", "trade-journal"]})
    lines = [
        header,
        "",
        "# 交易复盘总览",
        "",
        "## 最近交易",
    ]
    if recent_trades:
        for trade in recent_trades[:20]:
            lines.append(
                f"- {trade.get('buy_date') or '-'} | {trade.get('name') or trade.get('ts_code')} | "
                f"收益 {trade.get('actual_return_pct') if trade.get('actual_return_pct') is not None else '-'}% | "
                f"状态 {trade.get('status') or '-'}"
            )
    else:
        lines.append("- 暂无交易记录。")

    lines.extend(["", "## 最近体检"])
    if recent_reports:
        for report in recent_reports[:12]:
            lines.append(
                f"- {report.get('period_start') or '-'} -> {report.get('period_end') or '-'} | {report.get('period_kind') or '-'}"
            )
    else:
        lines.append("- 暂无体检报告。")
    lines.append("")
    return "\n".join(lines)
