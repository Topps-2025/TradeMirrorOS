from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .app import create_app


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_json_argument(text: str | None) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("decision-context-json must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradeMirrorOS OpenClaw skill CLI")
    parser.add_argument("--root", help="Runtime root for data/artifacts")
    parser.add_argument("--disable-market-data", action="store_true", help="Do not call market data providers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize runtime folders and SQLite schema")

    intake = subparsers.add_parser("intake", help="Parse and apply non-standard journal text")
    intake_sub = intake.add_subparsers(dest="action", required=True)
    for action_name in ("parse", "apply", "draft-start"):
        action = intake_sub.add_parser(action_name)
        action.add_argument("--text", required=True)
        action.add_argument("--mode", choices=["auto", "trade", "plan"], default="auto")
        action.add_argument("--trade-date")
        if action_name == "draft-start":
            action.add_argument("--session-key")
    intake_draft_reply = intake_sub.add_parser("draft-reply")
    intake_draft_reply.add_argument("draft_id", nargs="?")
    intake_draft_reply.add_argument("--text", required=True)
    intake_draft_reply.add_argument("--no-apply-if-ready", action="store_true")
    intake_draft_reply.add_argument("--session-key")
    for action_name in ("draft-show", "draft-apply"):
        action = intake_sub.add_parser(action_name)
        action.add_argument("draft_id", nargs="?")
        action.add_argument("--session-key")
    intake_draft_list = intake_sub.add_parser("draft-list")
    intake_draft_list.add_argument("--status")
    intake_draft_list.add_argument("--limit", type=int, default=20)
    intake_draft_list.add_argument("--session-key")
    intake_draft_cancel = intake_sub.add_parser("draft-cancel")
    intake_draft_cancel.add_argument("draft_id", nargs="?")
    intake_draft_cancel.add_argument("--reason", default="")
    intake_draft_cancel.add_argument("--session-key")

    vault = subparsers.add_parser("vault", help="Manage markdown vault exports")
    vault_sub = vault.add_subparsers(dest="action", required=True)
    vault_sub.add_parser("init")
    vault_sync = vault_sub.add_parser("sync")
    vault_sync.add_argument("--trade-date")
    vault_sync.add_argument("--limit", type=int, default=200)
    vault_sync.add_argument("--full", action="store_true")
    vault_sync.add_argument("--clean", action="store_true")
    vault_daily = vault_sub.add_parser("daily")
    vault_daily.add_argument("--trade-date", required=True)
    vault_plan = vault_sub.add_parser("plan")
    vault_plan.add_argument("plan_id")
    vault_trade = vault_sub.add_parser("trade")
    vault_trade.add_argument("trade_id")
    vault_review = vault_sub.add_parser("review")
    vault_review.add_argument("review_id")
    vault_report = vault_sub.add_parser("report")
    vault_report.add_argument("report_id")
    vault_memory = vault_sub.add_parser("memory")
    vault_memory.add_argument("memory_id")
    vault_skill = vault_sub.add_parser("skill")
    vault_skill.add_argument("skill_id")
    vault_sub.add_parser("dashboard")
    vault_sub.add_parser("graph")
    vault_sub.add_parser("mirror-root")
    vault_sub.add_parser("sync-all", aliases=["sync-root", "sync-private"])

    plan = subparsers.add_parser("plan", help="Manage trade plans")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    plan_create = plan_sub.add_parser("create")
    plan_create.add_argument("--ts-code", required=True)
    plan_create.add_argument("--name")
    plan_create.add_argument("--direction", required=True)
    plan_create.add_argument("--thesis", required=True)
    plan_create.add_argument("--logic-tags", default="")
    plan_create.add_argument("--market-stage")
    plan_create.add_argument("--environment-tags", default="")
    plan_create.add_argument("--buy-zone")
    plan_create.add_argument("--sell-zone")
    plan_create.add_argument("--stop-loss")
    plan_create.add_argument("--holding-period")
    plan_create.add_argument("--valid-from")
    plan_create.add_argument("--valid-to")
    plan_create.add_argument("--reminder-time")
    plan_create.add_argument("--notes")
    plan_create.add_argument("--decision-context-json", default="")
    plan_create.add_argument("--with-reference", action="store_true")
    plan_create.add_argument("--lookback-days", type=int, default=365)
    plan_list = plan_sub.add_parser("list")
    plan_list.add_argument("--status")
    plan_list.add_argument("--active-only", action="store_true")
    plan_list.add_argument("--trade-date")
    plan_status = plan_sub.add_parser("status")
    plan_status.add_argument("plan_id")
    plan_status.add_argument("--status", required=True)
    plan_status.add_argument("--trade-id")
    plan_status.add_argument("--reason")
    plan_enrich = plan_sub.add_parser("enrich")
    plan_enrich.add_argument("plan_id")
    plan_enrich.add_argument("--text", required=True)
    plan_enrich.add_argument("--trade-date")
    plan_enrich.add_argument("--lookback-days", type=int, default=365)
    plan_ref = plan_sub.add_parser("reference")
    plan_ref.add_argument("--logic-tags", default="")
    plan_ref.add_argument("--market-stage")
    plan_ref.add_argument("--environment-tags", default="")
    plan_ref.add_argument("--lookback-days", type=int, default=365)
    plan_ref.add_argument("--trade-date")

    trade = subparsers.add_parser("trade", help="Manage trade journal")
    trade_sub = trade.add_subparsers(dest="action", required=True)
    trade_log = trade_sub.add_parser("log")
    trade_log.add_argument("--ts-code", required=True)
    trade_log.add_argument("--name")
    trade_log.add_argument("--plan-id")
    trade_log.add_argument("--direction", default="long")
    trade_log.add_argument("--buy-date", required=True)
    trade_log.add_argument("--buy-price", required=True, type=float)
    trade_log.add_argument("--thesis", required=True)
    trade_log.add_argument("--buy-reason", default="")
    trade_log.add_argument("--buy-position", default="")
    trade_log.add_argument("--sell-date")
    trade_log.add_argument("--sell-price", type=float)
    trade_log.add_argument("--sell-reason", default="")
    trade_log.add_argument("--sell-position", default="")
    trade_log.add_argument("--position-size-pct", type=float)
    trade_log.add_argument("--logic-type-tags", default="")
    trade_log.add_argument("--pattern-tags", default="")
    trade_log.add_argument("--theme")
    trade_log.add_argument("--market-stage")
    trade_log.add_argument("--environment-tags", default="")
    trade_log.add_argument("--emotion-notes")
    trade_log.add_argument("--mistake-tags", default="")
    trade_log.add_argument("--lessons-learned")
    trade_log.add_argument("--notes")
    trade_log.add_argument("--decision-context-json", default="")
    trade_log.add_argument("--fetch-snapshot", action="store_true")
    trade_log.add_argument("--sector-name")
    trade_log.add_argument("--sector-change-pct", type=float)
    trade_close = trade_sub.add_parser("close")
    trade_close.add_argument("trade_id")
    trade_close.add_argument("--sell-date", required=True)
    trade_close.add_argument("--sell-price", required=True, type=float)
    trade_close.add_argument("--sell-reason", default="")
    trade_close.add_argument("--sell-position", default="")
    trade_close.add_argument("--emotion-notes")
    trade_close.add_argument("--mistake-tags", default="")
    trade_close.add_argument("--lessons-learned")
    trade_close.add_argument("--notes")
    trade_enrich = trade_sub.add_parser("enrich")
    trade_enrich.add_argument("trade_id")
    trade_enrich.add_argument("--text", required=True)
    trade_enrich.add_argument("--trade-date")
    trade_enrich.add_argument("--lookback-days", type=int, default=365)
    trade_import = trade_sub.add_parser("import-statement")
    trade_import.add_argument("--file", required=True)
    trade_import.add_argument("--trade-date")
    trade_import.add_argument("--session-key")
    trade_incomplete = trade_sub.add_parser("incomplete")
    trade_incomplete.add_argument("--status")
    trade_incomplete.add_argument("--limit", type=int, default=200)
    trade_incomplete.add_argument("--trade-date")
    trade_incomplete.add_argument("--ts-code")
    trade_incomplete.add_argument("--include-complete", action="store_true")
    trade_list = trade_sub.add_parser("list")
    trade_list.add_argument("--status")
    trade_list.add_argument("--limit", type=int, default=50)

    review = subparsers.add_parser("review", help="Manage sell-side reviews")
    review_sub = review.add_subparsers(dest="action", required=True)
    review_run = review_sub.add_parser("run")
    review_run.add_argument("--as-of-date")
    review_list = review_sub.add_parser("list")
    review_list.add_argument("--status")
    review_list.add_argument("--limit", type=int, default=50)
    review_resp = review_sub.add_parser("respond")
    review_resp.add_argument("review_id")
    review_resp.add_argument("--feedback", required=True)
    review_resp.add_argument("--weight-action", default="")

    report = subparsers.add_parser("report", help="Generate reports")
    report_sub = report.add_subparsers(dest="action", required=True)
    report_health = report_sub.add_parser("health")
    report_health.add_argument("--period-start", required=True)
    report_health.add_argument("--period-end", required=True)
    report_health.add_argument("--period-kind", default="custom")

    evolution = subparsers.add_parser("evolution", help="Generate self-evolution paths and reminders")
    evolution_sub = evolution.add_subparsers(dest="action", required=True)
    evolution_report = evolution_sub.add_parser("report")
    evolution_report.add_argument("--trade-date")
    evolution_report.add_argument("--lookback-days", type=int, default=365)
    evolution_report.add_argument("--min-samples", type=int, default=2)
    evolution_portrait = evolution_sub.add_parser("portrait")
    evolution_portrait.add_argument("--trade-date")
    evolution_portrait.add_argument("--lookback-days", type=int, default=365)
    evolution_portrait.add_argument("--min-samples", type=int, default=2)
    evolution_remind = evolution_sub.add_parser("remind")
    evolution_remind.add_argument("--logic-tags", default="")
    evolution_remind.add_argument("--pattern-tags", default="")
    evolution_remind.add_argument("--market-stage")
    evolution_remind.add_argument("--environment-tags", default="")
    evolution_remind.add_argument("--trade-date")
    evolution_remind.add_argument("--lookback-days", type=int, default=365)
    evolution_remind.add_argument("--min-samples", type=int, default=2)

    memory = subparsers.add_parser("memory", help="Manage long-term trade memory")
    memory_sub = memory.add_subparsers(dest="action", required=True)
    memory_rebuild = memory_sub.add_parser("rebuild")
    memory_rebuild.add_argument("--limit", type=int, default=0)
    memory_query = memory_sub.add_parser("query")
    memory_query.add_argument("--text", default="")
    memory_query.add_argument("--ts-code")
    memory_query.add_argument("--strategy-line")
    memory_query.add_argument("--market-stage")
    memory_query.add_argument("--tags", default="")
    memory_query.add_argument("--trade-date")
    memory_query.add_argument("--limit", type=int, default=8)
    memory_skillize = memory_sub.add_parser("skillize")
    memory_skillize.add_argument("--trade-date")
    memory_skillize.add_argument("--lookback-days", type=int, default=365)
    memory_skillize.add_argument("--min-samples", type=int, default=2)
    memory_revise = memory_sub.add_parser("revise")
    memory_revise.add_argument("memory_id")
    memory_revise.add_argument("--title")
    memory_revise.add_argument("--text-body")
    memory_revise.add_argument("--trade-date")
    memory_revise.add_argument("--market-stage")
    memory_revise.add_argument("--strategy-line")
    memory_revise.add_argument("--tags")
    memory_revise.add_argument("--add-tags", default="")
    memory_revise.add_argument("--remove-tags", default="")
    memory_revise.add_argument("--summary-json", default="")
    memory_revise.add_argument("--quality-json", default="")
    memory_revise.add_argument("--quality-score", type=float)
    memory_revise.add_argument("--correction-note")
    memory_skill_edit = memory_sub.add_parser("skill-edit")
    memory_skill_edit.add_argument("skill_id")
    memory_skill_edit.add_argument("--title")
    memory_skill_edit.add_argument("--intent")
    memory_skill_edit.add_argument("--trigger-conditions")
    memory_skill_edit.add_argument("--add-trigger-conditions", default="")
    memory_skill_edit.add_argument("--remove-trigger-conditions", default="")
    memory_skill_edit.add_argument("--do-not-use-when")
    memory_skill_edit.add_argument("--add-do-not-use-when", default="")
    memory_skill_edit.add_argument("--remove-do-not-use-when", default="")
    memory_skill_edit.add_argument("--summary-markdown")
    memory_skill_edit.add_argument("--community-shareable", choices=["true", "false"])

    schedule = subparsers.add_parser("schedule", help="Run scheduler checks")
    schedule.add_argument("--now", help="Current timestamp, format YYYY-MM-DDTHH:MM")
    schedule.add_argument("--force", action="store_true")
    schedule.add_argument("--dry-run", action="store_true")

    maintenance = subparsers.add_parser("maintenance", help="Run maintenance and runtime diagnostics")
    maintenance_sub = maintenance.add_subparsers(dest="action", required=True)
    maintenance_sub.add_parser("self-check")
    maintenance_purge = maintenance_sub.add_parser("purge-range")
    maintenance_purge.add_argument("--start-date", required=True)
    maintenance_purge.add_argument("--end-date", required=True)
    maintenance_purge.add_argument("--no-rebuild-memory", action="store_true")
    maintenance_purge.add_argument("--no-sync-vault", action="store_true")

    session = subparsers.add_parser("session", help="OpenClaw-oriented session state machine")
    session_sub = session.add_subparsers(dest="action", required=True)
    session_turn = session_sub.add_parser("turn")
    session_turn.add_argument("--session-key", required=True)
    session_turn.add_argument("--text", required=True)
    session_turn.add_argument("--mode", choices=["auto", "trade", "plan"], default="auto")
    session_turn.add_argument("--trade-date")
    session_turn.add_argument("--lookback-days", type=int, default=365)
    session_state = session_sub.add_parser("state")
    session_state.add_argument("--session-key", required=True)
    session_reset = session_sub.add_parser("reset")
    session_reset.add_argument("--session-key", required=True)
    session_reset.add_argument("--reason", default="")

    return parser


def main(argv: list[str] | None = None, anchor_path: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if anchor_path is None:
        anchor_path = Path(__file__).resolve()
    app = create_app(anchor_path, runtime_root=args.root, enable_market_data=not args.disable_market_data)

    if args.command == "init":
        _print_json(app.init_runtime())
        return 0

    if args.command == "intake":
        if args.action == "parse":
            _print_json(app.parse_journal_text(args.text, mode=args.mode, trade_date=args.trade_date))
        elif args.action == "apply":
            _print_json(app.apply_journal_text(args.text, mode=args.mode, trade_date=args.trade_date))
        elif args.action == "draft-start":
            _print_json(app.start_journal_draft(args.text, mode=args.mode, trade_date=args.trade_date, session_key=args.session_key))
        elif args.action == "draft-reply":
            _print_json(
                app.continue_journal_draft(
                    args.draft_id,
                    args.text,
                    apply_if_ready=not args.no_apply_if_ready,
                    session_key=args.session_key,
                )
            )
        elif args.action == "draft-show":
            _print_json(app.get_journal_draft(args.draft_id, session_key=args.session_key))
        elif args.action == "draft-apply":
            _print_json(app.apply_journal_draft(args.draft_id, session_key=args.session_key))
        elif args.action == "draft-list":
            _print_json(app.list_journal_drafts(status=args.status, limit=args.limit, session_key=args.session_key))
        else:
            _print_json(app.cancel_journal_draft(args.draft_id, reason=args.reason, session_key=args.session_key))
        return 0

    if args.command == "vault":
        if args.action == "init":
            _print_json(app.init_vault())
        elif args.action == "sync":
            _print_json(app.sync_vault(trade_date=args.trade_date, limit=args.limit, full=args.full, clean=args.clean))
        elif args.action == "daily":
            _print_json(app.export_daily_note(args.trade_date))
        elif args.action == "plan":
            _print_json(app.export_plan_note(args.plan_id))
        elif args.action == "trade":
            _print_json(app.export_trade_note(args.trade_id))
        elif args.action == "review":
            _print_json(app.export_review_note(args.review_id))
        elif args.action == "report":
            _print_json(app.export_report_note(args.report_id))
        elif args.action == "memory":
            _print_json(app.export_memory_note(args.memory_id))
        elif args.action == "skill":
            _print_json(app.export_skill_note(args.skill_id))
        elif args.action == "graph":
            _print_json(app.export_graph_note())
        elif args.action == "mirror-root":
            _print_json(app.mirror_runtime_exports_to_repo_root())
        elif args.action == "sync-all":
            _print_json(app.sync_repo_snapshot())
        else:
            _print_json(app.export_dashboard_note())
        return 0

    if args.command == "plan":
        if args.action == "create":
            _print_json(
                app.create_plan(
                    ts_code=args.ts_code,
                    name=args.name,
                    direction=args.direction,
                    thesis=args.thesis,
                    logic_tags=args.logic_tags,
                    market_stage=args.market_stage,
                    environment_tags=args.environment_tags,
                    buy_zone=args.buy_zone,
                    sell_zone=args.sell_zone,
                    stop_loss=args.stop_loss,
                    holding_period=args.holding_period,
                    valid_from=args.valid_from,
                    valid_to=args.valid_to,
                    reminder_time=args.reminder_time,
                    notes=args.notes,
                    decision_context=_parse_json_argument(args.decision_context_json),
                    with_reference=args.with_reference,
                    lookback_days=args.lookback_days,
                )
            )
        elif args.action == "list":
            _print_json(app.list_plans(status=args.status, active_only=args.active_only, trade_date=args.trade_date))
        elif args.action == "status":
            _print_json(app.update_plan_status(args.plan_id, status=args.status, trade_id=args.trade_id, reason=args.reason))
        elif args.action == "enrich":
            _print_json(app.enrich_plan_from_text(args.plan_id, args.text, trade_date=args.trade_date, lookback_days=args.lookback_days))
        else:
            _print_json(
                app.generate_reference(
                    logic_tags=args.logic_tags,
                    market_stage=args.market_stage,
                    environment_tags=args.environment_tags,
                    lookback_days=args.lookback_days,
                    trade_date=args.trade_date,
                    write_artifact=True,
                )
            )
        return 0

    if args.command == "trade":
        if args.action == "log":
            _print_json(
                app.log_trade(
                    ts_code=args.ts_code,
                    name=args.name,
                    plan_id=args.plan_id,
                    direction=args.direction,
                    buy_date=args.buy_date,
                    buy_price=args.buy_price,
                    thesis=args.thesis,
                    buy_reason=args.buy_reason,
                    buy_position=args.buy_position,
                    sell_date=args.sell_date,
                    sell_price=args.sell_price,
                    sell_reason=args.sell_reason,
                    sell_position=args.sell_position,
                    position_size_pct=args.position_size_pct,
                    logic_type_tags=args.logic_type_tags,
                    pattern_tags=args.pattern_tags,
                    theme=args.theme,
                    market_stage_tag=args.market_stage,
                    environment_tags=args.environment_tags,
                    emotion_notes=args.emotion_notes,
                    mistake_tags=args.mistake_tags,
                    lessons_learned=args.lessons_learned,
                    notes=args.notes,
                    decision_context=_parse_json_argument(args.decision_context_json),
                    fetch_snapshot=args.fetch_snapshot,
                    sector_name=args.sector_name,
                    sector_change_pct=args.sector_change_pct,
                )
            )
        elif args.action == "close":
            _print_json(
                app.close_trade(
                    args.trade_id,
                    sell_date=args.sell_date,
                    sell_price=args.sell_price,
                    sell_reason=args.sell_reason,
                    sell_position=args.sell_position,
                    emotion_notes=args.emotion_notes,
                    mistake_tags=args.mistake_tags,
                    lessons_learned=args.lessons_learned,
                    notes=args.notes,
                )
            )
        elif args.action == "enrich":
            _print_json(app.enrich_trade_from_text(args.trade_id, args.text, trade_date=args.trade_date, lookback_days=args.lookback_days))
        elif args.action == "import-statement":
            _print_json(app.import_statement_file(args.file, trade_date=args.trade_date, session_key=args.session_key))
        elif args.action == "incomplete":
            _print_json(
                app.build_trade_follow_up_backlog(
                    status=args.status,
                    limit=args.limit,
                    trade_date=args.trade_date,
                    ts_code=args.ts_code,
                    include_complete=args.include_complete,
                )
            )
        else:
            _print_json(app.list_trades(status=args.status, limit=args.limit))
        return 0

    if args.command == "review":
        if args.action == "run":
            _print_json(app.run_review_cycle(as_of_date=args.as_of_date))
        elif args.action == "list":
            _print_json(app.list_reviews(status=args.status, limit=args.limit))
        else:
            _print_json(app.respond_review(args.review_id, feedback=args.feedback, weight_action=args.weight_action))
        return 0

    if args.command == "report":
        _print_json(app.generate_health_report(args.period_start, args.period_end, period_kind=args.period_kind))
        return 0

    if args.command == "evolution":
        if args.action == "report":
            _print_json(app.generate_evolution_report(trade_date=args.trade_date, lookback_days=args.lookback_days, min_samples=args.min_samples))
        elif args.action == "portrait":
            _print_json(app.generate_style_portrait(trade_date=args.trade_date, lookback_days=args.lookback_days, min_samples=args.min_samples))
        else:
            _print_json(
                app.generate_evolution_reminder(
                    logic_tags=args.logic_tags,
                    pattern_tags=args.pattern_tags,
                    market_stage=args.market_stage,
                    environment_tags=args.environment_tags,
                    trade_date=args.trade_date,
                    lookback_days=args.lookback_days,
                    min_samples=args.min_samples,
                    write_artifact=True,
                )
            )
        return 0

    if args.command == "memory":
        if args.action == "rebuild":
            _print_json(app.rebuild_memory(limit=args.limit))
        elif args.action == "query":
            _print_json(
                app.query_memory(
                    text=args.text,
                    ts_code=args.ts_code,
                    strategy_line=args.strategy_line,
                    market_stage=args.market_stage,
                    tags=args.tags,
                    trade_date=args.trade_date,
                    limit=args.limit,
                )
            )
        elif args.action == "revise":
            _print_json(
                app.revise_memory_cell(
                    args.memory_id,
                    title=args.title,
                    text_body=args.text_body,
                    trade_date=args.trade_date,
                    market_stage=args.market_stage,
                    strategy_line=args.strategy_line,
                    tags=args.tags,
                    add_tags=args.add_tags,
                    remove_tags=args.remove_tags,
                    summary_patch=_parse_json_argument(args.summary_json),
                    quality_patch=_parse_json_argument(args.quality_json),
                    quality_score=args.quality_score,
                    correction_note=args.correction_note,
                )
            )
        elif args.action == "skill-edit":
            _print_json(
                app.revise_skill_card(
                    args.skill_id,
                    title=args.title,
                    intent=args.intent,
                    trigger_conditions=args.trigger_conditions,
                    add_trigger_conditions=args.add_trigger_conditions,
                    remove_trigger_conditions=args.remove_trigger_conditions,
                    do_not_use_when=args.do_not_use_when,
                    add_do_not_use_when=args.add_do_not_use_when,
                    remove_do_not_use_when=args.remove_do_not_use_when,
                    summary_markdown=args.summary_markdown,
                    community_shareable=None if args.community_shareable is None else args.community_shareable == "true",
                )
            )
        else:
            _print_json(app.skillize_memory(trade_date=args.trade_date, lookback_days=args.lookback_days, min_samples=args.min_samples))
        return 0

    if args.command == "schedule":
        _print_json(app.run_schedule(now=args.now, force=args.force, dry_run=args.dry_run))
        return 0

    if args.command == "maintenance":
        if args.action == "self-check":
            _print_json(app.runtime_self_check())
        else:
            _print_json(
                app.purge_records_in_date_range(
                    args.start_date,
                    args.end_date,
                    rebuild_memory_views=not args.no_rebuild_memory,
                    sync_vault_after=not args.no_sync_vault,
                )
            )
        return 0

    if args.command == "session":
        if args.action == "turn":
            _print_json(app.handle_session_turn(args.session_key, args.text, mode=args.mode, trade_date=args.trade_date, lookback_days=args.lookback_days))
        elif args.action == "state":
            _print_json(app.get_session_state(args.session_key))
        else:
            _print_json(app.reset_session_thread(args.session_key, reason=args.reason))
        return 0

    return 1
