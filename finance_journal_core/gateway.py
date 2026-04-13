from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from .app import create_app


DOMAIN_ALIASES = {
    "watchlist": "watchlist",
    "关注": "watchlist",
    "zixuan": "watchlist",
    "keyword": "keyword",
    "关键词": "keyword",
    "关键字": "keyword",
    "event": "event",
    "事件": "event",
    "news": "event",
    "plan": "plan",
    "计划": "plan",
    "brief": "brief",
    "晨报": "brief",
    "morning": "brief",
    "trade": "trade",
    "交易": "trade",
    "journal": "trade",
    "evolution": "evolution",
    "进化": "evolution",
    "基因": "evolution",
    "轨迹": "evolution",
    "reference": "reference",
    "参考": "reference",
    "review": "review",
    "回顾": "review",
    "report": "report",
    "体检": "report",
    "报告": "report",
    "intake": "intake",
    "记账": "intake",
    "速记": "intake",
    "复盘口述": "intake",
    "session": "session",
    "会话": "session",
    "搭子": "session",
    "vault": "vault",
    "obsidian": "vault",
    "知识库": "vault",
    "笔记库": "vault",
    "schedule": "schedule",
    "调度": "schedule",
}

ACTION_ALIASES = {
    "新增": "add",
    "添加": "add",
    "初始化": "init",
    "创建": "create",
    "新建": "create",
    "列出": "list",
    "列表": "list",
    "查看": "list",
    "删除": "remove",
    "移除": "remove",
    "更新": "status",
    "状态": "status",
    "生成": "generate",
    "抓取": "fetch",
    "抓取网址": "fetch-url",
    "抓网址": "fetch-url",
    "同步": "fetch",
    "记录": "log",
    "开仓": "log",
    "平仓": "close",
    "查询": "query",
    "执行": "run",
    "反馈": "respond",
    "导出": "export",
    "导入": "import-statement",
    "上传": "import-statement",
    "导入交割单": "import-statement",
    "缺失": "incomplete",
    "缺口": "incomplete",
    "补全队列": "incomplete",
    "同步库": "sync",
    "日报": "daily",
    "解析": "parse",
    "落账": "apply",
    "起草": "draft-start",
    "继续": "draft-reply",
    "补充": "draft-reply",
    "当前": "draft-show",
    "完成": "draft-apply",
    "取消": "draft-cancel",
    "提醒": "remind",
    "路径": "report",
    "沉淀": "enrich",
    "画像": "portrait",
    "风格": "portrait",
    "接话": "turn",
    "恢复": "state",
    "重置": "reset",
}

KEY_ALIASES = {
    "code": "ts_code",
    "symbol": "ts_code",
    "标的": "ts_code",
    "股票": "ts_code",
    "name": "name",
    "名称": "name",
    "word": "keyword",
    "关键词": "keyword",
    "category": "category",
    "分类": "category",
    "type": "event_type",
    "事件类型": "event_type",
    "headline": "headline",
    "标题": "headline",
    "summary": "summary",
    "摘要": "summary",
    "priority": "priority",
    "优先级": "priority",
    "source": "source",
    "来源": "source",
    "url": "url",
    "网址": "url",
    "published_at": "published_at",
    "发布时间": "published_at",
    "file": "file",
    "path": "file",
    "filepath": "file",
    "文件": "file",
    "文件路径": "file",
    "交割单": "file",
    "trade_date": "trade_date",
    "日期": "trade_date",
    "direction": "direction",
    "方向": "direction",
    "thesis": "thesis",
    "逻辑": "thesis",
    "logic_tags": "logic_tags",
    "标签": "logic_tags",
    "market_stage": "market_stage",
    "市场阶段": "market_stage",
    "environment_tags": "environment_tags",
    "环境标签": "environment_tags",
    "buy_zone": "buy_zone",
    "买入区间": "buy_zone",
    "sell_zone": "sell_zone",
    "卖出区间": "sell_zone",
    "stop_loss": "stop_loss",
    "止损": "stop_loss",
    "holding_period": "holding_period",
    "持仓周期": "holding_period",
    "valid_from": "valid_from",
    "开始": "valid_from",
    "valid_to": "valid_to",
    "有效期": "valid_to",
    "id": "id",
    "plan_id": "plan_id",
    "trade_id": "trade_id",
    "reason": "reason",
    "buy_date": "buy_date",
    "买入日": "buy_date",
    "buy_price": "buy_price",
    "买价": "buy_price",
    "sell_date": "sell_date",
    "卖出日": "sell_date",
    "sell_price": "sell_price",
    "卖价": "sell_price",
    "sell_reason": "sell_reason",
    "卖出理由": "sell_reason",
    "emotion_notes": "emotion_notes",
    "情绪备注": "emotion_notes",
    "mistake_tags": "mistake_tags",
    "失误标签": "mistake_tags",
    "lessons_learned": "lessons_learned",
    "经验": "lessons_learned",
    "feedback": "feedback",
    "反馈": "feedback",
    "weight_action": "weight_action",
    "权重动作": "weight_action",
    "period_start": "period_start",
    "开始日期": "period_start",
    "period_end": "period_end",
    "结束日期": "period_end",
    "period_kind": "period_kind",
    "周期": "period_kind",
    "lookback_days": "lookback_days",
    "回看天数": "lookback_days",
    "as_of": "as_of_date",
    "截至": "as_of_date",
    "fetch_events": "fetch_events",
    "review_id": "review_id",
    "report_id": "report_id",
    "draft_id": "draft_id",
    "session": "session_key",
    "session_key": "session_key",
    "会话": "session_key",
    "text": "text",
    "raw": "text",
    "note": "text",
    "内容": "text",
    "mode": "mode",
    "limit": "limit",
    "status": "status",
    "logic_tags": "logic_tags",
    "pattern_tags": "pattern_tags",
    "min_samples": "min_samples",
    "mode": "mode",
    "limit": "limit",
    "items_path": "items_path",
    "headline_path": "headline_path",
    "summary_path": "summary_path",
    "published_path": "published_path",
    "url_path": "url_path",
    "include_patterns": "include_patterns",
    "exclude_patterns": "exclude_patterns",
    "follow_article": "follow_article",
}


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance Journal OpenClaw gateway")
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
    if domain == "vault" and len(tokens) > 1 and tokens[1] in {"同步", "sync"}:
        action = "sync"
        kv_tokens = tokens[2:]
    elif domain == "intake" and len(tokens) > 1 and tokens[1] and "=" not in tokens[1]:
        mapped_action = ACTION_ALIASES.get(tokens[1].lower(), ACTION_ALIASES.get(tokens[1], tokens[1]))
        if mapped_action == tokens[1] and len(tokens) >= 2:
            action = "parse"
            kv_tokens = tokens[1:]
        else:
            action = mapped_action
            kv_tokens = tokens[2:]
    elif len(tokens) > 1 and tokens[1] and "=" not in tokens[1]:
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
        normalized_key = KEY_ALIASES.get(key.lower(), KEY_ALIASES.get(key, key))
        params[normalized_key] = value.strip().strip('"').strip("'")
    if domain == "intake" and plain_tokens and "text" not in params:
        params["text"] = " ".join(plain_tokens).strip()
    return domain, action, params


def dispatch(command: str, anchor_path: Path, runtime_root: str | None = None, enable_market_data: bool = True) -> Any:
    app = create_app(anchor_path, runtime_root=runtime_root, enable_market_data=enable_market_data)
    domain, action, params = _split_command(command)

    if domain == "watchlist":
        if action == "add":
            return app.add_watchlist(params["ts_code"], name=params.get("name"), notes=params.get("notes", ""))
        if action == "remove":
            app.remove_watchlist(params["ts_code"])
            return {"removed": params["ts_code"]}
        return app.list_watchlist()

    if domain == "keyword":
        if action == "add":
            return app.add_keyword(params["keyword"], category=params.get("category", "industry"))
        if action == "remove":
            app.remove_keyword(params["keyword"])
            return {"removed": params["keyword"]}
        return app.list_keywords()

    if domain == "event":
        if action == "add":
            return app.add_info_event(
                event_type=params.get("event_type", "manual"),
                headline=params["headline"],
                summary=params.get("summary", ""),
                ts_code=params.get("ts_code"),
                name=params.get("name"),
                priority=params.get("priority", "normal"),
                source=params.get("source", "manual"),
                url=params.get("url", ""),
                published_at=params.get("published_at"),
                trade_date=params.get("trade_date"),
                tags=params.get("tags", ""),
            )
        if action == "fetch":
            return app.fetch_watchlist_events(start_date=params.get("start_date"), end_date=params.get("end_date"))
        if action == "fetch-url":
            return app.fetch_url_events(
                url=params.get("url", ""),
                event_type=params.get("event_type", "news"),
                source=params.get("source", "url_fetch"),
                parser_mode=params.get("mode", "auto"),
                ts_code=params.get("ts_code"),
                name=params.get("name"),
                keyword=params.get("keyword"),
                trade_date=params.get("trade_date"),
                priority=params.get("priority", "normal"),
                limit=int(params.get("limit", 20)),
                items_path=params.get("items_path", ""),
                headline_path=params.get("headline_path", ""),
                summary_path=params.get("summary_path", ""),
                published_path=params.get("published_path", ""),
                url_path=params.get("url_path", ""),
                include_patterns=params.get("include_patterns", ""),
                exclude_patterns=params.get("exclude_patterns", ""),
                follow_article=params.get("follow_article", "false").lower() in {"1", "true", "yes", "y"},
                min_headline_length=int(params["min_headline_length"]) if params.get("min_headline_length") else None,
                summary_lines=int(params["summary_lines"]) if params.get("summary_lines") else None,
                ignore_tokens=params.get("ignore_tokens", ""),
                drop_patterns=params.get("drop_patterns", ""),
                same_domain_only=params.get("same_domain_only", "false").lower() in {"1", "true", "yes", "y"},
                script_markers=params.get("script_markers", ""),
            )
        return app.list_info_events(trade_date=params.get("trade_date"), priority=params.get("priority"), limit=int(params.get("limit", 50)))

    if domain == "intake":
        if action == "turn":
            return app.handle_session_turn(
                params.get("session_key", ""),
                params.get("text", ""),
                mode=params.get("mode", "auto"),
                trade_date=params.get("trade_date"),
                lookback_days=int(params.get("lookback_days", 365)),
            )
        if action == "state":
            return app.get_session_state(params.get("session_key", ""))
        if action == "reset":
            return app.reset_session_thread(params.get("session_key", ""), reason=params.get("reason", ""))
        if params.get("session_key") and action in {"parse", "query", "list"} and params.get("text"):
            return app.handle_session_turn(
                params.get("session_key", ""),
                params.get("text", ""),
                mode=params.get("mode", "auto"),
                trade_date=params.get("trade_date"),
                lookback_days=int(params.get("lookback_days", 365)),
            )
        if action == "apply":
            return app.apply_journal_text(
                params.get("text", ""),
                mode=params.get("mode", "auto"),
                trade_date=params.get("trade_date"),
            )
        if action == "draft-start":
            return app.start_journal_draft(
                params.get("text", ""),
                mode=params.get("mode", "auto"),
                trade_date=params.get("trade_date"),
                session_key=params.get("session_key"),
            )
        if action == "draft-reply":
            target_id = params.get("draft_id") or params.get("id")
            return app.continue_journal_draft(
                target_id,
                params.get("text", ""),
                apply_if_ready=params.get("apply_if_ready", "true").lower() in {"1", "true", "yes", "y"},
                session_key=params.get("session_key"),
            )
        if action == "draft-apply":
            target_id = params.get("draft_id") or params.get("id")
            return app.apply_journal_draft(target_id, session_key=params.get("session_key"))
        if action == "draft-cancel":
            target_id = params.get("draft_id") or params.get("id")
            return app.cancel_journal_draft(target_id, reason=params.get("reason", ""), session_key=params.get("session_key"))
        if action in {"draft-show", "query"}:
            target_id = params.get("draft_id") or params.get("id")
            return app.get_journal_draft(target_id, session_key=params.get("session_key"))
        if action == "draft-list":
            return app.list_journal_drafts(
                status=params.get("status"),
                limit=int(params.get("limit", 20)),
                session_key=params.get("session_key"),
            )
        return app.parse_journal_text(
            params.get("text", ""),
            mode=params.get("mode", "auto"),
            trade_date=params.get("trade_date"),
        )

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
                reminder_time=params.get("reminder_time"),
                notes=params.get("notes"),
                decision_context=json.loads(params["decision_context_json"]) if params.get("decision_context_json") else None,
                with_reference=params.get("with_reference", "false").lower() in {"1", "true", "yes", "y"},
                lookback_days=int(params.get("lookback_days", 365)),
            )
        if action == "status":
            target_id = params.get("plan_id") or params.get("id")
            return app.update_plan_status(target_id, status=params["status"], trade_id=params.get("trade_id"), reason=params.get("reason"))
        if action == "enrich":
            target_id = params.get("plan_id") or params.get("id")
            return app.enrich_plan_from_text(
                target_id,
                params.get("text", ""),
                trade_date=params.get("trade_date"),
                lookback_days=int(params.get("lookback_days", 365)),
            )
        if action in {"query", "reference"}:
            return app.generate_reference(
                logic_tags=params.get("logic_tags", ""),
                market_stage=params.get("market_stage"),
                environment_tags=params.get("environment_tags", ""),
                lookback_days=int(params.get("lookback_days", 365)),
                trade_date=params.get("trade_date"),
                write_artifact=True,
            )
        return app.list_plans(status=params.get("status"), active_only=params.get("active_only", "false").lower() in {"1", "true", "yes", "y"}, trade_date=params.get("trade_date"))

    if domain == "brief":
        return app.generate_morning_brief(trade_date=params.get("trade_date"), fetch_events=params.get("fetch_events", "false").lower() in {"1", "true", "yes", "y"})

    if domain == "trade":
        if action == "import-statement":
            return app.import_statement_file(
                params["file"],
                trade_date=params.get("trade_date"),
                session_key=params.get("session_key"),
            )
        if action == "incomplete":
            return app.build_trade_follow_up_backlog(
                status=params.get("status"),
                limit=int(params.get("limit", 200)),
                trade_date=params.get("trade_date"),
                ts_code=params.get("ts_code"),
                include_complete=params.get("include_complete", "false").lower() in {"1", "true", "yes", "y"},
            )
        if action == "close":
            target_id = params.get("trade_id") or params.get("id")
            return app.close_trade(
                target_id,
                sell_date=params["sell_date"],
                sell_price=float(params["sell_price"]),
                sell_reason=params.get("sell_reason", ""),
                sell_position=params.get("sell_position", ""),
                emotion_notes=params.get("emotion_notes"),
                mistake_tags=params.get("mistake_tags", ""),
                lessons_learned=params.get("lessons_learned"),
                notes=params.get("notes"),
            )
        if action == "enrich":
            target_id = params.get("trade_id") or params.get("id")
            return app.enrich_trade_from_text(
                target_id,
                params.get("text", ""),
                trade_date=params.get("trade_date"),
                lookback_days=int(params.get("lookback_days", 365)),
            )
        if action == "log":
            return app.log_trade(
                ts_code=params["ts_code"],
                name=params.get("name"),
                plan_id=params.get("plan_id"),
                direction=params.get("direction", "long"),
                buy_date=params["buy_date"],
                buy_price=float(params["buy_price"]),
                thesis=params["thesis"],
                buy_reason=params.get("buy_reason", ""),
                buy_position=params.get("buy_position", ""),
                sell_date=params.get("sell_date"),
                sell_price=float(params["sell_price"]) if params.get("sell_price") else None,
                sell_reason=params.get("sell_reason", ""),
                sell_position=params.get("sell_position", ""),
                position_size_pct=float(params["position_size_pct"]) if params.get("position_size_pct") else None,
                logic_type_tags=params.get("logic_type_tags") or params.get("logic_tags", ""),
                pattern_tags=params.get("pattern_tags", ""),
                theme=params.get("theme"),
                market_stage_tag=params.get("market_stage"),
                environment_tags=params.get("environment_tags", ""),
                emotion_notes=params.get("emotion_notes"),
                mistake_tags=params.get("mistake_tags", ""),
                lessons_learned=params.get("lessons_learned"),
                notes=params.get("notes"),
                decision_context=json.loads(params["decision_context_json"]) if params.get("decision_context_json") else None,
                fetch_snapshot=params.get("fetch_snapshot", "false").lower() in {"1", "true", "yes", "y"},
                sector_name=params.get("sector_name"),
                sector_change_pct=float(params["sector_change_pct"]) if params.get("sector_change_pct") else None,
            )
        return app.list_trades(status=params.get("status"), limit=int(params.get("limit", 50)))

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
            return app.generate_style_portrait(
                trade_date=params.get("trade_date"),
                lookback_days=int(params.get("lookback_days", 365)),
                min_samples=int(params.get("min_samples", 2)),
                write_artifact=True,
            )
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
        return app.generate_evolution_report(
            lookback_days=int(params.get("lookback_days", 365)),
            trade_date=params.get("trade_date"),
            min_samples=int(params.get("min_samples", 2)),
            write_artifact=True,
        )

    if domain == "review":
        if action == "run":
            return app.run_review_cycle(as_of_date=params.get("as_of_date") or params.get("trade_date"))
        if action == "respond":
            target_id = params.get("review_id") or params.get("id")
            return app.respond_review(target_id, feedback=params["feedback"], weight_action=params.get("weight_action", ""))
        return app.list_reviews(status=params.get("status"), limit=int(params.get("limit", 50)))

    if domain == "report":
        return app.generate_health_report(params["period_start"], params["period_end"], period_kind=params.get("period_kind", "custom"))

    if domain == "vault":
        if action == "init":
            return app.init_vault()
        if action == "sync":
            return app.sync_vault(trade_date=params.get("trade_date"), limit=int(params.get("limit", 200)))
        if action in {"daily", "generate"}:
            return app.export_daily_note(params["trade_date"])
        if action == "plan":
            return app.export_plan_note(params.get("plan_id") or params.get("id"))
        if action == "trade":
            return app.export_trade_note(params.get("trade_id") or params.get("id"))
        if action == "review":
            return app.export_review_note(params.get("review_id") or params.get("id"))
        if action == "report":
            return app.export_report_note(params.get("report_id") or params.get("id"))
        return app.export_dashboard_note()

    if domain == "schedule":
        return app.run_schedule(
            now=params.get("now"),
            force=params.get("force", "false").lower() in {"1", "true", "yes", "y"},
            dry_run=params.get("dry_run", "false").lower() in {"1", "true", "yes", "y"},
        )

    raise ValueError(f"unsupported domain: {domain}")


def main(argv: list[str] | None = None, anchor_path: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if anchor_path is None:
        anchor_path = Path(__file__).resolve()
    payload = dispatch(args.command, anchor_path=anchor_path, runtime_root=args.root, enable_market_data=not args.disable_market_data)
    _print(payload)
    return 0
