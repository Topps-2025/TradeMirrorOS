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
    parser = argparse.ArgumentParser(description="Finance Journal OpenClaw skill CLI")
    parser.add_argument("--root", help="Runtime root for data/artifacts")
    parser.add_argument("--disable-market-data", action="store_true", help="Do not call Tushare")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize runtime folders and SQLite schema")

    intake = subparsers.add_parser("intake", help="Parse and apply non-standard journal text")
    intake_sub = intake.add_subparsers(dest="action", required=True)
    intake_parse = intake_sub.add_parser("parse")
    intake_parse.add_argument("--text", required=True)
    intake_parse.add_argument("--mode", choices=["auto", "trade", "plan"], default="auto")
    intake_parse.add_argument("--trade-date")
    intake_apply = intake_sub.add_parser("apply")
    intake_apply.add_argument("--text", required=True)
    intake_apply.add_argument("--mode", choices=["auto", "trade", "plan"], default="auto")
    intake_apply.add_argument("--trade-date")
    intake_draft_start = intake_sub.add_parser("draft-start")
    intake_draft_start.add_argument("--text", required=True)
    intake_draft_start.add_argument("--mode", choices=["auto", "trade", "plan"], default="auto")
    intake_draft_start.add_argument("--trade-date")
    intake_draft_start.add_argument("--session-key")
    intake_draft_reply = intake_sub.add_parser("draft-reply")
    intake_draft_reply.add_argument("draft_id", nargs="?")
    intake_draft_reply.add_argument("--text", required=True)
    intake_draft_reply.add_argument("--no-apply-if-ready", action="store_true")
    intake_draft_reply.add_argument("--session-key")
    intake_draft_show = intake_sub.add_parser("draft-show")
    intake_draft_show.add_argument("draft_id", nargs="?")
    intake_draft_show.add_argument("--session-key")
    intake_draft_apply = intake_sub.add_parser("draft-apply")
    intake_draft_apply.add_argument("draft_id", nargs="?")
    intake_draft_apply.add_argument("--session-key")
    intake_draft_list = intake_sub.add_parser("draft-list")
    intake_draft_list.add_argument("--status")
    intake_draft_list.add_argument("--limit", type=int, default=20)
    intake_draft_list.add_argument("--session-key")
    intake_draft_cancel = intake_sub.add_parser("draft-cancel")
    intake_draft_cancel.add_argument("draft_id", nargs="?")
    intake_draft_cancel.add_argument("--reason", default="")
    intake_draft_cancel.add_argument("--session-key")

    vault = subparsers.add_parser("vault", help="Manage Obsidian-style markdown vault")
    vault_sub = vault.add_subparsers(dest="action", required=True)
    vault_sub.add_parser("init")
    vault_sync = vault_sub.add_parser("sync")
    vault_sync.add_argument("--trade-date")
    vault_sync.add_argument("--limit", type=int, default=200)
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
    vault_sub.add_parser("dashboard")

    watchlist = subparsers.add_parser("watchlist", help="Manage watchlist")
    watchlist_sub = watchlist.add_subparsers(dest="action", required=True)
    watch_add = watchlist_sub.add_parser("add")
    watch_add.add_argument("ts_code")
    watch_add.add_argument("--name")
    watch_add.add_argument("--notes", default="")
    watch_add.add_argument("--source", default="manual")
    watchlist_sub.add_parser("list")
    watch_remove = watchlist_sub.add_parser("remove")
    watch_remove.add_argument("ts_code")

    keyword = subparsers.add_parser("keyword", help="Manage topic keywords")
    keyword_sub = keyword.add_subparsers(dest="action", required=True)
    keyword_add = keyword_sub.add_parser("add")
    keyword_add.add_argument("keyword")
    keyword_add.add_argument("--category", default="industry")
    keyword_sub.add_parser("list")
    keyword_remove = keyword_sub.add_parser("remove")
    keyword_remove.add_argument("keyword")

    event = subparsers.add_parser("event", help="Manage info events")
    event_sub = event.add_subparsers(dest="action", required=True)
    event_add = event_sub.add_parser("add")
    event_add.add_argument("--type", required=True, dest="event_type")
    event_add.add_argument("--headline", required=True)
    event_add.add_argument("--summary", default="")
    event_add.add_argument("--ts-code")
    event_add.add_argument("--name")
    event_add.add_argument("--priority", default="normal")
    event_add.add_argument("--source", default="manual")
    event_add.add_argument("--url", default="")
    event_add.add_argument("--published-at")
    event_add.add_argument("--trade-date")
    event_add.add_argument("--tags", default="")
    event_fetch = event_sub.add_parser("fetch")
    event_fetch.add_argument("--start-date")
    event_fetch.add_argument("--end-date")
    event_fetch_url = event_sub.add_parser("fetch-url")
    event_fetch_url.add_argument("--url", required=True)
    event_fetch_url.add_argument("--type", default="news", dest="event_type")
    event_fetch_url.add_argument("--source", default="url_fetch")
    event_fetch_url.add_argument("--mode", default="auto")
    event_fetch_url.add_argument("--ts-code")
    event_fetch_url.add_argument("--name")
    event_fetch_url.add_argument("--keyword")
    event_fetch_url.add_argument("--trade-date")
    event_fetch_url.add_argument("--priority", default="normal")
    event_fetch_url.add_argument("--limit", type=int, default=20)
    event_fetch_url.add_argument("--items-path", default="")
    event_fetch_url.add_argument("--headline-path", default="")
    event_fetch_url.add_argument("--summary-path", default="")
    event_fetch_url.add_argument("--published-path", default="")
    event_fetch_url.add_argument("--url-path", default="")
    event_fetch_url.add_argument("--include-patterns", default="")
    event_fetch_url.add_argument("--exclude-patterns", default="")
    event_fetch_url.add_argument("--follow-article", action="store_true")
    event_fetch_url.add_argument("--min-headline-length", type=int)
    event_fetch_url.add_argument("--summary-lines", type=int)
    event_fetch_url.add_argument("--ignore-tokens", default="")
    event_fetch_url.add_argument("--drop-patterns", default="")
    event_fetch_url.add_argument("--same-domain-only", action="store_true")
    event_fetch_url.add_argument("--script-markers", default="")
    event_list = event_sub.add_parser("list")
    event_list.add_argument("--trade-date")
    event_list.add_argument("--priority")
    event_list.add_argument("--limit", type=int, default=50)

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

    brief = subparsers.add_parser("brief", help="Generate morning brief")
    brief_sub = brief.add_subparsers(dest="action", required=True)
    brief_generate = brief_sub.add_parser("generate")
    brief_generate.add_argument("--trade-date")
    brief_generate.add_argument("--fetch-events", action="store_true")

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

    schedule = subparsers.add_parser("schedule", help="Run scheduler checks")
    schedule.add_argument("--now", help="Current timestamp, format YYYY-MM-DDTHH:MM")
    schedule.add_argument("--force", action="store_true")
    schedule.add_argument("--dry-run", action="store_true")

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
            _print_json(app.sync_vault(trade_date=args.trade_date, limit=args.limit))
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
        else:
            _print_json(app.export_dashboard_note())
        return 0

    if args.command == "watchlist":
        if args.action == "add":
            _print_json(app.add_watchlist(args.ts_code, name=args.name, notes=args.notes, source=args.source))
        elif args.action == "list":
            _print_json(app.list_watchlist())
        else:
            app.remove_watchlist(args.ts_code)
            print(f"watchlist removed: {args.ts_code}")
        return 0

    if args.command == "keyword":
        if args.action == "add":
            _print_json(app.add_keyword(args.keyword, category=args.category))
        elif args.action == "list":
            _print_json(app.list_keywords())
        else:
            app.remove_keyword(args.keyword)
            print(f"keyword removed: {args.keyword}")
        return 0

    if args.command == "event":
        if args.action == "add":
            _print_json(
                app.add_info_event(
                    event_type=args.event_type,
                    headline=args.headline,
                    summary=args.summary,
                    ts_code=args.ts_code,
                    name=args.name,
                    priority=args.priority,
                    source=args.source,
                    url=args.url,
                    published_at=args.published_at,
                    trade_date=args.trade_date,
                    tags=args.tags,
                )
            )
        elif args.action == "fetch":
            _print_json(app.fetch_watchlist_events(start_date=args.start_date, end_date=args.end_date))
        elif args.action == "fetch-url":
            _print_json(
                app.fetch_url_events(
                    url=args.url,
                    event_type=args.event_type,
                    source=args.source,
                    parser_mode=args.mode,
                    ts_code=args.ts_code,
                    name=args.name,
                    keyword=args.keyword,
                    trade_date=args.trade_date,
                    priority=args.priority,
                    limit=args.limit,
                    items_path=args.items_path,
                    headline_path=args.headline_path,
                    summary_path=args.summary_path,
                    published_path=args.published_path,
                    url_path=args.url_path,
                    include_patterns=args.include_patterns,
                    exclude_patterns=args.exclude_patterns,
                    follow_article=args.follow_article,
                    min_headline_length=args.min_headline_length,
                    summary_lines=args.summary_lines,
                    ignore_tokens=args.ignore_tokens,
                    drop_patterns=args.drop_patterns,
                    same_domain_only=args.same_domain_only,
                    script_markers=args.script_markers,
                )
            )
        else:
            _print_json(app.list_info_events(trade_date=args.trade_date, priority=args.priority, limit=args.limit))
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
            _print_json(
                app.enrich_plan_from_text(
                    args.plan_id,
                    args.text,
                    trade_date=args.trade_date,
                    lookback_days=args.lookback_days,
                )
            )
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

    if args.command == "brief":
        _print_json(app.generate_morning_brief(trade_date=args.trade_date, fetch_events=args.fetch_events))
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
            _print_json(
                app.enrich_trade_from_text(
                    args.trade_id,
                    args.text,
                    trade_date=args.trade_date,
                    lookback_days=args.lookback_days,
                )
            )
        elif args.action == "import-statement":
            _print_json(
                app.import_statement_file(
                    args.file,
                    trade_date=args.trade_date,
                    session_key=args.session_key,
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
            _print_json(
                app.generate_evolution_report(
                    trade_date=args.trade_date,
                    lookback_days=args.lookback_days,
                    min_samples=args.min_samples,
                )
            )
        elif args.action == "portrait":
            _print_json(
                app.generate_style_portrait(
                    trade_date=args.trade_date,
                    lookback_days=args.lookback_days,
                    min_samples=args.min_samples,
                )
            )
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

    if args.command == "schedule":
        _print_json(app.run_schedule(now=args.now, force=args.force, dry_run=args.dry_run))
        return 0

    if args.command == "session":
        if args.action == "turn":
            _print_json(
                app.handle_session_turn(
                    args.session_key,
                    args.text,
                    mode=args.mode,
                    trade_date=args.trade_date,
                    lookback_days=args.lookback_days,
                )
            )
        elif args.action == "state":
            _print_json(app.get_session_state(args.session_key))
        else:
            _print_json(app.reset_session_thread(args.session_key, reason=args.reason))
        return 0

    return 1
