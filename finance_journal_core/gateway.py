from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from .app import create_app


DOMAIN_ALIASES = {
    "plan": "plan",
    "计划": "plan",
    "trade": "trade",
    "交易": "trade",
    "journal": "trade",
    "review": "review",
    "回顾": "review",
    "report": "report",
    "体检": "report",
    "evolution": "evolution",
    "进化": "evolution",
    "reference": "reference",
    "参考": "reference",
    "intake": "intake",
    "记账": "intake",
    "session": "session",
    "会话": "session",
    "vault": "vault",
    "知识库": "vault",
    "memory": "memory",
    "记忆": "memory",
    "skill": "memory",
    "skills": "memory",
    "schedule": "schedule",
    "调度": "schedule",
}

ACTION_ALIASES = {
    "create": "create",
    "新建": "create",
    "新增": "create",
    "list": "list",
    "列表": "list",
    "status": "status",
    "状态": "status",
    "enrich": "enrich",
    "补充": "enrich",
    "reference": "reference",
    "record": "log",
    "记录": "log",
    "log": "log",
    "close": "close",
    "平仓": "close",
    "import": "import-statement",
    "导入": "import-statement",
    "incomplete": "incomplete",
    "缺口": "incomplete",
    "run": "run",
    "执行": "run",
    "respond": "respond",
    "反馈": "respond",
    "health": "health",
    "report": "report",
    "portrait": "portrait",
    "画像": "portrait",
    "remind": "remind",
    "提醒": "remind",
    "parse": "parse",
    "apply": "apply",
    "turn": "turn",
    "接话": "turn",
    "state": "state",
    "恢复": "state",
    "reset": "reset",
    "重置": "reset",
    "sync": "sync",
    "sync-all": "sync-all",
    "sync-root": "sync-all",
    "sync-private": "sync-all",
    "daily": "daily",
    "dashboard": "dashboard",
    "graph": "graph",
    "mirror-root": "mirror-root",
    "rebuild": "rebuild",
    "self-check": "self-check",
    "doctor": "self-check",
    "query": "query",
    "查询": "query",
    "skillize": "skillize",
    "revise": "revise",
    "edit": "revise",
    "skill-edit": "skill-edit",
    "固化": "skillize",
}

KEY_ALIASES = {
    "code": "ts_code",
    "symbol": "ts_code",
    "标的": "ts_code",
    "name": "name",
    "名称": "name",
    "file": "file",
    "文件": "file",
    "trade_date": "trade_date",
    "日期": "trade_date",
    "direction": "direction",
    "方向": "direction",
    "thesis": "thesis",
    "logic": "logic_tags",
    "logic_tags": "logic_tags",
    "pattern_tags": "pattern_tags",
    "market_stage": "market_stage",
    "environment_tags": "environment_tags",
    "buy_zone": "buy_zone",
    "sell_zone": "sell_zone",
    "stop_loss": "stop_loss",
    "holding_period": "holding_period",
    "valid_from": "valid_from",
    "valid_to": "valid_to",
    "id": "id",
    "plan_id": "plan_id",
    "trade_id": "trade_id",
    "review_id": "review_id",
    "report_id": "report_id",
    "memory_id": "memory_id",
    "skill_id": "skill_id",
    "reason": "reason",
    "buy_date": "buy_date",
    "buy_price": "buy_price",
    "sell_date": "sell_date",
    "sell_price": "sell_price",
    "sell_reason": "sell_reason",
    "emotion_notes": "emotion_notes",
    "mistake_tags": "mistake_tags",
    "lessons_learned": "lessons_learned",
    "feedback": "feedback",
    "weight_action": "weight_action",
    "period_start": "period_start",
    "period_end": "period_end",
    "period_kind": "period_kind",
    "lookback_days": "lookback_days",
    "min_samples": "min_samples",
    "session": "session_key",
    "session_key": "session_key",
    "text": "text",
    "content": "text",
    "mode": "mode",
    "status": "status",
    "limit": "limit",
    "full": "full",
    "clean": "clean",
    "tags": "tags",
    "strategy_line": "strategy_line",
    "title": "title",
    "text_body": "text_body",
    "add_tags": "add_tags",
    "remove_tags": "remove_tags",
    "summary_json": "summary_json",
    "quality_json": "quality_json",
    "quality_score": "quality_score",
    "correction_note": "correction_note",
    "trigger_conditions": "trigger_conditions",
    "add_trigger_conditions": "add_trigger_conditions",
    "remove_trigger_conditions": "remove_trigger_conditions",
    "do_not_use_when": "do_not_use_when",
    "add_do_not_use_when": "add_do_not_use_when",
    "remove_do_not_use_when": "remove_do_not_use_when",
    "summary_markdown": "summary_markdown",
    "community_shareable": "community_shareable",
    "intent": "intent",
    "start_date": "start_date",
    "end_date": "end_date",
    "sync_vault_after": "sync_vault_after",
    "rebuild_memory_views": "rebuild_memory_views",
}


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradeMirrorOS OpenClaw gateway")
    parser.add_argument("action", choices=["command"], nargs="?", default="command")
    parser.add_argument("--root", help="Runtime root for data/artifacts")
    parser.add_argument("--disable-market-data", action="store_true")
    parser.add_argument("--command", required=True, help="Structured natural-language command")
    return parser


def _split_command(command: str) -> tuple[str, str, dict[str, str]]:
    tokens = shlex.split(command, posix=False)
    if not tokens:
        raise ValueError("command is empty")
    domain = DOMAIN_ALIASES.get(tokens[0].lower(), DOMAIN_ALIASES.get(tokens[0], tokens[0]))
    action = "list"
    if len(tokens) > 1 and tokens[1] and "=" not in tokens[1]:
        action = ACTION_ALIASES.get(tokens[1].lower(), ACTION_ALIASES.get(tokens[1], tokens[1]))
        kv_tokens = tokens[2:]
    else:
        kv_tokens = tokens[1:]
    params: dict[str, str] = {}
    plain_tokens: list[str] = []
    for item in kv_tokens:
        if "=" not in item:
            plain_tokens.append(item)
            continue
        key, value = item.split("=", 1)
        params[KEY_ALIASES.get(key.lower(), KEY_ALIASES.get(key, key))] = value.strip().strip('"').strip("'")
    if domain in {"intake", "session", "memory"} and plain_tokens and "text" not in params:
        params["text"] = " ".join(plain_tokens).strip()
    return domain, action, params


def dispatch(command: str, anchor_path: Path, runtime_root: str | None = None, enable_market_data: bool = True) -> Any:
    app = create_app(anchor_path, runtime_root=runtime_root, enable_market_data=enable_market_data)
    domain, action, params = _split_command(command)

    if domain == "intake":
        if action == "apply":
            return app.apply_journal_text(params.get("text", ""), mode=params.get("mode", "auto"), trade_date=params.get("trade_date"))
        return app.parse_journal_text(params.get("text", ""), mode=params.get("mode", "auto"), trade_date=params.get("trade_date"))

    if domain == "session":
        if action == "state":
            return app.get_session_state(params.get("session_key", ""))
        if action == "reset":
            return app.reset_session_thread(params.get("session_key", ""), reason=params.get("reason", ""))
        return app.handle_session_turn(
            params.get("session_key", ""),
            params.get("text", ""),
            mode=params.get("mode", "auto"),
            trade_date=params.get("trade_date"),
            lookback_days=int(params.get("lookback_days", 365)),
        )

    if domain == "plan":
        if action == "create":
            return app.create_plan(
                ts_code=params["ts_code"],
                name=params.get("name"),
                direction=params["direction"],
                thesis=params["thesis"],
                logic_tags=params.get("logic_tags", ""),
                market_stage=params.get("market_stage"),
                environment_tags=params.get("environment_tags", ""),
                buy_zone=params.get("buy_zone"),
                sell_zone=params.get("sell_zone"),
                stop_loss=params.get("stop_loss"),
                holding_period=params.get("holding_period"),
                valid_from=params.get("valid_from"),
                valid_to=params.get("valid_to"),
                notes=params.get("notes"),
                decision_context=json.loads(params["decision_context_json"]) if params.get("decision_context_json") else None,
                with_reference=params.get("with_reference", "false").lower() in {"1", "true", "yes", "y"},
                lookback_days=int(params.get("lookback_days", 365)),
            )
        if action == "status":
            return app.update_plan_status(params.get("plan_id") or params.get("id") or "", status=params["status"], trade_id=params.get("trade_id"), reason=params.get("reason"))
        if action == "enrich":
            return app.enrich_plan_from_text(params.get("plan_id") or params.get("id") or "", params.get("text", ""), trade_date=params.get("trade_date"), lookback_days=int(params.get("lookback_days", 365)))
        if action == "reference":
            return app.generate_reference(
                logic_tags=params.get("logic_tags", ""),
                market_stage=params.get("market_stage"),
                environment_tags=params.get("environment_tags", ""),
                lookback_days=int(params.get("lookback_days", 365)),
                trade_date=params.get("trade_date"),
                write_artifact=True,
            )
        return app.list_plans(status=params.get("status"), active_only=params.get("active_only", "false").lower() in {"1", "true", "yes", "y"}, trade_date=params.get("trade_date"))

    if domain == "trade":
        if action == "import-statement":
            return app.import_statement_file(params["file"], trade_date=params.get("trade_date"), session_key=params.get("session_key"))
        if action == "incomplete":
            return app.build_trade_follow_up_backlog(status=params.get("status"), limit=int(params.get("limit", 200)), trade_date=params.get("trade_date"), ts_code=params.get("ts_code"), include_complete=params.get("include_complete", "false").lower() in {"1", "true", "yes", "y"})
        if action == "close":
            return app.close_trade(
                params.get("trade_id") or params.get("id") or "",
                sell_date=params["sell_date"],
                sell_price=float(params["sell_price"]),
                sell_reason=params.get("sell_reason", ""),
                emotion_notes=params.get("emotion_notes"),
                mistake_tags=params.get("mistake_tags", ""),
                lessons_learned=params.get("lessons_learned"),
                notes=params.get("notes"),
            )
        if action == "enrich":
            return app.enrich_trade_from_text(params.get("trade_id") or params.get("id") or "", params.get("text", ""), trade_date=params.get("trade_date"), lookback_days=int(params.get("lookback_days", 365)))
        if action == "log":
            return app.log_trade(
                ts_code=params["ts_code"],
                name=params.get("name"),
                plan_id=params.get("plan_id"),
                direction=params.get("direction", "long"),
                buy_date=params["buy_date"],
                buy_price=float(params["buy_price"]),
                thesis=params["thesis"],
                sell_date=params.get("sell_date"),
                sell_price=float(params["sell_price"]) if params.get("sell_price") else None,
                sell_reason=params.get("sell_reason", ""),
                logic_type_tags=params.get("logic_tags", ""),
                pattern_tags=params.get("pattern_tags", ""),
                market_stage_tag=params.get("market_stage"),
                environment_tags=params.get("environment_tags", ""),
                emotion_notes=params.get("emotion_notes"),
                mistake_tags=params.get("mistake_tags", ""),
                lessons_learned=params.get("lessons_learned"),
                notes=params.get("notes"),
                decision_context=json.loads(params["decision_context_json"]) if params.get("decision_context_json") else None,
            )
        return app.list_trades(status=params.get("status"), limit=int(params.get("limit", 50)))

    if domain == "review":
        if action == "run":
            return app.run_review_cycle(as_of_date=params.get("as_of_date") or params.get("trade_date"))
        if action == "respond":
            return app.respond_review(params.get("review_id") or params.get("id") or "", feedback=params["feedback"], weight_action=params.get("weight_action", ""))
        return app.list_reviews(status=params.get("status"), limit=int(params.get("limit", 50)))

    if domain == "report":
        return app.generate_health_report(params["period_start"], params["period_end"], period_kind=params.get("period_kind", "custom"))

    if domain == "reference":
        return app.generate_reference(
            logic_tags=params.get("logic_tags", ""),
            market_stage=params.get("market_stage"),
            environment_tags=params.get("environment_tags", ""),
            lookback_days=int(params.get("lookback_days", 365)),
            trade_date=params.get("trade_date"),
            write_artifact=True,
        )

    if domain == "evolution":
        if action == "portrait":
            return app.generate_style_portrait(trade_date=params.get("trade_date"), lookback_days=int(params.get("lookback_days", 365)), min_samples=int(params.get("min_samples", 2)), write_artifact=True)
        if action == "remind":
            return app.generate_evolution_reminder(
                logic_tags=params.get("logic_tags", ""),
                pattern_tags=params.get("pattern_tags", ""),
                market_stage=params.get("market_stage"),
                environment_tags=params.get("environment_tags", ""),
                lookback_days=int(params.get("lookback_days", 365)),
                trade_date=params.get("trade_date"),
                min_samples=int(params.get("min_samples", 2)),
                write_artifact=True,
            )
        return app.generate_evolution_report(trade_date=params.get("trade_date"), lookback_days=int(params.get("lookback_days", 365)), min_samples=int(params.get("min_samples", 2)), write_artifact=True)

    if domain == "memory":
        if action == "rebuild":
            return app.rebuild_memory(limit=int(params.get("limit", 0)))
        if action == "revise":
            return app.revise_memory_cell(
                params.get("memory_id") or params.get("id") or "",
                title=params.get("title"),
                text_body=params.get("text_body"),
                trade_date=params.get("trade_date"),
                market_stage=params.get("market_stage"),
                strategy_line=params.get("strategy_line"),
                tags=params.get("tags"),
                add_tags=params.get("add_tags", ""),
                remove_tags=params.get("remove_tags", ""),
                summary_patch=json.loads(params["summary_json"]) if params.get("summary_json") else None,
                quality_patch=json.loads(params["quality_json"]) if params.get("quality_json") else None,
                quality_score=float(params["quality_score"]) if params.get("quality_score") is not None else None,
                correction_note=params.get("correction_note"),
            )
        if action == "skill-edit":
            return app.revise_skill_card(
                params.get("skill_id") or params.get("id") or "",
                title=params.get("title"),
                intent=params.get("intent"),
                trigger_conditions=params.get("trigger_conditions"),
                add_trigger_conditions=params.get("add_trigger_conditions", ""),
                remove_trigger_conditions=params.get("remove_trigger_conditions", ""),
                do_not_use_when=params.get("do_not_use_when"),
                add_do_not_use_when=params.get("add_do_not_use_when", ""),
                remove_do_not_use_when=params.get("remove_do_not_use_when", ""),
                summary_markdown=params.get("summary_markdown"),
                community_shareable=(
                    None
                    if params.get("community_shareable") is None
                    else params.get("community_shareable", "").lower() in {"1", "true", "yes", "y"}
                ),
            )
        if action == "skillize":
            return app.skillize_memory(trade_date=params.get("trade_date"), lookback_days=int(params.get("lookback_days", 365)), min_samples=int(params.get("min_samples", 2)))
        return app.query_memory(
            text=params.get("text", ""),
            ts_code=params.get("ts_code"),
            strategy_line=params.get("strategy_line"),
            market_stage=params.get("market_stage"),
            tags=params.get("tags", ""),
            trade_date=params.get("trade_date"),
            limit=int(params.get("limit", 8)),
        )

    if domain == "vault":
        if action == "sync":
            return app.sync_vault(
                trade_date=params.get("trade_date"),
                limit=int(params.get("limit", 200)),
                full=params.get("full", "false").lower() in {"1", "true", "yes", "y"},
                clean=params.get("clean", "false").lower() in {"1", "true", "yes", "y"},
            )
        if action == "sync-all":
            return app.sync_repo_snapshot()
        if action == "daily":
            return app.export_daily_note(params["trade_date"])
        if action == "plan":
            return app.export_plan_note(params.get("plan_id") or params.get("id") or "")
        if action == "trade":
            return app.export_trade_note(params.get("trade_id") or params.get("id") or "")
        if action == "review":
            return app.export_review_note(params.get("review_id") or params.get("id") or "")
        if action == "report":
            return app.export_report_note(params.get("report_id") or params.get("id") or "")
        if action == "memory":
            return app.export_memory_note(params.get("memory_id") or params.get("id") or "")
        if action == "skill":
            return app.export_skill_note(params.get("skill_id") or params.get("id") or "")
        if action == "graph":
            return app.export_graph_note()
        if action == "mirror-root":
            return app.mirror_runtime_exports_to_repo_root()
        return app.export_dashboard_note()

    if domain == "schedule":
        return app.run_schedule(now=params.get("now"), force=params.get("force", "false").lower() in {"1", "true", "yes", "y"}, dry_run=params.get("dry_run", "false").lower() in {"1", "true", "yes", "y"})

    if domain == "maintenance":
        if action == "self-check":
            return app.runtime_self_check()
        if action == "purge-range":
            return app.purge_records_in_date_range(
                params["start_date"],
                params["end_date"],
                rebuild_memory_views=params.get("rebuild_memory_views", "true").lower() in {"1", "true", "yes", "y"},
                sync_vault_after=params.get("sync_vault_after", "true").lower() in {"1", "true", "yes", "y"},
            )
        raise ValueError(f"unsupported maintenance action: {action}")

    raise ValueError(f"unsupported domain: {domain}")


def main(argv: list[str] | None = None, anchor_path: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if anchor_path is None:
        anchor_path = Path(__file__).resolve()
    payload = dispatch(args.command, anchor_path=anchor_path, runtime_root=args.root, enable_market_data=not args.disable_market_data)
    _print(payload)
    return 0
