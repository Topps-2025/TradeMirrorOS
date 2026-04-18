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
    "memory": "06-memory",
    "skills": "07-skills",
    "graph": "08-graph",
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
        return ["- None yet."]
    strategy_context = payload.get("strategy_context") if isinstance(payload.get("strategy_context"), dict) else {}
    planned_zone = payload.get("planned_zone") if isinstance(payload.get("planned_zone"), dict) else {}
    objective_review = payload.get("objective_review") if isinstance(payload.get("objective_review"), dict) else {}
    lines = [
        f"- User focus: {', '.join(str(item) for item in payload.get('user_focus') or []) or '-'}",
        f"- Observed signals: {', '.join(str(item) for item in payload.get('observed_signals') or []) or '-'}",
        f"- Interpretation: {payload.get('interpretation') or '-'}",
        f"- Position reason: {payload.get('position_reason') or '-'}",
        f"- Position confidence: {payload.get('position_confidence') if payload.get('position_confidence') not in (None, '') else '-'}",
        f"- Market stage: {payload.get('market_stage') or '-'}",
        f"- Environment tags: {', '.join(str(item) for item in payload.get('environment_tags') or []) or '-'}",
        f"- Planned zone: buy {planned_zone.get('buy_zone') or '-'} / sell {planned_zone.get('sell_zone') or '-'}",
        f"- Risk boundary: {payload.get('risk_boundary') or '-'}",
        f"- Emotion notes: {payload.get('emotion_notes') or '-'}",
        f"- Mistake tags: {', '.join(str(item) for item in payload.get('mistake_tags') or []) or '-'}",
    ]
    if objective_review:
        lines.extend(
            [
                f"- Objective narrative: {objective_review.get('narrative_summary') or '-'}",
                f"- Objective execution facts: {objective_review.get('execution_facts') or '-'}",
                f"- Objective performance: {objective_review.get('performance_summary') or '-'}",
                f"- Objective index snapshot: {objective_review.get('index_summary') or '-'}",
                f"- Objective breadth snapshot: {objective_review.get('breadth_summary') or '-'}",
                f"- Objective sector snapshot: {objective_review.get('sector_summary') or '-'}",
                f"- Objective market regime: {objective_review.get('market_regime_summary') or '-'}",
            ]
        )
    if strategy_context:
        lines.extend(
            [
                f"- Strategy line: {strategy_context.get('strategy_line') or strategy_context.get('strategy_name') or strategy_context.get('strategy_id') or '-'}",
                f"- Strategy family: {strategy_context.get('strategy_family') or '-'}",
                f"- Factor list: {', '.join(str(item) for item in strategy_context.get('factor_list') or []) or '-'}",
                f"- Activation reason: {strategy_context.get('activation_reason') or '-'}",
                f"- Parameter version: {strategy_context.get('parameter_version') or '-'}",
                f"- Subjective override: {strategy_context.get('subjective_override') or '-'}",
            ]
        )
    return lines


def trade_decision_context(trade: dict[str, Any]) -> dict[str, Any]:
    payload = json_loads(trade.get("decision_context_json"), {})
    return payload if isinstance(payload, dict) else {}


def render_trade_reason_summary(trade: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    payload = context if context is not None else trade_decision_context(trade)
    parts: list[str] = []
    if trade.get("buy_reason"):
        parts.append(f"buy={trade['buy_reason']}")
    if trade.get("sell_reason"):
        parts.append(f"sell={trade['sell_reason']}")
    if payload.get("position_reason"):
        parts.append(f"position={payload['position_reason']}")
    return " | ".join(parts) or "-"


def render_trade_behavior_summary(trade: dict[str, Any]) -> str:
    parts: list[str] = []
    if trade.get("emotion_notes"):
        parts.append(f"emotion={trade['emotion_notes']}")
    mistake_tags = json_loads(trade.get("mistake_tags_json"), [])
    if mistake_tags:
        parts.append(f"mistakes={', '.join(str(item) for item in mistake_tags)}")
    if trade.get("lessons_learned"):
        parts.append(f"lesson={trade['lessons_learned']}")
    return " | ".join(parts) or "-"


def render_plan_note(plan: dict[str, Any]) -> str:
    tags = format_tags("trade-plan", json_loads(plan.get("logic_tags_json"), []), json_loads(plan.get("environment_tags_json"), []))
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
        f"# Plan | {plan.get('name') or plan.get('ts_code')}",
        "",
        "## Core",
        f"- Symbol: {plan.get('name') or '-'} ({plan.get('ts_code') or '-'})",
        f"- Direction: {plan.get('direction') or '-'}",
        f"- Status: {plan.get('status') or '-'}",
        f"- Thesis: {plan.get('thesis') or '-'}",
        f"- Logic tags: {', '.join(json_loads(plan.get('logic_tags_json'), [])) or '-'}",
        f"- Market stage: {plan.get('market_stage_tag') or '-'}",
        f"- Environment tags: {', '.join(json_loads(plan.get('environment_tags_json'), [])) or '-'}",
        f"- Buy zone: {plan.get('buy_zone') or '-'}",
        f"- Sell zone: {plan.get('sell_zone') or '-'}",
        f"- Stop loss: {plan.get('stop_loss') or '-'}",
        "",
        "## Decision Context",
        *render_decision_context(json_loads(plan.get("decision_context_json"), {})),
        "",
        "## Notes",
        plan.get("notes") or "-",
        "",
    ]
    return "\n".join(lines)


def render_trade_note(trade: dict[str, Any], plan: dict[str, Any] | None = None, review_rows: list[dict[str, Any]] | None = None) -> str:
    logic_tags = json_loads(trade.get("logic_type_tags_json"), [])
    pattern_tags = json_loads(trade.get("pattern_tags_json"), [])
    env_tags = json_loads(trade.get("environment_tags_json"), [])
    mistake_tags = json_loads(trade.get("mistake_tags_json"), [])
    decision_context = trade_decision_context(trade)
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
        f"# Trade | {trade.get('name') or trade.get('ts_code')}",
        "",
        "## Facts",
        f"- Buy: {trade.get('buy_date') or '-'} @ {trade.get('buy_price') if trade.get('buy_price') is not None else '-'}",
        f"- Sell: {trade.get('sell_date') or '-'} @ {trade.get('sell_price') if trade.get('sell_price') is not None else '-'}",
        f"- Status: {trade.get('status') or '-'}",
        f"- Actual return: {trade.get('actual_return_pct') if trade.get('actual_return_pct') is not None else '-'}%",
        f"- Timing alpha: {trade.get('timing_alpha_pct') if trade.get('timing_alpha_pct') is not None else '-'}%",
        f"- Holding days: {trade.get('holding_days') if trade.get('holding_days') is not None else '-'}",
        "",
        "## Setup",
        f"- Thesis: {trade.get('thesis') or '-'}",
        f"- Buy reason: {trade.get('buy_reason') or '-'}",
        f"- Sell reason: {trade.get('sell_reason') or '-'}",
        f"- Buy position: {trade.get('buy_position') or '-'}",
        f"- Sell position: {trade.get('sell_position') or '-'}",
        f"- Logic tags: {', '.join(logic_tags) or '-'}",
        f"- Pattern tags: {', '.join(pattern_tags) or '-'}",
        f"- Market stage: {trade.get('market_stage_tag') or '-'}",
        f"- Environment tags: {', '.join(env_tags) or '-'}",
        f"- Linked plan: {plan.get('plan_id') if plan else '-'}",
        "",
        "## Decision Context",
        *render_decision_context(decision_context),
        "",
        "## Reflection",
        f"- Emotion notes: {trade.get('emotion_notes') or '-'}",
        f"- Mistake tags: {', '.join(mistake_tags) or '-'}",
        f"- Lessons learned: {trade.get('lessons_learned') or '-'}",
        f"- Notes: {trade.get('notes') or '-'}",
    ]
    if review_rows:
        lines.extend(["", "## Post-exit Reviews"])
        for review in review_rows:
            lines.append(
                f"- {review.get('review_due_date') or '-'} | {review.get('review_type') or '-'} | "
                f"feedback={review.get('feedback') or '-'}"
            )
    lines.extend(["", "## Manual Follow-up", "- Best reusable part:", "- Most dangerous repeat error:", "- What to do differently next time:", ""])
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
        f"# Review | {review.get('name') or review.get('ts_code')}",
        "",
        "## Snapshot",
        f"- Sell date: {review.get('sell_date') or '-'}",
        f"- Review due: {review.get('review_due_date') or '-'}",
        f"- Review type: {review.get('review_type') or '-'}",
        f"- Max gain after exit: {review.get('max_gain_pct') if review.get('max_gain_pct') is not None else '-'}%",
        f"- Max drawdown after exit: {review.get('max_drawdown_pct') if review.get('max_drawdown_pct') is not None else '-'}%",
        "",
        "## Context",
        f"- Original sell reason: {trade.get('sell_reason') if trade else '-'}",
        f"- System prompt: {review.get('prompt_text') or '-'}",
        f"- Feedback: {review.get('feedback') or '-'}",
        f"- Weight action: {review.get('weight_action') or '-'}",
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
        f"# Health Report | {report.get('period_start') or '-'} -> {report.get('period_end') or '-'}",
        "",
        f"- Closed trades: {report.get('trade_count') or 0}",
        f"- Plans: {report.get('plan_count') or 0}",
        f"- Plan execution rate: {metrics.get('plan_execution_rate_pct') if metrics.get('plan_execution_rate_pct') is not None else '-'}%",
        f"- Off-plan ratio: {metrics.get('off_plan_trade_ratio_pct') if metrics.get('off_plan_trade_ratio_pct') is not None else '-'}%",
        "",
        "## Body",
        report.get("markdown") or "-",
        "",
    ]
    return "\n".join(lines)


def render_memory_note(memory_row: dict[str, Any]) -> str:
    tags = format_tags("trade-memory", *json_loads(memory_row.get("tags_json"), []))
    header = frontmatter(
        {
            "note_type": "memory_cell",
            "memory_id": memory_row.get("memory_id") or "",
            "memory_kind": memory_row.get("memory_kind") or "",
            "source_entity_kind": memory_row.get("source_entity_kind") or "",
            "source_entity_id": memory_row.get("source_entity_id") or "",
            "ts_code": memory_row.get("ts_code") or "",
            "trade_date": memory_row.get("trade_date") or "",
            "tags": tags,
        }
    )
    summary = json_loads(memory_row.get("summary_json"), {}) or {}
    quality = json_loads(memory_row.get("quality_json"), {}) or {}
    lines = [
        header,
        "",
        f"# Memory Cell | {memory_row.get('title') or memory_row.get('memory_id')}",
        "",
        "## Summary",
        f"- Trade date: {memory_row.get('trade_date') or '-'}",
        f"- Symbol: {memory_row.get('ts_code') or '-'}",
        f"- Strategy line: {memory_row.get('strategy_line') or '-'}",
        f"- Market stage: {memory_row.get('market_stage') or '-'}",
        f"- Summary json: {summary}",
        f"- Quality json: {quality}",
        "",
        "## Text",
        memory_row.get("text_body") or "-",
        "",
    ]
    return "\n".join(lines)


def render_skill_note(skill_row: dict[str, Any]) -> str:
    tags = format_tags("memory-skill", *json_loads(skill_row.get("trigger_conditions_json"), []))
    header = frontmatter(
        {
            "note_type": "memory_skill_card",
            "skill_id": skill_row.get("skill_id") or "",
            "source_kind": skill_row.get("source_kind") or "",
            "source_id": skill_row.get("source_id") or "",
            "sample_size": skill_row.get("sample_size") or 0,
            "community_shareable": bool(skill_row.get("community_shareable")),
            "tags": tags,
        }
    )
    lines = [
        header,
        "",
        f"# Skill Card | {skill_row.get('title') or skill_row.get('skill_id')}",
        "",
        f"- Intent: {skill_row.get('intent') or '-'}",
        f"- Trigger conditions: {', '.join(json_loads(skill_row.get('trigger_conditions_json'), [])) or '-'}",
        f"- Do not use when: {', '.join(json_loads(skill_row.get('do_not_use_when_json'), [])) or '-'}",
        f"- Evidence trades: {', '.join(json_loads(skill_row.get('evidence_trade_ids_json'), [])) or '-'}",
        "",
        skill_row.get("summary_markdown") or "-",
        "",
    ]
    return "\n".join(lines)


def render_daily_note(
    trade_date: str,
    plans: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    memory_cells: list[dict[str, Any]],
    skill_cards: list[dict[str, Any]],
) -> str:
    header = frontmatter(
        {
            "note_type": "daily_journal",
            "trade_date": trade_date,
            "tags": ["daily-journal", trade_date],
        }
    )
    lines = [header, "", f"# Daily Journal | {trade_date}", "", "## Plans"]
    if plans:
        for plan in plans:
            lines.append(f"- {plan.get('name') or plan.get('ts_code')}: {plan.get('thesis') or '-'}")
    else:
        lines.append("- No active plans.")

    lines.extend(["", "## Trades"])
    if trades:
        for trade in trades:
            decision_context = trade_decision_context(trade)
            lines.append(
                f"- {trade.get('name') or trade.get('ts_code')}: "
                f"buy {trade.get('buy_price') if trade.get('buy_price') is not None else '-'} / "
                f"sell {trade.get('sell_price') if trade.get('sell_price') is not None else '-'} / "
                f"return {trade.get('actual_return_pct') if trade.get('actual_return_pct') is not None else '-'}%"
            )
            reason_summary = render_trade_reason_summary(trade, context=decision_context)
            behavior_summary = render_trade_behavior_summary(trade)
            if reason_summary != "-":
                lines.append(f"  - Reasons: {reason_summary}")
            if behavior_summary != "-":
                lines.append(f"  - Behavior: {behavior_summary}")
    else:
        lines.append("- No trades.")

    lines.extend(["", "## Reviews"])
    if reviews:
        for review in reviews:
            lines.append(f"- {review.get('name') or review.get('ts_code')}: {review.get('review_type') or '-'} | feedback={review.get('feedback') or '-'}")
    else:
        lines.append("- No reviews.")

    lines.extend(["", "## Memory Recall"])
    if memory_cells:
        for item in memory_cells[:8]:
            lines.append(f"- {item.get('title') or item.get('memory_id')} | score={item.get('score') if item.get('score') is not None else '-'}")
    else:
        lines.append("- No long-term memory highlights yet.")

    lines.extend(["", "## Skill Cards"])
    if skill_cards:
        for item in skill_cards[:5]:
            lines.append(f"- {item.get('title') or item.get('skill_id')} | samples={item.get('sample_size') or 0}")
    else:
        lines.append("- No skill cards yet.")

    lines.extend(["", "## Manual Reflection", "- What repeated memory mattered most today?", "- Which risk pattern almost came back?", "- What should be solidified into a reusable skill?", ""])
    return "\n".join(lines)


def render_dashboard_note(recent_trades: list[dict[str, Any]], recent_reports: list[dict[str, Any]], recent_skills: list[dict[str, Any]] | None = None) -> str:
    header = frontmatter({"note_type": "dashboard", "tags": ["dashboard", "trade-journal"]})
    lines = [header, "", "# TradeMirrorOS Dashboard", "", "## Recent Trades"]
    if recent_trades:
        for trade in recent_trades[:20]:
            lines.append(
                f"- {trade.get('buy_date') or '-'} | {trade.get('name') or trade.get('ts_code')} | "
                f"return {trade.get('actual_return_pct') if trade.get('actual_return_pct') is not None else '-'}% | "
                f"status {trade.get('status') or '-'}"
            )
    else:
        lines.append("- No trades yet.")
    lines.extend(["", "## Recent Reports"])
    if recent_reports:
        for report in recent_reports[:12]:
            lines.append(f"- {report.get('period_start') or '-'} -> {report.get('period_end') or '-'} | {report.get('period_kind') or '-'}")
    else:
        lines.append("- No health reports yet.")
    lines.extend(["", "## Recent Skill Cards"])
    if recent_skills:
        for skill in recent_skills[:10]:
            lines.append(f"- {skill.get('title') or skill.get('skill_id')} | samples={skill.get('sample_size') or 0}")
    else:
        lines.append("- No skill cards yet.")
    lines.append("")
    return "\n".join(lines)


def render_graph_note(graph_state: dict[str, Any]) -> str:
    stats = graph_state.get("stats") or {}
    scenes = graph_state.get("recent_scenes") or []
    hyperedges = graph_state.get("recent_hyperedges") or []
    memory_rows = graph_state.get("recent_memory_cells") or []
    skill_rows = graph_state.get("recent_skill_cards") or []
    prompt_text = str(graph_state.get("prompt_text") or "").strip()

    header = frontmatter({"note_type": "knowledge_graph_snapshot", "tags": ["knowledge-graph", "openclaw", "trade-journal"]})
    lines = [
        header,
        "",
        "# Local Knowledge Graph Snapshot",
        "",
        "## Counts",
        f"- Plans: {stats.get('plan_count') or 0}",
        f"- Trades: {stats.get('trade_count') or 0}",
        f"- Reviews: {stats.get('review_count') or 0}",
        f"- Memory cells: {stats.get('memory_count') or 0}",
        f"- Scenes: {stats.get('scene_count') or 0}",
        f"- Hyperedges: {stats.get('hyperedge_count') or 0}",
        f"- Skill cards: {stats.get('skill_count') or 0}",
        "",
        "## Recent Scenes",
    ]
    if scenes:
        for scene in scenes[:10]:
            memory_ids = json_loads(scene.get("memory_ids_json"), []) or []
            lines.append(
                f"- {scene.get('title') or scene.get('scene_key') or '-'} | "
                f"type={scene.get('scene_type') or '-'} | memories={len(memory_ids)} | "
                f"{scene.get('description') or '-'}"
            )
    else:
        lines.append("- No scene snapshot yet.")

    lines.extend(["", "## Recent Hyperedges"])
    if hyperedges:
        for edge in hyperedges[:10]:
            tags = ", ".join(json_loads(edge.get("tags_json"), []) or []) or "-"
            lines.append(
                f"- {edge.get('label') or edge.get('edge_key') or '-'} | "
                f"type={edge.get('edge_type') or '-'} | tags={tags}"
            )
    else:
        lines.append("- No hyperedge snapshot yet.")

    lines.extend(["", "## Recent Memory Cells"])
    if memory_rows:
        for row in memory_rows[:10]:
            lines.append(
                f"- {row.get('title') or row.get('memory_id') or '-'} | "
                f"{row.get('memory_kind') or '-'} | date={row.get('trade_date') or '-'} | "
                f"symbol={row.get('ts_code') or '-'}"
            )
    else:
        lines.append("- No memory cells yet.")

    lines.extend(["", "## Recent Skill Cards"])
    if skill_rows:
        for row in skill_rows[:10]:
            lines.append(
                f"- {row.get('title') or row.get('skill_id') or '-'} | "
                f"samples={row.get('sample_size') or 0} | intent={row.get('intent') or '-'}"
            )
    else:
        lines.append("- No skill cards yet.")

    lines.extend(["", "## OpenClaw Prompt"])
    if prompt_text:
        lines.extend(["```text", prompt_text, "```"])
    else:
        lines.append("- No prompt snapshot yet.")
    lines.append("")
    return "\n".join(lines)
