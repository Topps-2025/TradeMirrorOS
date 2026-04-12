from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .analytics import (
    build_style_portrait,
    build_reference_report,
    build_evolution_reminder,
    build_evolution_report,
    calculate_plan_execution_deviation,
    compute_return_pct,
    generate_health_report_payload,
    split_tags,
)
from .config import load_runtime_config
from .intake import (
    build_polling_bundle,
    build_reflection_prompts,
    build_standardized_record,
    evaluate_journal_fields,
    extract_field_value,
    parse_freeform_journal,
)
from .market_data import (
    TushareMarketData,
    normalize_datetime_text,
    normalize_trade_date,
    normalize_ts_code,
    shift_calendar_date,
    to_date,
)
from .storage import FinanceJournalDB, ensure_runtime_dirs, json_dumps, json_loads, make_id, now_ts, safe_filename
from .url_sources import UrlEventFetcher
from .vault import (
    ensure_vault_dirs,
    file_stem,
    render_daily_note,
    render_dashboard_note,
    render_health_report_note,
    render_plan_note,
    render_review_note,
    render_trade_note,
)


def _coalesce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FinanceJournalApp:
    def __init__(
        self,
        repo_root: Path,
        skill_root: Path,
        runtime_root: str | None = None,
        enable_market_data: bool = True,
        token: str | None = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.skill_root = Path(skill_root).resolve()
        self.config = load_runtime_config(self.repo_root, self.skill_root, runtime_root=runtime_root)
        ensure_runtime_dirs(self.config)
        self.db = FinanceJournalDB(self.config["db_path"])
        self.db.init_schema()
        self.url_fetcher = UrlEventFetcher(config=self.config.get("url_sources", {}))
        self.market = None
        if enable_market_data and self.config.get("tushare", {}).get("enabled", True):
            self.market = TushareMarketData(token=token)

    def init_runtime(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        self.db.init_schema()
        vault_info = self.init_vault()
        return {
            "runtime_root": str(self.config["runtime_root"]),
            "db_path": str(self.config["db_path"]),
            "artifacts_dir": str(self.config["artifacts_dir"]),
            "memory_dir": str(self.config["memory_dir"]),
            "status_dir": str(self.config["status_dir"]),
            "vault_root": vault_info["vault_root"],
        }

    def init_vault(self) -> dict[str, Any]:
        vault_root = Path(self.config["vault_root"])
        dirs = ensure_vault_dirs(vault_root)
        return {
            "vault_root": str(vault_root),
            "folders": {key: str(path) for key, path in dirs.items()},
        }

    def _today(self) -> str:
        return datetime.now().strftime("%Y%m%d")

    def _daily_dir(self, trade_date: str | None = None) -> Path:
        token = normalize_trade_date(trade_date or self._today())
        path = self.config["artifacts_dir"] / "daily" / token
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_artifact(self, trade_date: str, stem: str, payload: dict[str, Any], markdown: str | None = None) -> dict[str, str]:
        directory = self._daily_dir(trade_date)
        json_path = directory / f"{safe_filename(stem)}.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        paths = {"json": str(json_path)}
        if markdown is not None:
            md_path = directory / f"{safe_filename(stem)}.md"
            md_path.write_text(markdown, encoding="utf-8")
            paths["markdown"] = str(md_path)
        return paths

    def _vault_enabled(self) -> bool:
        return bool(self.config.get("vault", {}).get("enabled", True))

    def _vault_write(self, bucket: str, stem: str, markdown: str) -> str:
        dirs = ensure_vault_dirs(Path(self.config["vault_root"]))
        target = dirs[bucket] / f"{safe_filename(stem)}.md"
        target.write_text(markdown, encoding="utf-8")
        return str(target)

    def _recent_health_reports(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "SELECT report_id, period_kind, period_start, period_end, created_at FROM health_reports ORDER BY period_end DESC, created_at DESC LIMIT ?",
            (int(limit),),
        )

    def export_dashboard_note(self) -> dict[str, Any]:
        if not self._vault_enabled():
            return {"enabled": False}
        markdown = render_dashboard_note(self.list_trades(limit=20), self._recent_health_reports(limit=12))
        path = self._vault_write("dashboard", "trade_journal_dashboard", markdown)
        return {"path": path}

    def export_plan_note(self, plan_id: str) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"plan not found: {plan_id}")
        markdown = render_plan_note(plan)
        stem = file_stem("plan", plan.get("valid_from") or "", plan.get("ts_code") or "", plan.get("name") or "", plan_id)
        path = self._vault_write("plans", stem, markdown)
        return {"path": path, "plan_id": plan_id}

    def export_trade_note(self, trade_id: str) -> dict[str, Any]:
        trade = self.get_trade(trade_id)
        if not trade:
            raise ValueError(f"trade not found: {trade_id}")
        plan = self.get_plan(trade.get("plan_id")) if trade.get("plan_id") else None
        reviews = self.db.fetchall("SELECT * FROM reviews WHERE trade_id = ? ORDER BY review_due_date ASC", (trade_id,))
        markdown = render_trade_note(trade, plan=plan, review_rows=reviews)
        stem = file_stem("trade", trade.get("buy_date") or "", trade.get("ts_code") or "", trade.get("name") or "", trade_id)
        path = self._vault_write("trades", stem, markdown)
        return {"path": path, "trade_id": trade_id}

    def export_review_note(self, review_id: str) -> dict[str, Any]:
        review = self.db.fetchone("SELECT * FROM reviews WHERE review_id = ?", (review_id,))
        if not review:
            raise ValueError(f"review not found: {review_id}")
        trade = self.get_trade(review["trade_id"])
        markdown = render_review_note(review, trade=trade)
        stem = file_stem("review", review.get("review_due_date") or "", review.get("ts_code") or "", review_id)
        path = self._vault_write("reviews", stem, markdown)
        return {"path": path, "review_id": review_id}

    def export_report_note(self, report_id: str) -> dict[str, Any]:
        row = self.db.fetchone(
            "SELECT report_id, period_kind, period_start, period_end, report_markdown, report_json, created_at FROM health_reports WHERE report_id = ?",
            (report_id,),
        )
        if not row:
            raise ValueError(f"report not found: {report_id}")
        payload = json.loads(row["report_json"])
        payload["report_id"] = row["report_id"]
        payload["period_kind"] = row["period_kind"]
        payload["period_start"] = row["period_start"]
        payload["period_end"] = row["period_end"]
        payload["markdown"] = row["report_markdown"]
        markdown = render_health_report_note(payload)
        stem = file_stem("health", row.get("period_kind") or "", row.get("period_end") or "", row["report_id"])
        path = self._vault_write("reports", stem, markdown)
        return {"path": path, "report_id": report_id}

    def export_daily_note(self, trade_date: str) -> dict[str, Any]:
        token = normalize_trade_date(trade_date)
        plans = self.db.fetchall(
            "SELECT * FROM plans WHERE valid_from <= ? AND valid_to >= ? ORDER BY created_at DESC",
            (token, token),
        )
        trades = self.db.fetchall(
            "SELECT * FROM trades WHERE buy_date = ? OR sell_date = ? ORDER BY updated_at DESC",
            (token, token),
        )
        reviews = self.db.fetchall(
            "SELECT * FROM reviews WHERE review_due_date = ? OR sell_date = ? ORDER BY updated_at DESC",
            (token, token),
        )
        events = self.list_info_events(trade_date=token, limit=20)
        markdown = render_daily_note(token, plans, trades, reviews, events)
        stem = file_stem("daily", token, "review")
        path = self._vault_write("daily", stem, markdown)
        return {"path": path, "trade_date": token}

    def sync_vault(self, trade_date: str | None = None, limit: int = 200) -> dict[str, Any]:
        if not self._vault_enabled():
            return {"enabled": False, "paths": []}
        self.init_vault()
        paths: list[str] = []
        for plan in self.db.fetchall("SELECT plan_id FROM plans ORDER BY updated_at DESC LIMIT ?", (int(limit),)):
            paths.append(self.export_plan_note(plan["plan_id"])["path"])
        for trade in self.db.fetchall("SELECT trade_id FROM trades ORDER BY updated_at DESC LIMIT ?", (int(limit),)):
            paths.append(self.export_trade_note(trade["trade_id"])["path"])
        for review in self.db.fetchall("SELECT review_id FROM reviews ORDER BY updated_at DESC LIMIT ?", (int(limit),)):
            paths.append(self.export_review_note(review["review_id"])["path"])
        for report in self._recent_health_reports(limit=limit):
            paths.append(self.export_report_note(report["report_id"])["path"])
        if trade_date:
            paths.append(self.export_daily_note(trade_date)["path"])
        paths.append(self.export_dashboard_note()["path"])
        return {"enabled": True, "paths": paths}

    def _resolve_name(self, ts_code: str, name: str | None = None) -> str:
        if name:
            return str(name).strip()
        if not self.market:
            return ts_code
        resolved = self.market.resolve_stock(ts_code)
        return str(resolved.get("name") or ts_code)

    def _soft_trade_day(self, trade_date: str | None = None) -> str:
        token = normalize_trade_date(trade_date or self._today())
        if not self.market:
            return token
        try:
            if self.market.is_trade_day(token):
                return token
            return self.market.previous_trade_date(token, 1, inclusive=False)
        except Exception:
            return token

    def _symbol_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for row in self.list_watchlist(active_only=False):
            code = row.get("ts_code") or ""
            name = row.get("name") or ""
            if code:
                index[code] = name or code
            if name and code:
                index[name] = code
        for row in self.db.fetchall("SELECT ts_code, name FROM plans ORDER BY updated_at DESC LIMIT 500"):
            code = row.get("ts_code") or ""
            name = row.get("name") or ""
            if code and code not in index:
                index[code] = name or code
            if name and code and name not in index:
                index[name] = code
        for row in self.db.fetchall("SELECT ts_code, name FROM trades ORDER BY updated_at DESC LIMIT 500"):
            code = row.get("ts_code") or ""
            name = row.get("name") or ""
            if code and code not in index:
                index[code] = name or code
            if name and code and name not in index:
                index[name] = code
        return index

    def parse_journal_text(self, text: str, mode: str = "auto", trade_date: str | None = None) -> dict[str, Any]:
        payload = parse_freeform_journal(
            text,
            symbol_index=self._symbol_index(),
            preferred_mode=mode,
            anchor_date=normalize_trade_date(trade_date or self._today()),
        )
        if not payload["fields"].get("ts_code") and self.market:
            for candidate in sorted(set(re.findall(r"[\u4e00-\u9fff]{2,8}", text or "")), key=len, reverse=True):
                try:
                    resolved = self.market.resolve_stock(candidate)
                except Exception:
                    continue
                payload["fields"]["ts_code"] = resolved.get("ts_code") or ""
                payload["fields"]["name"] = resolved.get("name") or candidate
                if "ts_code" in payload["missing_fields"]:
                    payload["missing_fields"] = [item for item in payload["missing_fields"] if item != "ts_code"]
                    payload["follow_up_questions"] = [
                        item for item in payload["follow_up_questions"] if "股票" not in item and "代码" not in item
                    ]
                    payload["action_ready"] = not payload["missing_fields"]
                break
        evaluation = evaluate_journal_fields(payload.get("fields") or {}, payload.get("journal_kind") or "open_trade")
        payload["required_fields"] = evaluation["required_fields"]
        payload["missing_fields"] = evaluation["missing_fields"]
        payload["follow_up_questions"] = evaluation["follow_up_questions"]
        payload["action_ready"] = evaluation["action_ready"]
        payload["suggested_command"] = evaluation["suggested_command"]
        payload["standardized_record"] = build_standardized_record(payload["fields"], payload["journal_kind"])
        reflection_prompts = build_reflection_prompts(
            payload["fields"],
            payload["journal_kind"],
            evaluation["missing_fields"],
        )
        payload["reflection_prompts"] = reflection_prompts
        payload["polling_bundle"] = build_polling_bundle(
            payload["fields"],
            payload["journal_kind"],
            evaluation["missing_fields"],
            evaluation["follow_up_questions"],
            reflection_prompts=reflection_prompts,
        )
        return payload

    def _merge_unique_tags(self, *values: Any) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            for tag in split_tags(value):
                if tag in seen:
                    continue
                seen.add(tag)
                merged.append(tag)
        return merged

    def _merge_unique_items(self, *values: Any) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in (None, ""):
                continue
            items = value if isinstance(value, (list, tuple, set)) else [value]
            for item in items:
                text = str(item or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                merged.append(text)
        return merged

    def _append_text_block(self, existing: Any, addition: Any) -> str:
        blocks: list[str] = []
        for item in (existing, addition):
            text = str(item or "").strip()
            if text and text not in blocks:
                blocks.append(text)
        return "\n".join(blocks)

    def _decision_context_from_fields(
        self,
        fields: dict[str, Any],
        journal_kind: str,
        base_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = dict(base_context or {})
        context["capture_mode"] = "user_view_slice"
        context["journal_kind"] = journal_kind
        primary_symbol = {
            "ts_code": fields.get("ts_code") or "",
            "name": fields.get("name") or "",
        }
        if primary_symbol["ts_code"] or primary_symbol["name"]:
            context["primary_symbol"] = primary_symbol
        focus_seed = []
        if fields.get("name"):
            focus_seed.append(fields.get("name"))
        elif fields.get("ts_code"):
            focus_seed.append(fields.get("ts_code"))
        context["user_focus"] = self._merge_unique_items(
            context.get("user_focus", []),
            focus_seed,
            fields.get("user_focus", []),
        )
        context["observed_signals"] = self._merge_unique_items(
            context.get("observed_signals", []),
            fields.get("observed_signals", []),
        )
        context["interpretation"] = str(context.get("interpretation") or fields.get("thesis") or "").strip()
        context["position_reason"] = self._append_text_block(context.get("position_reason"), fields.get("position_reason"))
        if fields.get("position_confidence") not in (None, ""):
            context["position_confidence"] = fields.get("position_confidence")
        elif context.get("position_confidence") in ("", None):
            context.pop("position_confidence", None)
        if fields.get("stress_level") not in (None, ""):
            context["stress_level"] = fields.get("stress_level")
        elif context.get("stress_level") in ("", None):
            context.pop("stress_level", None)
        if fields.get("position_size_pct") not in (None, ""):
            context["position_size_pct"] = fields.get("position_size_pct")
        elif context.get("position_size_pct") in ("", None):
            context.pop("position_size_pct", None)
        context["emotion_notes"] = self._append_text_block(context.get("emotion_notes"), fields.get("emotion_notes"))
        context["mistake_tags"] = self._merge_unique_tags(context.get("mistake_tags", []), fields.get("mistake_tags", []))
        context["environment_tags"] = self._merge_unique_tags(context.get("environment_tags", []), fields.get("environment_tags", []))
        market_stage = self._pick_market_stage(fields.get("environment_tags"), fallback=context.get("market_stage") or "")
        if market_stage:
            context["market_stage"] = market_stage
        else:
            context.pop("market_stage", None)
        if fields.get("stop_loss"):
            context["risk_boundary"] = str(fields.get("stop_loss") or "")
        if fields.get("buy_zone") or fields.get("sell_zone"):
            context["planned_zone"] = {
                "buy_zone": str(fields.get("buy_zone") or ""),
                "sell_zone": str(fields.get("sell_zone") or ""),
            }
        if fields.get("notes"):
            context["source_notes"] = self._append_text_block(context.get("source_notes"), fields.get("notes"))
        return {key: value for key, value in context.items() if value not in (None, "", [], {})}

    def _apply_decision_context_to_fields(self, fields: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(fields)
        ctx = dict(context or {})
        payload["user_focus"] = self._merge_unique_items(payload.get("user_focus", []), ctx.get("user_focus", []))
        payload["observed_signals"] = self._merge_unique_items(payload.get("observed_signals", []), ctx.get("observed_signals", []))
        payload["position_reason"] = self._append_text_block(payload.get("position_reason"), ctx.get("position_reason"))
        if payload.get("position_confidence") in (None, "") and ctx.get("position_confidence") not in (None, ""):
            payload["position_confidence"] = ctx.get("position_confidence")
        if payload.get("stress_level") in (None, "") and ctx.get("stress_level") not in (None, ""):
            payload["stress_level"] = ctx.get("stress_level")
        if payload.get("position_size_pct") in (None, "") and ctx.get("position_size_pct") not in (None, ""):
            payload["position_size_pct"] = ctx.get("position_size_pct")
        if not payload.get("emotion_notes") and ctx.get("emotion_notes"):
            payload["emotion_notes"] = ctx.get("emotion_notes")
        payload["mistake_tags"] = self._merge_unique_tags(payload.get("mistake_tags", []), ctx.get("mistake_tags", []))
        payload["environment_tags"] = self._merge_unique_tags(payload.get("environment_tags", []), ctx.get("environment_tags", []))
        if not payload.get("thesis") and ctx.get("interpretation"):
            payload["thesis"] = ctx.get("interpretation")
        return payload

    def _journal_kind_from_fields(self, mode: str, fields: dict[str, Any]) -> str:
        if mode == "plan":
            return "plan"
        has_buy = fields.get("buy_price") is not None
        has_sell = fields.get("sell_price") is not None
        if has_buy and has_sell:
            return "closed_trade"
        if has_sell and not has_buy:
            return "close_only"
        return "open_trade"

    def _pick_market_stage(self, environment_tags: list[str] | str | None, fallback: str = "") -> str:
        for tag in split_tags(environment_tags):
            if tag.endswith("市") or "分歧" in tag or "主升" in tag or "冰点" in tag or "下跌" in tag or "上涨" in tag:
                return tag
        return str(fallback or "").strip()

    def _plan_to_journal_fields(self, plan: dict[str, Any]) -> dict[str, Any]:
        fields = {
            "ts_code": plan.get("ts_code") or "",
            "name": plan.get("name") or "",
            "direction": plan.get("direction") or "buy",
            "thesis": plan.get("thesis") or "",
            "logic_tags": split_tags(json_loads(plan.get("logic_tags_json"), [])),
            "pattern_tags": [],
            "environment_tags": split_tags(json_loads(plan.get("environment_tags_json"), [])),
            "user_focus": [],
            "observed_signals": [],
            "position_reason": "",
            "position_confidence": None,
            "stress_level": None,
            "mistake_tags": [],
            "emotion_notes": "",
            "lessons_learned": "",
            "position_size_pct": None,
            "buy_date": plan.get("valid_from") or "",
            "sell_date": "",
            "buy_price": None,
            "sell_price": None,
            "buy_zone": plan.get("buy_zone") or "",
            "sell_zone": plan.get("sell_zone") or "",
            "stop_loss": plan.get("stop_loss") or "",
            "holding_period": plan.get("holding_period") or "",
            "valid_from": plan.get("valid_from") or "",
            "valid_to": plan.get("valid_to") or "",
            "notes": plan.get("notes") or "",
        }
        return self._apply_decision_context_to_fields(fields, json_loads(plan.get("decision_context_json"), {}) or {})

    def _trade_to_journal_fields(self, trade: dict[str, Any]) -> dict[str, Any]:
        fields = {
            "ts_code": trade.get("ts_code") or "",
            "name": trade.get("name") or "",
            "direction": trade.get("direction") or "long",
            "thesis": trade.get("thesis") or "",
            "logic_tags": split_tags(json_loads(trade.get("logic_type_tags_json"), [])),
            "pattern_tags": split_tags(json_loads(trade.get("pattern_tags_json"), [])),
            "environment_tags": split_tags(json_loads(trade.get("environment_tags_json"), [])),
            "user_focus": [],
            "observed_signals": [],
            "position_reason": "",
            "position_confidence": None,
            "stress_level": None,
            "mistake_tags": split_tags(json_loads(trade.get("mistake_tags_json"), [])),
            "emotion_notes": trade.get("emotion_notes") or "",
            "lessons_learned": trade.get("lessons_learned") or "",
            "position_size_pct": trade.get("position_size_pct"),
            "buy_date": trade.get("buy_date") or "",
            "sell_date": trade.get("sell_date") or "",
            "buy_price": trade.get("buy_price"),
            "sell_price": trade.get("sell_price"),
            "buy_zone": "",
            "sell_zone": "",
            "stop_loss": "",
            "holding_period": "",
            "valid_from": trade.get("buy_date") or "",
            "valid_to": trade.get("sell_date") or "",
            "notes": trade.get("notes") or "",
        }
        return self._apply_decision_context_to_fields(fields, json_loads(trade.get("decision_context_json"), {}) or {})

    def _changed_field_names(self, before_fields: dict[str, Any], after_fields: dict[str, Any], candidates: list[str]) -> list[str]:
        changed: list[str] = []
        for key in candidates:
            before = before_fields.get(key)
            after = after_fields.get(key)
            if before == after:
                continue
            changed.append(key)
        return changed

    def _normalize_session_key(self, session_key: str | None) -> str:
        token = str(session_key or "").strip()
        if not token:
            raise ValueError("session_key is required")
        return token

    def _decode_session_thread(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        payload = dict(row)
        payload["memory"] = json_loads(row.get("memory_json"), {}) or {}
        payload["last_result"] = json_loads(row.get("last_result_json"), {}) or {}
        payload.pop("memory_json", None)
        payload.pop("last_result_json", None)
        return payload

    def _upsert_session_thread(
        self,
        session_key: str,
        *,
        active_draft_id: str = "",
        active_entity_kind: str = "",
        active_entity_id: str = "",
        active_mode: str = "auto",
        trade_date: str = "",
        status: str = "active",
        memory: dict[str, Any] | None = None,
        last_user_text: str = "",
        last_assistant_text: str = "",
        last_route: str = "",
        last_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._normalize_session_key(session_key)
        now = now_ts()
        current = self.get_session_thread(token)
        created_at = (current or {}).get("created_at") or now
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO session_threads(
                    session_key, active_draft_id, active_entity_kind, active_entity_id, active_mode, trade_date,
                    status, memory_json, last_user_text, last_assistant_text, last_route, last_result_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    active_draft_id=excluded.active_draft_id,
                    active_entity_kind=excluded.active_entity_kind,
                    active_entity_id=excluded.active_entity_id,
                    active_mode=excluded.active_mode,
                    trade_date=excluded.trade_date,
                    status=excluded.status,
                    memory_json=excluded.memory_json,
                    last_user_text=excluded.last_user_text,
                    last_assistant_text=excluded.last_assistant_text,
                    last_route=excluded.last_route,
                    last_result_json=excluded.last_result_json,
                    updated_at=excluded.updated_at
                """,
                (
                    token,
                    active_draft_id,
                    active_entity_kind,
                    active_entity_id,
                    active_mode,
                    trade_date,
                    status,
                    json_dumps(memory or {}),
                    last_user_text,
                    last_assistant_text,
                    last_route,
                    json_dumps(last_result or {}),
                    created_at,
                    now,
                ),
            )
        return self.get_session_thread(token) or {}

    def get_session_thread(self, session_key: str | None) -> dict[str, Any] | None:
        token = self._normalize_session_key(session_key)
        return self._decode_session_thread(
            self.db.fetchone("SELECT * FROM session_threads WHERE session_key = ?", (token,))
        )

    def _entity_summary(self, entity_kind: str, entity_id: str) -> str:
        if entity_kind == "trade":
            trade = self.get_trade(entity_id) or {}
            if trade:
                return f"最近聚焦交易：{trade.get('name') or trade.get('ts_code')} | 逻辑={trade.get('thesis') or '-'}"
        if entity_kind == "plan":
            plan = self.get_plan(entity_id) or {}
            if plan:
                return f"最近聚焦计划：{plan.get('name') or plan.get('ts_code')} | 逻辑={plan.get('thesis') or '-'}"
        return ""

    def _pending_question_from_result(self, payload: dict[str, Any] | None) -> str:
        result = dict(payload or {})
        stack: list[Any] = [
            result,
            result.get("draft"),
            result.get("result"),
            result.get("follow_up"),
        ]
        items = result.get("items")
        if isinstance(items, list):
            stack.extend(item.get("follow_up") for item in items if isinstance(item, dict))
        for item in stack:
            if not isinstance(item, dict):
                continue
            polling_bundle = item.get("polling_bundle")
            if isinstance(polling_bundle, dict):
                next_question = str(polling_bundle.get("next_question") or "").strip()
                if next_question:
                    return next_question
            follow_up_questions = item.get("follow_up_questions")
            if isinstance(follow_up_questions, list):
                for candidate in follow_up_questions:
                    text = str(candidate or "").strip()
                    if text:
                        return text
            reflection_prompts = item.get("reflection_prompts")
            if isinstance(reflection_prompts, list):
                for candidate in reflection_prompts:
                    if isinstance(candidate, dict):
                        text = str(candidate.get("question") or "").strip()
                    else:
                        text = str(candidate or "").strip()
                    if text:
                        return text
        return ""

    def _build_session_state_payload(self, session_key: str) -> dict[str, Any]:
        thread = self.get_session_thread(session_key) or {}
        active_draft = None
        if thread.get("active_draft_id"):
            active_draft = self.get_journal_draft(thread.get("active_draft_id"))
        entity_summary = self._entity_summary(thread.get("active_entity_kind") or "", thread.get("active_entity_id") or "")
        pending_question = (active_draft or {}).get("next_question") or self._pending_question_from_result(thread.get("last_result"))
        return {
            "session_key": thread.get("session_key") or self._normalize_session_key(session_key),
            "status": thread.get("status") or "active",
            "active_mode": thread.get("active_mode") or "auto",
            "trade_date": thread.get("trade_date") or "",
            "active_draft_id": thread.get("active_draft_id") or "",
            "active_entity_kind": thread.get("active_entity_kind") or "",
            "active_entity_id": thread.get("active_entity_id") or "",
            "pending_question": pending_question,
            "entity_summary": entity_summary,
            "last_route": thread.get("last_route") or "",
            "last_assistant_text": thread.get("last_assistant_text") or "",
        }

    def _normalized_session_memory(self, memory: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(memory or {})
        shared_contexts = payload.get("shared_contexts")
        if not isinstance(shared_contexts, dict):
            shared_contexts = {}
        for scope_name in ("trade_dates", "symbols", "strategies"):
            scope_payload = shared_contexts.get(scope_name)
            if not isinstance(scope_payload, dict):
                shared_contexts[scope_name] = {}
        payload["shared_contexts"] = shared_contexts
        return payload

    def _generic_trade_date_signals(self, values: Any) -> list[str]:
        generic_hints = ("板块", "大盘", "指数", "市场", "情绪", "量能", "回流", "分歧", "修复", "风险")
        signals = self._merge_unique_items(values)
        return [item for item in signals if any(hint in item for hint in generic_hints)]

    def _has_strong_thesis_text(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.lower()
        thesis_hints = (
            "逻辑",
            "因为",
            "博弈",
            "回流",
            "修复",
            "低吸",
            "突破",
            "题材",
            "趋势",
            "反弹",
            "首阴",
            "基本面",
            "业绩",
            "均线",
            "分歧",
            "cpo",
            "ai",
            "股息",
        )
        return any(hint in lowered for hint in thesis_hints)

    def _focused_symbol_context(self, entity_kind: str, entity_id: str, trade_date: str) -> dict[str, str]:
        if not entity_id or entity_kind not in {"plan", "trade"}:
            return {}
        if entity_kind == "plan":
            row = self.get_plan(entity_id) or {}
            row_date = normalize_trade_date(row.get("valid_from") or trade_date)
        else:
            row = self.get_trade(entity_id) or {}
            row_date = normalize_trade_date(row.get("buy_date") or trade_date)
        if not row or row_date != normalize_trade_date(trade_date):
            return {}
        ts_code = str(row.get("ts_code") or "").strip()
        if not ts_code:
            return {}
        return {
            "ts_code": ts_code,
            "name": str(row.get("name") or "").strip(),
        }

    def _session_reuse_summary(self, reuse_items: list[dict[str, Any]] | None) -> str:
        scope_labels = {
            "trade_date": "同日环境",
            "symbol": "同票主线",
            "focused_symbol": "当前聚焦标的",
            "strategy": "同策略条线",
        }
        labels: list[str] = []
        for item in reuse_items or []:
            label = scope_labels.get(str(item.get("scope") or ""), "")
            if label and label not in labels:
                labels.append(label)
        if not labels:
            return ""
        return f"已自动复用{'、'.join(labels)}。"

    def _update_session_memory_from_fields(
        self,
        memory: dict[str, Any] | None,
        fields: dict[str, Any] | None,
        *,
        trade_date: str,
        journal_kind: str = "",
    ) -> dict[str, Any]:
        payload = self._normalized_session_memory(memory)
        if journal_kind:
            payload["last_journal_kind"] = journal_kind
        if not fields:
            return payload

        shared_contexts = payload["shared_contexts"]
        trade_date_token = normalize_trade_date(trade_date)
        day_context = dict(shared_contexts["trade_dates"].get(trade_date_token) or {})
        env_tags = self._merge_unique_tags(day_context.get("environment_tags", []), fields.get("environment_tags", []))
        if env_tags:
            day_context["environment_tags"] = env_tags
            market_stage = self._pick_market_stage(env_tags, fallback=day_context.get("market_stage") or "")
            if market_stage:
                day_context["market_stage"] = market_stage
        generic_signals = self._merge_unique_items(
            day_context.get("observed_signals", []),
            self._generic_trade_date_signals(fields.get("observed_signals", [])),
        )
        if generic_signals:
            day_context["observed_signals"] = generic_signals
        if day_context:
            shared_contexts["trade_dates"][trade_date_token] = day_context

        ts_code = str(fields.get("ts_code") or "").strip()
        if ts_code:
            symbol_context = dict(shared_contexts["symbols"].get(ts_code) or {})
            if fields.get("name"):
                symbol_context["name"] = str(fields.get("name") or "").strip()
            if fields.get("thesis"):
                symbol_context["thesis"] = str(fields.get("thesis") or "").strip()
            logic_tags = self._merge_unique_tags(symbol_context.get("logic_tags", []), fields.get("logic_tags", []))
            pattern_tags = self._merge_unique_tags(symbol_context.get("pattern_tags", []), fields.get("pattern_tags", []))
            user_focus = self._merge_unique_items(symbol_context.get("user_focus", []), fields.get("user_focus", []))
            if logic_tags:
                symbol_context["logic_tags"] = logic_tags
            if pattern_tags:
                symbol_context["pattern_tags"] = pattern_tags
            if user_focus:
                symbol_context["user_focus"] = user_focus
            symbol_context["trade_date"] = trade_date_token
            shared_contexts["symbols"][ts_code] = symbol_context
            payload["last_symbol"] = {
                "ts_code": ts_code,
                "name": str(fields.get("name") or symbol_context.get("name") or "").strip(),
                "trade_date": trade_date_token,
            }
        return payload

    def _apply_session_memory_to_fields(
        self,
        fields: dict[str, Any],
        *,
        trade_date: str,
        journal_kind: str,
        memory: dict[str, Any] | None = None,
        focused_symbol: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        merged = dict(fields)
        reuse_items: list[dict[str, Any]] = []
        payload = self._normalized_session_memory(memory)

        if not merged.get("ts_code") and focused_symbol and focused_symbol.get("ts_code"):
            merged["ts_code"] = focused_symbol.get("ts_code") or ""
            if focused_symbol.get("name"):
                merged["name"] = focused_symbol.get("name") or ""
            reuse_items.append(
                {
                    "scope": "focused_symbol",
                    "fields": ["ts_code"] + (["name"] if focused_symbol.get("name") else []),
                }
            )

        trade_date_token = normalize_trade_date(trade_date)
        shared_contexts = payload["shared_contexts"]
        day_context = dict(shared_contexts["trade_dates"].get(trade_date_token) or {})
        applied_day_fields: list[str] = []
        if not split_tags(merged.get("environment_tags")) and split_tags(day_context.get("environment_tags", [])):
            merged["environment_tags"] = split_tags(day_context.get("environment_tags", []))
            applied_day_fields.append("environment_tags")
        if not merged.get("observed_signals") and day_context.get("observed_signals"):
            merged["observed_signals"] = self._merge_unique_items(day_context.get("observed_signals", []))
            applied_day_fields.append("observed_signals")
        if applied_day_fields:
            reuse_items.append({"scope": "trade_date", "fields": applied_day_fields})

        ts_code = str(merged.get("ts_code") or "").strip()
        symbol_context = dict(shared_contexts["symbols"].get(ts_code) or {}) if ts_code else {}
        applied_symbol_fields: list[str] = []
        if ts_code and symbol_context.get("trade_date") == trade_date_token:
            if not merged.get("name") and symbol_context.get("name"):
                merged["name"] = str(symbol_context.get("name") or "").strip()
                applied_symbol_fields.append("name")
            if (
                journal_kind in {"plan", "open_trade", "closed_trade"}
                and not self._has_strong_thesis_text(merged.get("thesis"))
                and symbol_context.get("thesis")
            ):
                merged["thesis"] = str(symbol_context.get("thesis") or "").strip()
                applied_symbol_fields.append("thesis")
            if not merged.get("logic_tags") and symbol_context.get("logic_tags"):
                merged["logic_tags"] = split_tags(symbol_context.get("logic_tags", []))
                applied_symbol_fields.append("logic_tags")
            if not merged.get("pattern_tags") and symbol_context.get("pattern_tags"):
                merged["pattern_tags"] = split_tags(symbol_context.get("pattern_tags", []))
                applied_symbol_fields.append("pattern_tags")
            if not merged.get("user_focus") and symbol_context.get("user_focus"):
                merged["user_focus"] = self._merge_unique_items(symbol_context.get("user_focus", []))
                applied_symbol_fields.append("user_focus")
        if applied_symbol_fields:
            reuse_items.append({"scope": "symbol", "fields": applied_symbol_fields})
        return merged, reuse_items

    def _refresh_parsed_payload(
        self,
        payload: dict[str, Any],
        *,
        mode: str,
        fields: dict[str, Any],
        trade_date: str,
        session_reuse: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        refreshed = dict(payload)
        refreshed_fields = dict(fields)
        journal_kind = self._journal_kind_from_fields(mode, refreshed_fields)
        evaluation = evaluate_journal_fields(refreshed_fields, journal_kind)
        reflection_prompts = build_reflection_prompts(
            refreshed_fields,
            journal_kind,
            evaluation["missing_fields"],
        )
        refreshed["mode"] = mode
        refreshed["journal_kind"] = journal_kind
        refreshed["fields"] = refreshed_fields
        refreshed["required_fields"] = evaluation["required_fields"]
        refreshed["missing_fields"] = evaluation["missing_fields"]
        refreshed["follow_up_questions"] = evaluation["follow_up_questions"]
        refreshed["action_ready"] = evaluation["action_ready"]
        refreshed["suggested_command"] = evaluation["suggested_command"]
        refreshed["standardized_record"] = build_standardized_record(refreshed_fields, journal_kind)
        refreshed["reflection_prompts"] = reflection_prompts
        refreshed["polling_bundle"] = build_polling_bundle(
            refreshed_fields,
            journal_kind,
            evaluation["missing_fields"],
            evaluation["follow_up_questions"],
            reflection_prompts=reflection_prompts,
        )
        if session_reuse:
            refreshed["session_reuse"] = session_reuse
        elif "session_reuse" in refreshed:
            refreshed.pop("session_reuse", None)
        return refreshed

    def _looks_like_status_request(self, text: str) -> bool:
        token = str(text or "").strip()
        return token in {"当前", "当前状态", "状态", "进度", "看看进度", "show", "status"}

    def _looks_like_reset_request(self, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        return lowered in {"reset", "clear", "重置", "清空会话", "结束会话", "重新开始"}

    def _looks_like_apply_request(self, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        return lowered in {"完成", "落账", "apply", "确认落账"}

    def _looks_like_reflection_message(self, text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return False
        hints = (
            "补充",
            "反思",
            "复盘",
            "经验",
            "教训",
            "当时",
            "有点急",
            "冲动",
            "拿不稳",
            "怕错过",
            "心态",
            "情绪",
            "卖飞",
        )
        return any(item in token for item in hints)

    def _looks_like_new_journal_message(self, text: str, mode: str, trade_date: str) -> bool:
        parsed = self.parse_journal_text(text, mode=mode, trade_date=trade_date)
        fields = parsed.get("fields") or {}
        if fields.get("ts_code"):
            return True
        if fields.get("buy_price") is not None or fields.get("sell_price") is not None:
            return True
        if str(text or "").strip().startswith(("计划", "今天", "买了", "卖了", "低吸", "追高")):
            return True
        return False

    def _assistant_message_for_draft(self, draft: dict[str, Any]) -> str:
        missing = "、".join(draft.get("missing_fields") or [])
        next_question = draft.get("next_question") or "继续补充即可。"
        examples = ((draft.get("polling_bundle") or {}).get("examples") or [])
        example_text = f" 例如：{examples[0]}。" if examples else ""
        reuse_prefix = self._session_reuse_summary(draft.get("session_reuse") or [])
        return f"{reuse_prefix}我先帮你起草好了，当前还缺：{missing or '无'}。下一问：{next_question}{example_text}"

    def _assistant_message_for_applied(
        self,
        journal_kind: str,
        fields: dict[str, Any],
        entity_kind: str,
        session_reuse: list[dict[str, Any]] | None = None,
    ) -> str:
        summary = build_standardized_record(fields, journal_kind).get("summary") or ""
        prefix = "已记入计划账本" if entity_kind == "plan" else "已记入交易账本"
        reuse_prefix = self._session_reuse_summary(session_reuse)
        return f"{reuse_prefix}{prefix}。{summary}"

    def _assistant_message_for_enrich(self, entity_kind: str, updated_fields: list[str], reflection_prompts: list[dict[str, Any]]) -> str:
        label = "计划" if entity_kind == "plan" else "交易"
        changed = "、".join(updated_fields[:6]) or "备注"
        tail = ""
        if reflection_prompts:
            tail = f" 下一步可继续想一想：{reflection_prompts[0].get('question') or ''}"
        return f"已把补充内容沉淀回原{label}，这次更新了：{changed}.{tail}".strip()

    def _entity_info_from_response(self, entity_kind: str, payload: dict[str, Any]) -> tuple[str, str]:
        if entity_kind == "plan":
            plan = payload.get("plan") or {}
            return "plan", str(plan.get("plan_id") or "")
        if entity_kind == "trade":
            trade = payload.get("trade") or {}
            return "trade", str(trade.get("trade_id") or "")
        return "", ""

    def _open_trade_candidates(self, ts_code: str) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'open' AND ts_code = ? ORDER BY buy_date DESC, updated_at DESC",
            (normalize_ts_code(ts_code),),
        )

    def _apply_journal_fields(self, fields: dict[str, Any], journal_kind: str, trade_date: str | None = None) -> dict[str, Any]:
        if journal_kind == "plan":
            return {
                "applied": True,
                "journal_kind": journal_kind,
                "result": self.create_plan(
                    ts_code=fields["ts_code"],
                    name=fields.get("name"),
                    direction=fields.get("direction") or "buy",
                    thesis=fields.get("thesis") or fields.get("notes") or "",
                    logic_tags=fields.get("logic_tags", []),
                    market_stage=(fields.get("environment_tags") or [""])[0]
                    if any(tag.endswith("市") or "分歧" in tag or "主升" in tag for tag in fields.get("environment_tags", []))
                    else "",
                    environment_tags=fields.get("environment_tags", []),
                    buy_zone=fields.get("buy_zone") or "",
                    sell_zone=fields.get("sell_zone") or "",
                    stop_loss=fields.get("stop_loss") or "",
                    holding_period=fields.get("holding_period") or "",
                    valid_from=fields.get("valid_from") or normalize_trade_date(trade_date or self._today()),
                    valid_to=fields.get("valid_to") or normalize_trade_date(trade_date or self._today()),
                    decision_context=self._decision_context_from_fields(fields, "plan"),
                    notes=fields.get("notes") or "",
                ),
            }
        if journal_kind in {"open_trade", "closed_trade"}:
            return {
                "applied": True,
                "journal_kind": journal_kind,
                "result": self.log_trade(
                    ts_code=fields["ts_code"],
                    name=fields.get("name"),
                    buy_date=fields["buy_date"],
                    buy_price=float(fields["buy_price"]),
                    thesis=fields.get("thesis") or fields.get("notes") or "",
                    sell_date=fields.get("sell_date") or None,
                    sell_price=float(fields["sell_price"]) if fields.get("sell_price") is not None else None,
                    logic_type_tags=fields.get("logic_tags", []),
                    pattern_tags=fields.get("pattern_tags", []),
                    environment_tags=fields.get("environment_tags", []),
                    emotion_notes=fields.get("emotion_notes") or "",
                    mistake_tags=fields.get("mistake_tags", []),
                    lessons_learned=fields.get("lessons_learned") or "",
                    decision_context=self._decision_context_from_fields(fields, journal_kind),
                    notes=fields.get("notes") or "",
                    position_size_pct=fields.get("position_size_pct"),
                ),
            }
        candidates = self._open_trade_candidates(fields["ts_code"])
        if not candidates:
            return {
                "applied": False,
                "journal_kind": journal_kind,
                "reason": "no_open_trade_found",
                "candidates": [],
            }
        if len(candidates) > 1:
            return {
                "applied": False,
                "journal_kind": journal_kind,
                "reason": "multiple_open_trades",
                "candidates": [
                    {
                        "trade_id": item.get("trade_id"),
                        "name": item.get("name") or item.get("ts_code"),
                        "buy_date": item.get("buy_date"),
                        "buy_price": item.get("buy_price"),
                    }
                    for item in candidates[:5]
                ],
            }
        trade_row = candidates[0]
        return {
            "applied": True,
            "journal_kind": journal_kind,
            "resolved_trade_id": trade_row.get("trade_id"),
            "result": self.close_trade(
                trade_row["trade_id"],
                sell_date=fields["sell_date"],
                sell_price=float(fields["sell_price"]),
                sell_reason=fields.get("thesis") or "",
                emotion_notes=fields.get("emotion_notes") or "",
                mistake_tags=fields.get("mistake_tags", []),
                lessons_learned=fields.get("lessons_learned") or "",
                notes=fields.get("notes") or "",
            ),
        }

    def _applied_entity_info(self, apply_result: dict[str, Any]) -> tuple[str, str]:
        if not apply_result.get("applied"):
            return "", ""
        result = apply_result.get("result") or {}
        journal_kind = apply_result.get("journal_kind") or ""
        if journal_kind == "plan":
            plan = result.get("plan") or {}
            return "plan", str(plan.get("plan_id") or "")
        trade = result if journal_kind == "close_only" else (result or {})
        return "trade", str(trade.get("trade_id") or "")

    def _merge_journal_reply(
        self,
        existing_fields: dict[str, Any],
        reply_text: str,
        mode: str,
        trade_date: str,
        current_missing: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        merged = dict(existing_fields)
        parsed = self.parse_journal_text(reply_text, mode=mode, trade_date=trade_date)
        target_fields = list(dict.fromkeys(current_missing[:2]))
        for optional_field in ("ts_code", "direction", "thesis"):
            if optional_field in current_missing:
                target_fields.append(optional_field)
        if any(token in reply_text for token in ("止损", "跌破")):
            target_fields.append("stop_loss")
        if re.search(r"\d+(?:\.\d+)?\s*[-~至到]\s*\d+(?:\.\d+)?", reply_text):
            if any(token in reply_text for token in ("卖", "止盈", "减仓")):
                target_fields.append("sell_zone")
            if any(token in reply_text for token in ("买", "低吸", "回踩", "区间")):
                target_fields.append("buy_zone")
        target_fields = list(dict.fromkeys(target_fields))
        for field_name in target_fields:
            value = extract_field_value(field_name, reply_text, symbol_index=self._symbol_index(), anchor_date=trade_date)
            if value in (None, "", []):
                continue
            if field_name == "ts_code":
                merged["ts_code"] = value.get("ts_code") or merged.get("ts_code") or ""
                if value.get("name"):
                    merged["name"] = value["name"]
                continue
            if field_name == "stop_loss":
                merged[field_name] = str(value)
                continue
            merged[field_name] = value

        fields = parsed.get("fields") or {}
        if fields.get("buy_price") is not None and any(token in reply_text for token in ("买", "开仓", "建仓", "低吸", "上车")):
            merged["buy_price"] = fields["buy_price"]
        if fields.get("sell_price") is not None and any(token in reply_text for token in ("卖", "平仓", "清仓", "减仓")):
            merged["sell_price"] = fields["sell_price"]
        if fields.get("buy_date") and any(token in reply_text for token in ("今天", "昨天", "年", "月", "-", "/")):
            merged["buy_date"] = fields["buy_date"]
        if fields.get("sell_date") and any(token in reply_text for token in ("今天", "昨天", "年", "月", "-", "/")):
            merged["sell_date"] = fields["sell_date"]
        if fields.get("buy_zone") and any(token in reply_text for token in ("买", "低吸", "回踩", "区间")):
            merged["buy_zone"] = fields["buy_zone"]
        if fields.get("sell_zone") and any(token in reply_text for token in ("卖", "止盈", "减仓", "区间")):
            merged["sell_zone"] = fields["sell_zone"]
        if fields.get("stop_loss") and any(token in reply_text for token in ("止损", "跌破")):
            merged["stop_loss"] = fields["stop_loss"]
        if fields.get("position_size_pct") is not None:
            merged["position_size_pct"] = fields["position_size_pct"]
        if fields.get("position_reason"):
            merged["position_reason"] = self._append_text_block(merged.get("position_reason"), fields.get("position_reason"))
        if fields.get("position_confidence") not in (None, ""):
            merged["position_confidence"] = fields["position_confidence"]
        if fields.get("stress_level") not in (None, ""):
            merged["stress_level"] = fields["stress_level"]
        if fields.get("thesis"):
            merged["thesis"] = fields["thesis"]
        if fields.get("name") and merged.get("ts_code") and not merged.get("name"):
            merged["name"] = fields["name"]
        merged["logic_tags"] = self._merge_unique_tags(merged.get("logic_tags", []), fields.get("logic_tags", []))
        merged["pattern_tags"] = self._merge_unique_tags(merged.get("pattern_tags", []), fields.get("pattern_tags", []))
        merged["environment_tags"] = self._merge_unique_tags(merged.get("environment_tags", []), fields.get("environment_tags", []))
        merged["user_focus"] = self._merge_unique_items(merged.get("user_focus", []), fields.get("user_focus", []))
        merged["observed_signals"] = self._merge_unique_items(merged.get("observed_signals", []), fields.get("observed_signals", []))
        merged["mistake_tags"] = self._merge_unique_tags(merged.get("mistake_tags", []), fields.get("mistake_tags", []))
        if fields.get("emotion_notes"):
            merged["emotion_notes"] = self._append_text_block(merged.get("emotion_notes"), fields.get("emotion_notes"))
        if "经验" in reply_text or "教训" in reply_text:
            merged["lessons_learned"] = self._append_text_block(merged.get("lessons_learned"), reply_text)
        merged["notes"] = self._append_text_block(merged.get("notes"), reply_text)
        merged["valid_from"] = merged.get("valid_from") or trade_date
        if mode == "plan" and not merged.get("valid_to"):
            merged["valid_to"] = trade_date
        return merged, parsed

    def _decode_journal_draft(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        payload = dict(row)
        payload["raw_inputs"] = json_loads(row.get("raw_inputs_json"), []) or []
        payload["fields"] = json_loads(row.get("fields_json"), {}) or {}
        payload["missing_fields"] = json_loads(row.get("missing_fields_json"), []) or []
        payload["follow_up_questions"] = json_loads(row.get("follow_up_questions_json"), []) or []
        payload["result"] = json_loads(row.get("result_json"), {}) or {}
        payload["next_question"] = payload.get("last_question") or (payload["follow_up_questions"][0] if payload["follow_up_questions"] else "")
        payload["standardized_record"] = build_standardized_record(payload["fields"], payload.get("journal_kind") or "open_trade")
        reflection_prompts = build_reflection_prompts(
            payload["fields"],
            payload.get("journal_kind") or "open_trade",
            payload["missing_fields"],
        )
        payload["reflection_prompts"] = reflection_prompts
        payload["polling_bundle"] = build_polling_bundle(
            payload["fields"],
            payload.get("journal_kind") or "open_trade",
            payload["missing_fields"],
            payload["follow_up_questions"],
            reflection_prompts=reflection_prompts,
        )
        for key in ("raw_inputs_json", "fields_json", "missing_fields_json", "follow_up_questions_json", "result_json"):
            payload.pop(key, None)
        return payload

    def _resolve_journal_draft_id(self, draft_id: str | None = None, session_key: str | None = None) -> tuple[str, bool]:
        token = str(draft_id or "").strip()
        if token:
            return token, False
        session_token = str(session_key or "").strip()
        if session_token:
            active_rows = self.db.fetchall(
                "SELECT draft_id FROM journal_drafts WHERE status = 'active' AND session_key = ? ORDER BY updated_at DESC LIMIT 2",
                (session_token,),
            )
        else:
            active_rows = self.db.fetchall(
                "SELECT draft_id FROM journal_drafts WHERE status = 'active' ORDER BY updated_at DESC LIMIT 2"
            )
        if not active_rows:
            raise ValueError("no active draft found")
        if len(active_rows) > 1:
            if session_token:
                raise ValueError(f"multiple active drafts found in session: {session_token}; please specify draft_id")
            raise ValueError("multiple active drafts found; please specify draft_id")
        return str(active_rows[0]["draft_id"]), True

    def start_journal_draft(
        self,
        text: str,
        mode: str = "auto",
        trade_date: str | None = None,
        session_key: str | None = None,
        session_memory: dict[str, Any] | None = None,
        focused_symbol: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = normalize_trade_date(trade_date or self._today())
        parsed = self.parse_journal_text(text, mode=mode, trade_date=token)
        parsed_fields, reuse_items = self._apply_session_memory_to_fields(
            parsed.get("fields") or {},
            trade_date=token,
            journal_kind=parsed.get("journal_kind") or "open_trade",
            memory=session_memory,
            focused_symbol=focused_symbol,
        )
        parsed = self._refresh_parsed_payload(
            parsed,
            mode=parsed.get("mode") or mode,
            fields=parsed_fields,
            trade_date=token,
            session_reuse=reuse_items,
        )
        draft_id = make_id("draft")
        timestamp = now_ts()
        session_token = str(session_key or "").strip()
        missing_fields = parsed.get("missing_fields", [])
        follow_up_questions = parsed.get("follow_up_questions", [])
        next_field = missing_fields[0] if missing_fields else ""
        last_question = follow_up_questions[0] if follow_up_questions else ""
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO journal_drafts(
                    draft_id, session_key, mode, journal_kind, trade_date, status, source_text, latest_input_text, raw_inputs_json,
                    fields_json, missing_fields_json, follow_up_questions_json, next_field, last_question,
                    applied_entity_kind, applied_entity_id, result_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, '', '', '{}', ?, ?)
                """,
                (
                    draft_id,
                    session_token,
                    parsed.get("mode") or mode,
                    parsed["journal_kind"],
                    token,
                    text,
                    text,
                    json_dumps([text]),
                    json_dumps(parsed["fields"]),
                    json_dumps(missing_fields),
                    json_dumps(follow_up_questions),
                    next_field,
                    last_question,
                    timestamp,
                    timestamp,
                ),
            )
        payload = self.get_journal_draft(draft_id) or {}
        if reuse_items:
            payload["session_reuse"] = reuse_items
        return payload

    def get_journal_draft(self, draft_id: str | None = None, session_key: str | None = None) -> dict[str, Any] | None:
        resolved_id, auto_selected = self._resolve_journal_draft_id(draft_id, session_key=session_key)
        payload = self._decode_journal_draft(
            self.db.fetchone("SELECT * FROM journal_drafts WHERE draft_id = ?", (resolved_id,))
        )
        if payload is not None:
            payload["auto_selected_latest_active"] = auto_selected
        return payload

    def list_journal_drafts(self, status: str | None = None, limit: int = 20, session_key: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM journal_drafts WHERE 1 = 1"
        params: list[Any] = []
        if session_key:
            sql += " AND session_key = ?"
            params.append(str(session_key).strip())
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.fetchall(sql, tuple(params))
        return [item for item in (self._decode_journal_draft(row) for row in rows) if item]

    def cancel_journal_draft(self, draft_id: str | None = None, reason: str = "", session_key: str | None = None) -> dict[str, Any]:
        resolved_id, auto_selected = self._resolve_journal_draft_id(draft_id, session_key=session_key)
        draft = self.get_journal_draft(resolved_id, session_key=session_key)
        if not draft:
            raise ValueError(f"draft not found: {resolved_id}")
        result = draft.get("result") or {}
        if reason:
            result["cancel_reason"] = reason
        self.db.execute(
            "UPDATE journal_drafts SET status = 'cancelled', result_json = ?, updated_at = ? WHERE draft_id = ?",
            (json_dumps(result), now_ts(), resolved_id),
        )
        payload = self.get_journal_draft(resolved_id, session_key=session_key) or {}
        payload["auto_selected_latest_active"] = auto_selected
        return payload

    def continue_journal_draft(
        self,
        draft_id: str | None = None,
        text: str = "",
        apply_if_ready: bool = True,
        session_key: str | None = None,
        session_memory: dict[str, Any] | None = None,
        focused_symbol: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        resolved_id, auto_selected = self._resolve_journal_draft_id(draft_id, session_key=session_key)
        draft = self.get_journal_draft(resolved_id, session_key=session_key)
        if not draft:
            raise ValueError(f"draft not found: {resolved_id}")
        if draft.get("status") != "active":
            return draft
        token = draft.get("trade_date") or self._today()
        current_missing = list(draft.get("missing_fields") or [])
        merged_fields, parsed = self._merge_journal_reply(
            draft.get("fields") or {},
            text,
            mode=draft.get("mode") or "auto",
            trade_date=token,
            current_missing=current_missing,
        )
        journal_kind = self._journal_kind_from_fields(draft.get("mode") or "auto", merged_fields)
        merged_fields, reuse_items = self._apply_session_memory_to_fields(
            merged_fields,
            trade_date=token,
            journal_kind=journal_kind,
            memory=session_memory,
            focused_symbol=focused_symbol,
        )
        parsed = self._refresh_parsed_payload(
            parsed,
            mode=draft.get("mode") or "auto",
            fields=merged_fields,
            trade_date=token,
            session_reuse=reuse_items,
        )
        journal_kind = parsed.get("journal_kind") or journal_kind
        evaluation = evaluate_journal_fields(merged_fields, journal_kind)
        raw_inputs = list(draft.get("raw_inputs") or [])
        raw_inputs.append(text)
        self.db.execute(
            """
            UPDATE journal_drafts
            SET journal_kind = ?, latest_input_text = ?, raw_inputs_json = ?, fields_json = ?,
                missing_fields_json = ?, follow_up_questions_json = ?, next_field = ?, last_question = ?, updated_at = ?
            WHERE draft_id = ?
            """,
            (
                journal_kind,
                text,
                json_dumps(raw_inputs),
                json_dumps(merged_fields),
                json_dumps(evaluation["missing_fields"]),
                json_dumps(evaluation["follow_up_questions"]),
                evaluation["missing_fields"][0] if evaluation["missing_fields"] else "",
                evaluation["follow_up_questions"][0] if evaluation["follow_up_questions"] else "",
                now_ts(),
                resolved_id,
            ),
        )
        response = self.get_journal_draft(resolved_id, session_key=session_key) or {}
        response["auto_selected_latest_active"] = auto_selected
        response["last_parse"] = parsed
        if reuse_items:
            response["session_reuse"] = reuse_items
        if apply_if_ready and evaluation["action_ready"]:
            response["apply_result"] = self.apply_journal_draft(resolved_id, session_key=session_key)
            response = self.get_journal_draft(resolved_id, session_key=session_key) or response
            response["apply_result"] = response.get("result") or {}
            response["auto_selected_latest_active"] = auto_selected
            if reuse_items:
                response["session_reuse"] = reuse_items
        return response

    def apply_journal_draft(self, draft_id: str | None = None, session_key: str | None = None) -> dict[str, Any]:
        resolved_id, auto_selected = self._resolve_journal_draft_id(draft_id, session_key=session_key)
        draft = self.get_journal_draft(resolved_id, session_key=session_key)
        if not draft:
            raise ValueError(f"draft not found: {resolved_id}")
        evaluation = evaluate_journal_fields(draft.get("fields") or {}, draft.get("journal_kind") or "open_trade")
        if not evaluation["action_ready"]:
            result = {
                "applied": False,
                "reason": "missing_fields",
                "missing_fields": evaluation["missing_fields"],
                "follow_up_questions": evaluation["follow_up_questions"],
            }
            self.db.execute(
                "UPDATE journal_drafts SET result_json = ?, updated_at = ? WHERE draft_id = ?",
                (json_dumps(result), now_ts(), resolved_id),
            )
            fresh = self.get_journal_draft(resolved_id, session_key=session_key) or {}
            fresh["result"] = result
            fresh["auto_selected_latest_active"] = auto_selected
            return fresh
        apply_result = self._apply_journal_fields(
            draft.get("fields") or {},
            draft.get("journal_kind") or "open_trade",
            trade_date=draft.get("trade_date"),
        )
        entity_kind, entity_id = self._applied_entity_info(apply_result)
        new_status = "applied" if apply_result.get("applied") else draft.get("status") or "active"
        self.db.execute(
            """
            UPDATE journal_drafts
            SET status = ?, applied_entity_kind = ?, applied_entity_id = ?, result_json = ?, updated_at = ?
            WHERE draft_id = ?
            """,
            (
                new_status,
                entity_kind,
                entity_id,
                json_dumps(apply_result),
                now_ts(),
                resolved_id,
            ),
        )
        fresh = self.get_journal_draft(resolved_id, session_key=session_key) or {}
        fresh["result"] = apply_result
        fresh["auto_selected_latest_active"] = auto_selected
        return fresh

    def apply_journal_text(self, text: str, mode: str = "auto", trade_date: str | None = None) -> dict[str, Any]:
        draft = self.parse_journal_text(text, mode=mode, trade_date=trade_date)
        if not draft.get("action_ready"):
            return {
                "applied": False,
                "reason": "missing_fields",
                "draft": draft,
            }

        apply_result = self._apply_journal_fields(draft["fields"], draft["journal_kind"], trade_date=trade_date)
        if not apply_result.get("applied"):
            return {
                "applied": False,
                "reason": apply_result.get("reason") or "apply_failed",
                "draft": draft,
                "candidates": apply_result.get("candidates", []),
            }
        return {
            "applied": True,
            "journal_kind": draft["journal_kind"],
            "draft": draft,
            "result": apply_result["result"],
            "resolved_trade_id": apply_result.get("resolved_trade_id") or "",
        }

    def reset_session_thread(self, session_key: str | None, reason: str = "") -> dict[str, Any]:
        token = self._normalize_session_key(session_key)
        try:
            active_draft = self.get_journal_draft(session_key=token)
        except Exception:
            active_draft = None
        if active_draft and active_draft.get("status") == "active":
            try:
                self.cancel_journal_draft(active_draft.get("draft_id"), reason=reason or "session_reset", session_key=token)
            except Exception:
                pass
        payload = self._upsert_session_thread(
            token,
            active_draft_id="",
            active_entity_kind="",
            active_entity_id="",
            active_mode="auto",
            trade_date="",
            status="active",
            memory={},
            last_user_text=reason or "reset",
            last_assistant_text="会话已重置，可以重新开始记账。",
            last_route="session_reset",
            last_result={"reset": True, "reason": reason or ""},
        )
        return {
            "session_key": token,
            "route": "session_reset",
            "assistant_message": "会话已重置，可以重新开始记账。",
            "session_state": self._build_session_state_payload(token),
            "thread": payload,
        }

    def get_session_state(self, session_key: str | None) -> dict[str, Any]:
        token = self._normalize_session_key(session_key)
        state = self._build_session_state_payload(token)
        if state.get("active_draft_id"):
            assistant_message = f"当前还在补这条草稿。下一问：{state.get('pending_question') or '继续补充即可。'}"
        elif state.get("active_entity_kind"):
            if state.get("pending_question"):
                assistant_message = f"{state.get('entity_summary') or '最近聚焦记录已完成事实对齐。'} 下一步建议补：{state.get('pending_question')}"
            else:
                assistant_message = state.get("entity_summary") or "当前会话没有待补草稿，但保留了最近的聚焦记录。"
        else:
            assistant_message = "当前会话没有未完成草稿，可以直接继续发自然语言记账。"
        return {
            "session_key": token,
            "route": "session_state",
            "assistant_message": assistant_message,
            "session_state": state,
        }

    def handle_session_turn(
        self,
        session_key: str,
        text: str,
        mode: str = "auto",
        trade_date: str | None = None,
        lookback_days: int = 365,
    ) -> dict[str, Any]:
        token = self._normalize_session_key(session_key)
        user_text = str(text or "").strip()
        if not user_text:
            return self.get_session_state(token)
        current = self.get_session_thread(token) or {}
        resolved_trade_date = normalize_trade_date(trade_date or current.get("trade_date") or self._today())
        current_memory = self._normalized_session_memory(current.get("memory"))
        focused_symbol = self._focused_symbol_context(
            str(current.get("active_entity_kind") or ""),
            str(current.get("active_entity_id") or ""),
            resolved_trade_date,
        )

        if self._looks_like_reset_request(user_text):
            return self.reset_session_thread(token, reason=user_text)
        if self._looks_like_status_request(user_text):
            return self.get_session_state(token)

        active_draft_id = str(current.get("active_draft_id") or "")
        if active_draft_id:
            if self._looks_like_apply_request(user_text):
                draft = self.apply_journal_draft(active_draft_id, session_key=token)
            else:
                draft = self.continue_journal_draft(
                    active_draft_id,
                    user_text,
                    apply_if_ready=True,
                    session_key=token,
                    session_memory=current_memory,
                    focused_symbol=focused_symbol,
                )
            route = "draft_applied" if draft.get("status") == "applied" else "draft_continued"
            next_memory = self._update_session_memory_from_fields(
                current_memory,
                draft.get("fields") or {},
                trade_date=resolved_trade_date,
                journal_kind=draft.get("journal_kind") or "",
            )
            if draft.get("status") == "applied":
                entity_kind = draft.get("applied_entity_kind") or ""
                entity_id = draft.get("applied_entity_id") or ""
                assistant_message = self._assistant_message_for_applied(
                    draft.get("journal_kind") or "open_trade",
                    draft.get("fields") or {},
                    entity_kind,
                    session_reuse=draft.get("session_reuse") or [],
                )
                if (draft.get("reflection_prompts") or []):
                    assistant_message += f" 接下来可以继续补一句：{draft['reflection_prompts'][0].get('question') or ''}"
                self._upsert_session_thread(
                    token,
                    active_draft_id="",
                    active_entity_kind=entity_kind,
                    active_entity_id=entity_id,
                    active_mode=draft.get("mode") or mode,
                    trade_date=resolved_trade_date,
                    last_user_text=user_text,
                    last_assistant_text=assistant_message,
                    last_route=route,
                    last_result=draft,
                    memory=next_memory,
                )
            else:
                assistant_message = self._assistant_message_for_draft(draft)
                self._upsert_session_thread(
                    token,
                    active_draft_id=draft.get("draft_id") or active_draft_id,
                    active_entity_kind=current.get("active_entity_kind") or "",
                    active_entity_id=current.get("active_entity_id") or "",
                    active_mode=draft.get("mode") or mode,
                    trade_date=resolved_trade_date,
                    last_user_text=user_text,
                    last_assistant_text=assistant_message,
                    last_route=route,
                    last_result=draft,
                    memory=next_memory,
                )
            return {
                "session_key": token,
                "route": route,
                "assistant_message": assistant_message,
                "draft": draft,
                "session_state": self._build_session_state_payload(token),
            }

        active_entity_kind = str(current.get("active_entity_kind") or "")
        active_entity_id = str(current.get("active_entity_id") or "")
        if (
            active_entity_kind in {"plan", "trade"}
            and active_entity_id
            and self._looks_like_reflection_message(user_text)
            and not self._looks_like_new_journal_message(user_text, mode=mode, trade_date=resolved_trade_date)
        ):
            if active_entity_kind == "plan":
                enriched = self.enrich_plan_from_text(active_entity_id, user_text, trade_date=resolved_trade_date, lookback_days=lookback_days)
                memory_fields = self._plan_to_journal_fields(enriched.get("plan") or {})
            else:
                enriched = self.enrich_trade_from_text(active_entity_id, user_text, trade_date=resolved_trade_date, lookback_days=lookback_days)
                memory_fields = self._trade_to_journal_fields(enriched.get("trade") or {})
            entity_kind, entity_id = self._entity_info_from_response(active_entity_kind, enriched)
            assistant_message = self._assistant_message_for_enrich(
                entity_kind or active_entity_kind,
                enriched.get("updated_fields") or [],
                enriched.get("reflection_prompts") or [],
            )
            next_memory = self._update_session_memory_from_fields(
                current_memory,
                memory_fields,
                trade_date=resolved_trade_date,
                journal_kind="plan" if active_entity_kind == "plan" else "open_trade",
            )
            self._upsert_session_thread(
                token,
                active_draft_id="",
                active_entity_kind=entity_kind or active_entity_kind,
                active_entity_id=entity_id or active_entity_id,
                active_mode=mode,
                trade_date=resolved_trade_date,
                last_user_text=user_text,
                last_assistant_text=assistant_message,
                last_route="entity_enriched",
                last_result=enriched,
                memory=next_memory,
            )
            return {
                "session_key": token,
                "route": "entity_enriched",
                "assistant_message": assistant_message,
                "result": enriched,
                "session_state": self._build_session_state_payload(token),
            }

        parsed = self.parse_journal_text(user_text, mode=mode, trade_date=resolved_trade_date)
        parsed_fields, reuse_items = self._apply_session_memory_to_fields(
            parsed.get("fields") or {},
            trade_date=resolved_trade_date,
            journal_kind=parsed.get("journal_kind") or "open_trade",
            memory=current_memory,
            focused_symbol=focused_symbol,
        )
        parsed = self._refresh_parsed_payload(
            parsed,
            mode=parsed.get("mode") or mode,
            fields=parsed_fields,
            trade_date=resolved_trade_date,
            session_reuse=reuse_items,
        )
        if parsed.get("action_ready"):
            apply_result = self._apply_journal_fields(parsed["fields"], parsed["journal_kind"], trade_date=resolved_trade_date)
            entity_kind, entity_id = self._applied_entity_info(apply_result)
            assistant_message = self._assistant_message_for_applied(
                parsed["journal_kind"],
                parsed["fields"],
                entity_kind,
                session_reuse=parsed.get("session_reuse") or [],
            )
            if (parsed.get("reflection_prompts") or []):
                assistant_message += f" 接下来可以继续补一句：{parsed['reflection_prompts'][0].get('question') or ''}"
            result = {
                "applied": bool(apply_result.get("applied")),
                "journal_kind": parsed["journal_kind"],
                "draft": parsed,
                "result": apply_result.get("result") or {},
                "resolved_trade_id": apply_result.get("resolved_trade_id") or "",
            }
            next_memory = self._update_session_memory_from_fields(
                current_memory,
                parsed.get("fields") or {},
                trade_date=resolved_trade_date,
                journal_kind=parsed.get("journal_kind") or "",
            )
            self._upsert_session_thread(
                token,
                active_draft_id="",
                active_entity_kind=entity_kind,
                active_entity_id=entity_id,
                active_mode=mode,
                trade_date=resolved_trade_date,
                last_user_text=user_text,
                last_assistant_text=assistant_message,
                last_route="applied_from_session",
                last_result=result,
                memory=next_memory,
            )
            return {
                "session_key": token,
                "route": "applied_from_session",
                "assistant_message": assistant_message,
                "result": result,
                "session_state": self._build_session_state_payload(token),
            }

        draft = self.start_journal_draft(
            user_text,
            mode=mode,
            trade_date=resolved_trade_date,
            session_key=token,
            session_memory=current_memory,
            focused_symbol=focused_symbol,
        )
        assistant_message = self._assistant_message_for_draft(draft)
        next_memory = self._update_session_memory_from_fields(
            current_memory,
            draft.get("fields") or {},
            trade_date=resolved_trade_date,
            journal_kind=draft.get("journal_kind") or "",
        )
        self._upsert_session_thread(
            token,
            active_draft_id=draft.get("draft_id") or "",
            active_entity_kind=current.get("active_entity_kind") or "",
            active_entity_id=current.get("active_entity_id") or "",
            active_mode=draft.get("mode") or mode,
            trade_date=resolved_trade_date,
            last_user_text=user_text,
            last_assistant_text=assistant_message,
            last_route="draft_started",
            last_result=draft,
            memory=next_memory,
        )
        return {
            "session_key": token,
            "route": "draft_started",
            "assistant_message": assistant_message,
            "draft": draft,
            "session_state": self._build_session_state_payload(token),
        }

    def add_watchlist(self, ts_code: str, name: str | None = None, notes: str = "", source: str = "manual") -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        resolved_name = self._resolve_name(code, name)
        timestamp = now_ts()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist(ts_code, name, notes, source, is_active, created_at, updated_at)
                VALUES(?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(ts_code) DO UPDATE SET
                    name=excluded.name,
                    notes=excluded.notes,
                    source=excluded.source,
                    is_active=1,
                    updated_at=excluded.updated_at
                """,
                (code, resolved_name, notes, source, timestamp, timestamp),
            )
        return self.get_watchlist_item(code) or {}

    def get_watchlist_item(self, ts_code: str) -> dict[str, Any] | None:
        return self.db.fetchone("SELECT * FROM watchlist WHERE ts_code = ?", (normalize_ts_code(ts_code),))

    def list_watchlist(self, active_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM watchlist"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY updated_at DESC, ts_code ASC"
        return self.db.fetchall(sql)

    def remove_watchlist(self, ts_code: str) -> None:
        self.db.execute(
            "UPDATE watchlist SET is_active = 0, updated_at = ? WHERE ts_code = ?",
            (now_ts(), normalize_ts_code(ts_code)),
        )

    def add_keyword(self, keyword: str, category: str = "industry") -> dict[str, Any]:
        token = str(keyword or "").strip()
        if not token:
            raise ValueError("keyword is required")
        timestamp = now_ts()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO keywords(keyword, category, enabled, created_at, updated_at)
                VALUES(?, ?, 1, ?, ?)
                ON CONFLICT(keyword) DO UPDATE SET
                    category=excluded.category,
                    enabled=1,
                    updated_at=excluded.updated_at
                """,
                (token, category, timestamp, timestamp),
            )
        return self.db.fetchone("SELECT * FROM keywords WHERE keyword = ?", (token,)) or {}

    def list_keywords(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM keywords"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY updated_at DESC, keyword ASC"
        return self.db.fetchall(sql)

    def remove_keyword(self, keyword: str) -> None:
        self.db.execute(
            "UPDATE keywords SET enabled = 0, updated_at = ? WHERE keyword = ?",
            (now_ts(), str(keyword or "").strip()),
        )

    def create_plan(
        self,
        ts_code: str,
        direction: str,
        thesis: str,
        logic_tags: list[str] | str | None = None,
        market_stage: str | None = None,
        environment_tags: list[str] | str | None = None,
        buy_zone: str | None = None,
        sell_zone: str | None = None,
        stop_loss: str | None = None,
        holding_period: str | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        reminder_time: str | None = None,
        notes: str | None = None,
        decision_context: dict[str, Any] | None = None,
        with_reference: bool = False,
        lookback_days: int = 365,
        name: str | None = None,
    ) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        resolved_name = self._resolve_name(code, name)
        plan_id = make_id("plan")
        start = normalize_trade_date(valid_from or self._today())
        end = normalize_trade_date(valid_to or shift_calendar_date(start, 3))
        timestamp = now_ts()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO plans(
                    plan_id, ts_code, name, direction, thesis, logic_tags_json, market_stage_tag,
                    environment_tags_json, buy_zone, sell_zone, stop_loss, holding_period,
                    valid_from, valid_to, reminder_time, status, linked_trade_id, abandon_reason,
                    decision_context_json,
                    notes, created_at, updated_at
                ) VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', '', ?, ?, ?, ?
                )
                """,
                (
                    plan_id,
                    code,
                    resolved_name,
                    direction,
                    thesis,
                    json_dumps(split_tags(logic_tags)),
                    market_stage or "",
                    json_dumps(split_tags(environment_tags)),
                    buy_zone or "",
                    sell_zone or "",
                    stop_loss or "",
                    holding_period or "",
                    start,
                    end,
                    reminder_time or self.config.get("schedules", {}).get("plan_reminder_time", "08:30"),
                    json_dumps(decision_context or {}),
                    notes or "",
                    timestamp,
                    timestamp,
                ),
            )
        plan = self.get_plan(plan_id) or {}
        result = {"plan": plan}
        if with_reference:
            result["reference"] = self.generate_reference(
                logic_tags=split_tags(logic_tags),
                market_stage=market_stage,
                environment_tags=split_tags(environment_tags),
                lookback_days=lookback_days,
                write_artifact=False,
            )
        if split_tags(logic_tags) or market_stage or split_tags(environment_tags):
            result["evolution_reminder"] = self.generate_evolution_reminder(
                logic_tags=split_tags(logic_tags),
                market_stage=market_stage,
                environment_tags=split_tags(environment_tags),
                lookback_days=lookback_days,
                write_artifact=False,
            )
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_plan", True):
            result["vault_note"] = self.export_plan_note(plan_id)
        return result

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self.db.fetchone("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))

    def list_plans(self, status: str | None = None, active_only: bool = False, trade_date: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM plans WHERE 1 = 1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if active_only:
            token = normalize_trade_date(trade_date or self._today())
            sql += " AND valid_from <= ? AND valid_to >= ? AND status = 'pending'"
            params.extend([token, token])
        sql += " ORDER BY valid_to ASC, created_at DESC"
        return self.db.fetchall(sql, tuple(params))

    def update_plan_status(self, plan_id: str, status: str, trade_id: str | None = None, reason: str | None = None) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"plan not found: {plan_id}")
        linked_trade_id = trade_id if trade_id is not None else plan.get("linked_trade_id") or ""
        self.db.execute(
            "UPDATE plans SET status = ?, linked_trade_id = ?, abandon_reason = ?, updated_at = ? WHERE plan_id = ?",
            (status, linked_trade_id, reason or plan.get("abandon_reason") or "", now_ts(), plan_id),
        )
        return self.get_plan(plan_id) or {}

    def enrich_plan_from_text(
        self,
        plan_id: str,
        text: str,
        trade_date: str | None = None,
        lookback_days: int = 365,
    ) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"plan not found: {plan_id}")
        anchor_date = normalize_trade_date(trade_date or plan.get("valid_from") or self._today())
        before_fields = self._plan_to_journal_fields(plan)
        merged_fields, parsed = self._merge_journal_reply(before_fields, text, mode="plan", trade_date=anchor_date, current_missing=[])
        merged_fields["ts_code"] = plan.get("ts_code") or merged_fields.get("ts_code") or ""
        merged_fields["name"] = plan.get("name") or merged_fields.get("name") or ""
        market_stage = self._pick_market_stage(merged_fields.get("environment_tags"), fallback=plan.get("market_stage_tag") or "")
        decision_context = self._decision_context_from_fields(
            merged_fields,
            "plan",
            base_context=json_loads(plan.get("decision_context_json"), {}) or {},
        )
        self.db.execute(
            """
            UPDATE plans
            SET direction = ?, thesis = ?, logic_tags_json = ?, market_stage_tag = ?, environment_tags_json = ?,
                buy_zone = ?, sell_zone = ?, stop_loss = ?, holding_period = ?, decision_context_json = ?, notes = ?, updated_at = ?
            WHERE plan_id = ?
            """,
            (
                merged_fields.get("direction") or plan.get("direction") or "buy",
                merged_fields.get("thesis") or plan.get("thesis") or "",
                json_dumps(split_tags(merged_fields.get("logic_tags", []))),
                market_stage,
                json_dumps(split_tags(merged_fields.get("environment_tags", []))),
                merged_fields.get("buy_zone") or "",
                merged_fields.get("sell_zone") or "",
                merged_fields.get("stop_loss") or "",
                merged_fields.get("holding_period") or "",
                json_dumps(decision_context),
                merged_fields.get("notes") or "",
                now_ts(),
                plan_id,
            ),
        )
        updated_plan = self.get_plan(plan_id) or {}
        reflection_prompts = build_reflection_prompts(merged_fields, "plan", [])
        response = {
            "plan": updated_plan,
            "parsed": parsed,
            "updated_fields": self._changed_field_names(
                before_fields,
                merged_fields,
                [
                    "thesis",
                    "logic_tags",
                    "environment_tags",
                    "user_focus",
                    "observed_signals",
                    "position_reason",
                    "position_confidence",
                    "buy_zone",
                    "sell_zone",
                    "stop_loss",
                    "holding_period",
                    "notes",
                ],
            ),
            "standardized_record": build_standardized_record(merged_fields, "plan"),
            "reflection_prompts": reflection_prompts,
            "polling_bundle": build_polling_bundle(
                merged_fields,
                "plan",
                [],
                [],
                reflection_prompts=reflection_prompts,
            ),
        }
        if json_loads(updated_plan.get("logic_tags_json"), []) or updated_plan.get("market_stage_tag") or json_loads(updated_plan.get("environment_tags_json"), []):
            response["evolution_reminder"] = self.generate_evolution_reminder(
                logic_tags=json_loads(updated_plan.get("logic_tags_json"), []),
                market_stage=updated_plan.get("market_stage_tag"),
                environment_tags=json_loads(updated_plan.get("environment_tags_json"), []),
                trade_date=anchor_date,
                lookback_days=lookback_days,
                write_artifact=False,
            )
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_plan", True):
            response["vault_note"] = self.export_plan_note(plan_id)
        return response

    def _event_id(self, event_type: str, ts_code: str, headline: str, published_at: str, source: str, url: str = "") -> str:
        seed = "|".join([event_type, ts_code or "", headline or "", published_at or "", source or "", url or ""])
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"event_{digest}"

    def add_info_event(
        self,
        event_type: str,
        headline: str,
        summary: str = "",
        ts_code: str | None = None,
        name: str | None = None,
        priority: str = "normal",
        source: str = "manual",
        published_at: str | None = None,
        trade_date: str | None = None,
        tags: list[str] | str | None = None,
        url: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        code = normalize_ts_code(ts_code) if ts_code else ""
        resolved_name = name or (self._resolve_name(code, None) if code else "")
        published = normalize_datetime_text(published_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        token = normalize_trade_date(trade_date or published[:10])
        event_url = str(url or "").strip()
        event_id = self._event_id(event_type, code, headline, published, source, event_url)
        created_at = now_ts()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO info_events(
                    event_id, ts_code, name, event_type, priority, headline, summary, source,
                    url, published_at, trade_date, tags_json, raw_payload_json, pushed_at, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    code,
                    resolved_name,
                    event_type,
                    priority,
                    headline,
                    summary,
                    source,
                    event_url,
                    published,
                    token,
                    json_dumps(split_tags(tags)),
                    json_dumps(raw_payload or {}),
                    "",
                    created_at,
                ),
            )
        return self.db.fetchone("SELECT * FROM info_events WHERE event_id = ?", (event_id,)) or {}

    def list_info_events(self, trade_date: str | None = None, priority: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT * FROM info_events WHERE 1 = 1"
        params: list[Any] = []
        if trade_date:
            sql += " AND trade_date = ?"
            params.append(normalize_trade_date(trade_date))
        if priority:
            sql += " AND priority = ?"
            params.append(priority)
        sql += " ORDER BY published_at DESC, created_at DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        return self.db.fetchall(sql, tuple(params))

    def _normalize_feed_rows(
        self,
        rows: list[dict[str, Any]],
        event_type: str,
        fallback_trade_date: str,
        default_ts_code: str = "",
        default_name: str = "",
        keyword_tag: str = "",
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        high_priority_words = ["业绩", "预告", "合同", "停牌", "复牌", "减持", "增持", "监管", "问询", "CPI", "PPI", "降准", "美联储"]
        for row in rows:
            headline = str(row.get("title") or row.get("ann_title") or row.get("headline") or row.get("name") or "").strip()
            if not headline:
                continue
            summary = str(row.get("summary") or row.get("content") or row.get("desc") or row.get("abstract") or "").strip()
            published = normalize_datetime_text(
                row.get("ann_date") or row.get("pub_time") or row.get("datetime") or row.get("date") or fallback_trade_date
            )
            code = normalize_ts_code(row.get("ts_code") or row.get("symbol") or default_ts_code or "") if (row.get("ts_code") or row.get("symbol") or default_ts_code) else ""
            name = str(row.get("name") or row.get("ts_name") or default_name or "").strip()
            source = str(row.get("src") or row.get("source") or event_type).strip()
            priority = "high" if any(word in f"{headline} {summary}" for word in high_priority_words) else "normal"
            tags = [event_type]
            if keyword_tag:
                tags.append(keyword_tag)
            url = str(row.get("url") or row.get("link") or row.get("article_url") or "").strip()
            normalized.append(
                {
                    "event_type": event_type,
                    "headline": headline,
                    "summary": summary,
                    "ts_code": code,
                    "name": name,
                    "source": source,
                    "priority": priority,
                    "published_at": published,
                    "trade_date": normalize_trade_date(published[:10] if published else fallback_trade_date),
                    "tags": tags,
                    "url": url,
                    "raw_payload": row,
                }
            )
        return normalized

    def _configured_url_adapters(self) -> list[dict[str, Any]]:
        cfg = self.config.get("url_sources", {}) or {}
        if not cfg.get("enabled", False):
            return []
        adapters = cfg.get("adapters") or []
        return [dict(item) for item in adapters if isinstance(item, dict)]

    def _is_tushare_permission_error(self, exc: Exception) -> bool:
        return "没有接口访问权限" in str(exc)

    def _is_tushare_rate_limit_error(self, exc: Exception) -> bool:
        return "每分钟最多访问该接口" in str(exc)

    def fetch_url_events(
        self,
        url: str,
        event_type: str = "news",
        source: str = "url_fetch",
        parser_mode: str = "auto",
        ts_code: str | None = None,
        name: str | None = None,
        keyword: str | None = None,
        trade_date: str | None = None,
        priority: str = "normal",
        limit: int = 20,
        items_path: str = "",
        headline_path: str = "",
        summary_path: str = "",
        published_path: str = "",
        url_path: str = "",
        include_patterns: list[str] | str | None = None,
        exclude_patterns: list[str] | str | None = None,
        follow_article: bool = False,
        min_headline_length: int | None = None,
        summary_lines: int | None = None,
        ignore_tokens: list[str] | str | None = None,
        drop_patterns: list[str] | str | None = None,
        same_domain_only: bool = False,
        script_markers: list[str] | str | None = None,
    ) -> dict[str, Any]:
        if not str(url or "").strip():
            raise ValueError("url is required")
        token = normalize_trade_date(trade_date or self._today())
        adapter = {
            "name": source or "url_fetch",
            "event_type": event_type,
            "source": source or "url_fetch",
            "priority": priority,
            "url_template": url,
            "parser": {
                "mode": parser_mode or "auto",
                "limit": limit,
                "items_path": items_path,
                "headline_path": headline_path,
                "summary_path": summary_path,
                "published_path": published_path,
                "url_path": url_path,
                "include_patterns": split_tags(include_patterns),
                "exclude_patterns": split_tags(exclude_patterns),
                "follow_article": follow_article,
                "min_headline_length": min_headline_length,
                "summary_lines": summary_lines,
                "ignore_tokens": split_tags(ignore_tokens),
                "drop_patterns": split_tags(drop_patterns),
                "same_domain_only": same_domain_only,
                "script_markers": split_tags(script_markers),
            },
        }
        context = {
            "ts_code": normalize_ts_code(ts_code) if ts_code else "",
            "name": name or "",
            "keyword": keyword or "",
            "start_date": token,
            "end_date": token,
            "trade_date": token,
            "label": keyword or name or ts_code or url,
        }
        rows = self.url_fetcher.fetch_url_events(url, adapter, context=context)
        inserted_rows: list[dict[str, Any]] = []
        for row in rows:
            inserted_rows.append(self.add_info_event(**row))
        return {
            "url": url,
            "event_type": event_type,
            "source": source,
            "trade_date": token,
            "inserted": len(inserted_rows),
            "events": inserted_rows,
        }

    def fetch_watchlist_events(self, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        watchlist = self.list_watchlist(active_only=True)
        keywords = self.list_keywords(enabled_only=True)
        start = normalize_trade_date(start_date or shift_calendar_date(self._today(), -int(self.config.get("monitoring", {}).get("announcement_lookback_days", 1))))
        end = normalize_trade_date(end_date or self._today())
        tushare_cfg = self.config.get("tushare", {})
        results = {
            "start_date": start,
            "end_date": end,
            "inserted": 0,
            "errors": [],
            "channels": {
                "tushare": {"attempted": bool(self.market), "inserted": 0},
                "url_adapters": {"attempted": 0, "inserted": 0, "adapter_results": []},
            },
        }

        if self.market:
            announcement_permission_denied = False
            for item in watchlist:
                if announcement_permission_denied:
                    break
                try:
                    df = self.market.call_endpoint(
                        tushare_cfg.get("announcement_endpoint", "anns_d"),
                        ts_code=item["ts_code"],
                        start_date=start,
                        end_date=end,
                    )
                    rows = self._normalize_feed_rows(
                        df.fillna("").to_dict(orient="records"),
                        "announcement",
                        end,
                        default_ts_code=item["ts_code"],
                        default_name=item.get("name") or "",
                    )
                    for row in rows:
                        self.add_info_event(**row)
                        results["inserted"] += 1
                        results["channels"]["tushare"]["inserted"] += 1
                except Exception as exc:
                    if self._is_tushare_permission_error(exc):
                        results["errors"].append(f"announcement:* -> {exc}")
                        announcement_permission_denied = True
                    else:
                        results["errors"].append(f"announcement:{item['ts_code']} -> {exc}")

            news_rate_limited = False
            for item in keywords:
                if news_rate_limited:
                    break
                try:
                    df = self.market.call_endpoint(
                        tushare_cfg.get("news_endpoint", "news"),
                        start_date=start,
                        end_date=end,
                        keyword=item["keyword"],
                    )
                    rows = self._normalize_feed_rows(df.fillna("").to_dict(orient="records"), "keyword_news", end, keyword_tag=item["keyword"])
                    for row in rows:
                        self.add_info_event(**row)
                        results["inserted"] += 1
                        results["channels"]["tushare"]["inserted"] += 1
                except Exception as exc:
                    if self._is_tushare_rate_limit_error(exc):
                        results["errors"].append(f"news:* -> {exc}")
                        news_rate_limited = True
                    else:
                        results["errors"].append(f"news:{item['keyword']} -> {exc}")

            try:
                df = self.market.call_endpoint(tushare_cfg.get("macro_endpoint", "major_news"), start_date=start, end_date=end)
                rows = self._normalize_feed_rows(df.fillna("").to_dict(orient="records"), "macro", end)
                for row in rows:
                    self.add_info_event(**row)
                    results["inserted"] += 1
                    results["channels"]["tushare"]["inserted"] += 1
            except Exception as exc:
                results["errors"].append(f"macro -> {exc}")

        adapters = self._configured_url_adapters()
        if adapters:
            adapter_result = self.url_fetcher.fetch_configured_events(adapters, watchlist, keywords, start, end)
            results["channels"]["url_adapters"]["attempted"] = adapter_result["attempted"]
            results["channels"]["url_adapters"]["adapter_results"] = adapter_result["adapter_results"]
            for row in adapter_result["events"]:
                self.add_info_event(**row)
                results["inserted"] += 1
                results["channels"]["url_adapters"]["inserted"] += 1
            results["errors"].extend(adapter_result["errors"])

        if not self.market and not adapters:
            results["errors"].append("no remote event source configured; enable Tushare or url_sources.adapters")
        return results

    def _watchlist_snapshot(self, trade_date: str) -> list[dict[str, Any]]:
        items = self.list_watchlist(active_only=True)
        snapshots: list[dict[str, Any]] = []
        if not self.market or not self.config.get("notifications", {}).get("include_watchlist_snapshot", True):
            return snapshots
        reference_date = self._soft_trade_day(shift_calendar_date(trade_date, -1))
        for item in items:
            try:
                bar = self.market.latest_bar(item["ts_code"], reference_date)
            except Exception:
                bar = None
            snapshots.append(
                {
                    "ts_code": item["ts_code"],
                    "name": item.get("name") or item["ts_code"],
                    "reference_date": reference_date,
                    "bar": bar,
                }
            )
        return snapshots

    def _priority_rank(self, value: str | None) -> int:
        return 1 if str(value or "").strip().lower() == "high" else 0

    def _normalize_event_identity(self, event: dict[str, Any]) -> str:
        headline = str(event.get("headline") or "").strip().lower()
        headline = re.sub(r"\s+", "", headline)
        headline = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", headline)
        scope = str(event.get("ts_code") or event.get("name") or event.get("event_type") or "")
        return f"{scope}|{headline[:96]}"

    def _dedupe_info_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for event in events:
            key = self._normalize_event_identity(event)
            source = str(event.get("source") or "unknown").strip() or "unknown"
            current = buckets.get(key)
            if current is None:
                item = dict(event)
                item["source_list"] = [source]
                item["source_count"] = 1
                item["duplicate_count"] = 1
                item["merged_event_ids"] = [event.get("event_id")] if event.get("event_id") else []
                buckets[key] = item
                continue
            if source not in current["source_list"]:
                current["source_list"].append(source)
            current["source_count"] = len(current["source_list"])
            current["duplicate_count"] = int(current.get("duplicate_count") or 1) + 1
            if event.get("event_id"):
                current["merged_event_ids"].append(event.get("event_id"))
            should_replace = (
                self._priority_rank(event.get("priority")) > self._priority_rank(current.get("priority"))
                or str(event.get("published_at") or "") > str(current.get("published_at") or "")
            )
            if should_replace:
                preserved_sources = list(current["source_list"])
                merged_ids = list(current["merged_event_ids"])
                duplicate_count = current["duplicate_count"]
                current.clear()
                current.update(dict(event))
                current["source_list"] = preserved_sources
                current["source_count"] = len(preserved_sources)
                current["duplicate_count"] = duplicate_count
                current["merged_event_ids"] = merged_ids
        deduped = list(buckets.values())
        deduped.sort(
            key=lambda item: (
                self._priority_rank(item.get("priority")),
                str(item.get("published_at") or ""),
                str(item.get("created_at") or ""),
            ),
            reverse=True,
        )
        return deduped

    def _group_events_by_source(self, events: list[dict[str, Any]], limit_per_source: int = 6) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            source = str(event.get("source") or "unknown").strip() or "unknown"
            groups.setdefault(source, []).append(event)
        ordered = sorted(
            groups.items(),
            key=lambda item: (
                max(self._priority_rank(event.get("priority")) for event in item[1]),
                len(item[1]),
                item[0],
            ),
            reverse=True,
        )
        result: list[dict[str, Any]] = []
        for source, items in ordered:
            items.sort(
                key=lambda event: (
                    self._priority_rank(event.get("priority")),
                    str(event.get("published_at") or ""),
                ),
                reverse=True,
            )
            result.append(
                {
                    "source": source,
                    "count": len(items),
                    "high_priority_count": sum(1 for event in items if self._priority_rank(event.get("priority")) > 0),
                    "events": items[:limit_per_source],
                }
            )
        return result

    def _format_event_brief_line(self, event: dict[str, Any], include_sources: bool = False) -> str:
        prefix = f"{event.get('name') or event.get('ts_code')}: " if (event.get("name") or event.get("ts_code")) else ""
        label = prefix + str(event.get("headline") or "")
        if include_sources:
            sources = event.get("source_list") or ([event.get("source")] if event.get("source") else [])
            if sources:
                label += f" [{'/'.join(str(item) for item in sources[:3])}]"
        return label.strip()

    def generate_morning_brief(self, trade_date: str | None = None, fetch_events: bool = False) -> dict[str, Any]:
        token = normalize_trade_date(trade_date or self._today())
        fetch_result = None
        if fetch_events:
            try:
                fetch_result = self.fetch_watchlist_events(end_date=token)
            except Exception as exc:
                fetch_result = {"errors": [str(exc)], "inserted": 0}
        events = self.list_info_events(trade_date=token, limit=200)
        deduped_events = self._dedupe_info_events(events)
        high_priority = [item for item in deduped_events if item.get("priority") == "high"]
        normal_priority = [item for item in deduped_events if item.get("priority") != "high"]
        cross_source_events = [item for item in deduped_events if int(item.get("source_count") or 1) > 1]
        source_groups = self._group_events_by_source(deduped_events)
        active_plans = self.list_plans(active_only=True, trade_date=token)
        pending_reviews = self.list_reviews(status="pending", limit=20)
        snapshots = self._watchlist_snapshot(token)
        plan_evolution_reminders: list[dict[str, Any]] = []
        if self.config.get("notifications", {}).get("include_evolution_reminders_in_morning_brief", True):
            for item in active_plans[:10]:
                reminder = self.generate_evolution_reminder(
                    logic_tags=json_loads(item.get("logic_tags_json"), []),
                    market_stage=item.get("market_stage_tag"),
                    environment_tags=json_loads(item.get("environment_tags_json"), []),
                    trade_date=token,
                    write_artifact=False,
                )
                if reminder.get("matched_quality_paths") or reminder.get("matched_reusable_genes") or reminder.get("matched_risk_genes"):
                    plan_evolution_reminders.append(
                        {
                            "plan_id": item.get("plan_id"),
                            "name": item.get("name") or item.get("ts_code"),
                            "reminder": reminder,
                        }
                    )
        markdown_lines = [f"# 每日晨报 | {token}", "", "## 事件概览"]
        markdown_lines.append(f"- 原始事件数: {len(events)}")
        markdown_lines.append(f"- 去重后事件数: {len(deduped_events)}")
        markdown_lines.append(f"- 高优先级事件数: {len(high_priority)}")
        markdown_lines.append(f"- 交叉验证事件数: {len(cross_source_events)}")
        if source_groups:
            markdown_lines.append("- 来源分布: " + "、".join(f"{item['source']}({item['count']})" for item in source_groups[:6]))
        if fetch_result:
            inserted = fetch_result.get("inserted", 0)
            errors = fetch_result.get("errors") or []
            markdown_lines.append(f"- 本轮抓取: 新增 {inserted} 条，错误 {len(errors)} 条")
        markdown_lines.extend(["", "## 必读事项"])
        if high_priority:
            for item in high_priority[:10]:
                markdown_lines.append(f"- {self._format_event_brief_line(item, include_sources=True)}")
        else:
            markdown_lines.append("- 暂无高优先级事件。")
        markdown_lines.extend(["", "## 关注事件"])
        if normal_priority:
            for item in normal_priority[:15]:
                markdown_lines.append(f"- {self._format_event_brief_line(item, include_sources=True)}")
        else:
            markdown_lines.append("- 暂无新增普通事件。")
        if source_groups:
            markdown_lines.extend(["", "## 按来源分组"])
            for group in source_groups[:5]:
                markdown_lines.append(f"- {group['source']}: 共 {group['count']} 条，其中高优先级 {group['high_priority_count']} 条")
                for item in group["events"][:4]:
                    markdown_lines.append(f"  - {self._format_event_brief_line(item, include_sources=False)}")
        if cross_source_events:
            markdown_lines.extend(["", "## 交叉验证事件"])
            for item in cross_source_events[:8]:
                markdown_lines.append(f"- {self._format_event_brief_line(item, include_sources=True)}")
        markdown_lines.extend(["", "## 今日有效计划"])
        if active_plans:
            for item in active_plans:
                markdown_lines.append(
                    f"- {item.get('name') or item['ts_code']}: {item['thesis']} | 买入区间 {item.get('buy_zone') or '-'} | 止损 {item.get('stop_loss') or '-'} | 有效期至 {item.get('valid_to')}"
                )
        else:
            markdown_lines.append("- 今日暂无有效待执行计划。")
        if pending_reviews:
            markdown_lines.extend(["", "## 待处理回顾"])
            for item in pending_reviews[:10]:
                markdown_lines.append(f"- {item.get('name') or item.get('ts_code')}: {item.get('prompt_text') or '已有待处理卖出回顾。'}")
        if plan_evolution_reminders:
            markdown_lines.extend(["", "## 自进化提醒"])
            for item in plan_evolution_reminders[:10]:
                first_line = (item["reminder"].get("reminders") or ["暂无提醒"])[0]
                markdown_lines.append(f"- {item['name']}: {first_line}")
        if snapshots:
            markdown_lines.extend(["", "## 关注池上个交易日快照"])
            for item in snapshots[:20]:
                bar = item.get("bar") or {}
                price = bar.get("close") or "N/A"
                pct = bar.get("pct_chg") or "N/A"
                markdown_lines.append(f"- {item['name']} ({item['ts_code']}): {item['reference_date']} 收盘 {price}，涨跌 {pct}")
        markdown_lines.append("")
        markdown_lines.append("以上内容仅用于信息提醒与纪律辅助，不构成任何交易建议。")
        payload = {
            "trade_date": token,
            "raw_events": events,
            "deduped_events": deduped_events,
            "high_priority_events": high_priority,
            "normal_priority_events": normal_priority,
            "cross_source_events": cross_source_events,
            "source_groups": source_groups,
            "active_plans": active_plans,
            "pending_reviews": pending_reviews,
            "plan_evolution_reminders": plan_evolution_reminders,
            "watchlist_snapshots": snapshots,
            "fetch_result": fetch_result,
        }
        paths = self._write_artifact(token, "morning_brief", payload, "\n".join(markdown_lines).strip() + "\n")
        payload["artifact_paths"] = paths
        return payload

    def capture_market_snapshot(
        self,
        trade_date: str,
        ts_code: str,
        name: str | None = None,
        sector_name: str | None = None,
        sector_change_pct: float | None = None,
    ) -> dict[str, Any] | None:
        if not self.market:
            return None
        snapshot = self.market.build_market_snapshot(trade_date, ts_code=ts_code, name=name, sector_name=sector_name, sector_change_pct=sector_change_pct)
        snapshot_id = make_id("snapshot")
        self.db.execute(
            """
            INSERT INTO market_snapshots(
                snapshot_id, trade_date, ts_code, name, sh_change_pct, cyb_change_pct, up_down_ratio,
                limit_up_count, limit_down_count, sector_name, sector_change_pct, sector_strength_tag,
                raw_payload_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                snapshot["trade_date"],
                snapshot.get("ts_code") or "",
                snapshot.get("name") or "",
                snapshot.get("sh_change_pct"),
                snapshot.get("cyb_change_pct"),
                snapshot.get("up_down_ratio"),
                snapshot.get("limit_up_count"),
                snapshot.get("limit_down_count"),
                snapshot.get("sector_name") or "",
                snapshot.get("sector_change_pct"),
                snapshot.get("sector_strength_tag") or "",
                json_dumps(snapshot.get("raw_payload") or {}),
                now_ts(),
            ),
        )
        snapshot["snapshot_id"] = snapshot_id
        return snapshot

    def _compute_benchmark_return(self, ts_code: str, buy_date: str, sell_date: str) -> float | None:
        if not self.market:
            return None
        try:
            benchmark_entry = self.market.next_trade_date(buy_date, 1)
        except Exception:
            return None
        if benchmark_entry > normalize_trade_date(sell_date):
            return None
        try:
            bars = self.market.get_daily_bars(ts_code, start_date=benchmark_entry, end_date=normalize_trade_date(sell_date))
        except Exception:
            return None
        if not bars:
            return None
        first_bar = bars[0]
        last_bar = bars[-1]
        entry_price = _coalesce_float(first_bar.get("open"))
        exit_price = _coalesce_float(last_bar.get("close"))
        return compute_return_pct(entry_price, exit_price)

    def _compute_holding_days(self, buy_date: str, sell_date: str) -> int | None:
        start = normalize_trade_date(buy_date)
        end = normalize_trade_date(sell_date)
        if start > end:
            return None
        if self.market:
            try:
                days = self.market.trade_days_between(start, end)
                return max(len(days) - 1, 0)
            except Exception:
                pass
        return max((to_date(end) - to_date(start)).days, 0)

    def log_trade(
        self,
        ts_code: str,
        buy_date: str,
        buy_price: float,
        thesis: str,
        name: str | None = None,
        plan_id: str | None = None,
        direction: str = "long",
        buy_reason: str = "",
        buy_position: str = "",
        sell_date: str | None = None,
        sell_price: float | None = None,
        sell_reason: str = "",
        sell_position: str = "",
        position_size_pct: float | None = None,
        logic_type_tags: list[str] | str | None = None,
        pattern_tags: list[str] | str | None = None,
        theme: str | None = None,
        market_stage_tag: str | None = None,
        environment_tags: list[str] | str | None = None,
        emotion_notes: str | None = None,
        mistake_tags: list[str] | str | None = None,
        lessons_learned: str | None = None,
        decision_context: dict[str, Any] | None = None,
        notes: str | None = None,
        fetch_snapshot: bool = False,
        sector_name: str | None = None,
        sector_change_pct: float | None = None,
    ) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        resolved_name = self._resolve_name(code, name)
        trade_id = make_id("trade")
        normalized_buy_date = normalize_trade_date(buy_date)
        normalized_sell_date = normalize_trade_date(sell_date) if sell_date else ""
        plan = self.get_plan(plan_id) if plan_id else None
        snapshot = None
        if fetch_snapshot:
            snapshot = self.capture_market_snapshot(normalized_buy_date, code, name=resolved_name, sector_name=sector_name, sector_change_pct=sector_change_pct)
        actual_return = compute_return_pct(float(buy_price), float(sell_price)) if sell_price is not None else None
        benchmark_return = self._compute_benchmark_return(code, normalized_buy_date, normalized_sell_date) if normalized_sell_date else None
        timing_alpha = round(actual_return - benchmark_return, 2) if actual_return is not None and benchmark_return is not None else None
        holding_days = self._compute_holding_days(normalized_buy_date, normalized_sell_date) if normalized_sell_date else None
        deviation = calculate_plan_execution_deviation(plan, float(buy_price), float(sell_price) if sell_price is not None else None)
        timestamp = now_ts()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO trades(
                    trade_id, plan_id, ts_code, name, direction, thesis, buy_date, buy_price,
                    buy_reason, buy_position, sell_date, sell_price, sell_reason, sell_position,
                    position_size_pct, logic_type_tags_json, pattern_tags_json, theme,
                    market_stage_tag, environment_tags_json, snapshot_id, benchmark_return_pct,
                    actual_return_pct, timing_alpha_pct, holding_days, plan_execution_deviation_json,
                    decision_context_json,
                    review_status, status, emotion_notes, mistake_tags_json, lessons_learned, notes, created_at, updated_at
                ) VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    trade_id,
                    plan_id or "",
                    code,
                    resolved_name,
                    direction,
                    thesis,
                    normalized_buy_date,
                    float(buy_price),
                    buy_reason,
                    buy_position,
                    normalized_sell_date,
                    float(sell_price) if sell_price is not None else None,
                    sell_reason,
                    sell_position,
                    position_size_pct,
                    json_dumps(split_tags(logic_type_tags)),
                    json_dumps(split_tags(pattern_tags)),
                    theme or "",
                    market_stage_tag or "",
                    json_dumps(split_tags(environment_tags)),
                    snapshot.get("snapshot_id") if snapshot else "",
                    benchmark_return,
                    actual_return,
                    timing_alpha,
                    holding_days,
                    json_dumps(deviation),
                    json_dumps(decision_context or {}),
                    "pending",
                    "closed" if normalized_sell_date else "open",
                    emotion_notes or "",
                    json_dumps(split_tags(mistake_tags)),
                    lessons_learned or "",
                    notes or "",
                    timestamp,
                    timestamp,
                ),
            )
        if plan_id:
            self.update_plan_status(plan_id, "executed", trade_id=trade_id)
        trade_row = self.get_trade(trade_id) or {}
        if split_tags(logic_type_tags) or split_tags(pattern_tags) or market_stage_tag or split_tags(environment_tags):
            trade_row["evolution_reminder"] = self.generate_evolution_reminder(
                logic_tags=split_tags(logic_type_tags),
                pattern_tags=split_tags(pattern_tags),
                market_stage=market_stage_tag,
                environment_tags=split_tags(environment_tags),
                trade_date=normalized_buy_date,
                write_artifact=False,
            )
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_trade", True):
            trade_row["vault_note"] = self.export_trade_note(trade_id)
            trade_row["daily_vault_note"] = self.export_daily_note(normalized_buy_date)
        return trade_row

    def close_trade(
        self,
        trade_id: str,
        sell_date: str,
        sell_price: float,
        sell_reason: str = "",
        sell_position: str = "",
        emotion_notes: str | None = None,
        mistake_tags: list[str] | str | None = None,
        lessons_learned: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        trade = self.get_trade(trade_id)
        if not trade:
            raise ValueError(f"trade not found: {trade_id}")
        if trade.get("status") == "closed":
            raise ValueError(f"trade already closed: {trade_id}")
        normalized_sell_date = normalize_trade_date(sell_date)
        benchmark_return = self._compute_benchmark_return(trade["ts_code"], trade["buy_date"], normalized_sell_date)
        actual_return = compute_return_pct(float(trade["buy_price"]), float(sell_price))
        timing_alpha = round(actual_return - benchmark_return, 2) if actual_return is not None and benchmark_return is not None else None
        holding_days = self._compute_holding_days(trade["buy_date"], normalized_sell_date)
        plan = self.get_plan(trade.get("plan_id")) if trade.get("plan_id") else None
        deviation = calculate_plan_execution_deviation(plan, float(trade["buy_price"]), float(sell_price))
        merged_notes = "\n".join(part for part in [trade.get("notes") or "", notes or ""] if part).strip()
        merged_emotion = "\n".join(part for part in [trade.get("emotion_notes") or "", emotion_notes or ""] if part).strip()
        existing_mistakes = split_tags(json.loads(trade.get("mistake_tags_json") or "[]"))
        merged_mistake_tags = existing_mistakes + [tag for tag in split_tags(mistake_tags) if tag not in existing_mistakes]
        merged_lessons = "\n".join(part for part in [trade.get("lessons_learned") or "", lessons_learned or ""] if part).strip()
        self.db.execute(
            """
            UPDATE trades
            SET sell_date = ?, sell_price = ?, sell_reason = ?, sell_position = ?, benchmark_return_pct = ?,
                actual_return_pct = ?, timing_alpha_pct = ?, holding_days = ?, plan_execution_deviation_json = ?,
                status = 'closed', updated_at = ?, emotion_notes = ?, mistake_tags_json = ?, lessons_learned = ?, notes = ?
            WHERE trade_id = ?
            """,
            (
                normalized_sell_date,
                float(sell_price),
                sell_reason,
                sell_position,
                benchmark_return,
                actual_return,
                timing_alpha,
                holding_days,
                json_dumps(deviation),
                now_ts(),
                merged_emotion,
                json_dumps(merged_mistake_tags),
                merged_lessons,
                merged_notes,
                trade_id,
            ),
        )
        trade_row = self.get_trade(trade_id) or {}
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_trade", True):
            trade_row["vault_note"] = self.export_trade_note(trade_id)
            trade_row["daily_vault_note"] = self.export_daily_note(normalized_sell_date)
        return trade_row

    def enrich_trade_from_text(
        self,
        trade_id: str,
        text: str,
        trade_date: str | None = None,
        lookback_days: int = 365,
    ) -> dict[str, Any]:
        trade = self.get_trade(trade_id)
        if not trade:
            raise ValueError(f"trade not found: {trade_id}")
        anchor_date = normalize_trade_date(trade_date or trade.get("sell_date") or trade.get("buy_date") or self._today())
        before_fields = self._trade_to_journal_fields(trade)
        merged_fields, parsed = self._merge_journal_reply(before_fields, text, mode="trade", trade_date=anchor_date, current_missing=[])
        merged_fields["ts_code"] = trade.get("ts_code") or merged_fields.get("ts_code") or ""
        merged_fields["name"] = trade.get("name") or merged_fields.get("name") or ""
        market_stage = self._pick_market_stage(merged_fields.get("environment_tags"), fallback=trade.get("market_stage_tag") or "")
        normalized_buy_date = normalize_trade_date(merged_fields.get("buy_date") or trade.get("buy_date") or anchor_date)
        normalized_sell_date = normalize_trade_date(merged_fields.get("sell_date")) if merged_fields.get("sell_date") else ""
        buy_price = _coalesce_float(merged_fields.get("buy_price"))
        sell_price = _coalesce_float(merged_fields.get("sell_price"))
        plan = self.get_plan(trade.get("plan_id")) if trade.get("plan_id") else None
        benchmark_return = self._compute_benchmark_return(merged_fields["ts_code"], normalized_buy_date, normalized_sell_date) if normalized_sell_date else None
        actual_return = compute_return_pct(buy_price, sell_price) if buy_price is not None and sell_price is not None else None
        timing_alpha = round(actual_return - benchmark_return, 2) if actual_return is not None and benchmark_return is not None else None
        holding_days = self._compute_holding_days(normalized_buy_date, normalized_sell_date) if normalized_sell_date else None
        deviation = calculate_plan_execution_deviation(plan, buy_price, sell_price if sell_price is not None else None)
        decision_context = self._decision_context_from_fields(
            merged_fields,
            "closed_trade" if normalized_sell_date else "open_trade",
            base_context=json_loads(trade.get("decision_context_json"), {}) or {},
        )
        self.db.execute(
            """
            UPDATE trades
            SET thesis = ?, buy_date = ?, buy_price = ?, sell_date = ?, sell_price = ?, position_size_pct = ?,
                logic_type_tags_json = ?, pattern_tags_json = ?, market_stage_tag = ?, environment_tags_json = ?,
                benchmark_return_pct = ?, actual_return_pct = ?, timing_alpha_pct = ?, holding_days = ?,
                plan_execution_deviation_json = ?, decision_context_json = ?, status = ?, emotion_notes = ?, mistake_tags_json = ?,
                lessons_learned = ?, notes = ?, updated_at = ?
            WHERE trade_id = ?
            """,
            (
                merged_fields.get("thesis") or trade.get("thesis") or "",
                normalized_buy_date,
                buy_price,
                normalized_sell_date,
                sell_price,
                merged_fields.get("position_size_pct"),
                json_dumps(split_tags(merged_fields.get("logic_tags", []))),
                json_dumps(split_tags(merged_fields.get("pattern_tags", []))),
                market_stage,
                json_dumps(split_tags(merged_fields.get("environment_tags", []))),
                benchmark_return,
                actual_return,
                timing_alpha,
                holding_days,
                json_dumps(deviation),
                json_dumps(decision_context),
                "closed" if normalized_sell_date else "open",
                merged_fields.get("emotion_notes") or "",
                json_dumps(split_tags(merged_fields.get("mistake_tags", []))),
                merged_fields.get("lessons_learned") or "",
                merged_fields.get("notes") or "",
                now_ts(),
                trade_id,
            ),
        )
        updated_trade = self.get_trade(trade_id) or {}
        journal_kind = "closed_trade" if normalized_sell_date else "open_trade"
        reflection_prompts = build_reflection_prompts(merged_fields, journal_kind, [])
        response = {
            "trade": updated_trade,
            "parsed": parsed,
            "updated_fields": self._changed_field_names(
                before_fields,
                merged_fields,
                [
                    "thesis",
                    "logic_tags",
                    "pattern_tags",
                    "environment_tags",
                    "user_focus",
                    "observed_signals",
                    "position_reason",
                    "position_confidence",
                    "stress_level",
                    "mistake_tags",
                    "emotion_notes",
                    "lessons_learned",
                    "position_size_pct",
                    "buy_date",
                    "buy_price",
                    "sell_date",
                    "sell_price",
                    "notes",
                ],
            ),
            "standardized_record": build_standardized_record(merged_fields, journal_kind),
            "reflection_prompts": reflection_prompts,
            "polling_bundle": build_polling_bundle(
                merged_fields,
                journal_kind,
                [],
                [],
                reflection_prompts=reflection_prompts,
            ),
        }
        if json_loads(updated_trade.get("logic_type_tags_json"), []) or json_loads(updated_trade.get("pattern_tags_json"), []) or updated_trade.get("market_stage_tag") or json_loads(updated_trade.get("environment_tags_json"), []):
            response["evolution_reminder"] = self.generate_evolution_reminder(
                logic_tags=json_loads(updated_trade.get("logic_type_tags_json"), []),
                pattern_tags=json_loads(updated_trade.get("pattern_tags_json"), []),
                market_stage=updated_trade.get("market_stage_tag"),
                environment_tags=json_loads(updated_trade.get("environment_tags_json"), []),
                trade_date=anchor_date,
                lookback_days=lookback_days,
                write_artifact=False,
            )
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_trade", True):
            response["vault_note"] = self.export_trade_note(trade_id)
            response["daily_vault_note"] = self.export_daily_note(normalized_sell_date or normalized_buy_date)
        return response

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        return self.db.fetchone("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))

    def list_trades(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT * FROM trades WHERE 1 = 1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY COALESCE(sell_date, buy_date) DESC, updated_at DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        return self.db.fetchall(sql, tuple(params))

    def _statement_row_value(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return str(row.get(key) or "").strip()
        return ""

    def _statement_row_float(self, row: dict[str, Any], *keys: str) -> float | None:
        raw = self._statement_row_value(row, *keys)
        if not raw:
            return None
        cleaned = raw.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _normalize_statement_row(self, row: dict[str, Any], default_trade_date: str | None = None) -> dict[str, Any]:
        side = self._statement_row_value(row, "side", "direction", "买卖标志", "成交方向").lower()
        generic_date = self._statement_row_value(row, "trade_date", "成交日期", "date", "成交时间")
        generic_price = self._statement_row_float(row, "trade_price", "成交价格", "成交均价", "price", "均价", "成交价")
        buy_date = self._statement_row_value(row, "buy_date", "买入日期", "开仓日期", "买入成交日期")
        sell_date = self._statement_row_value(row, "sell_date", "卖出日期", "平仓日期", "卖出成交日期")
        buy_price = self._statement_row_float(row, "buy_price", "买入价格", "开仓均价", "买入均价", "买入成交价")
        sell_price = self._statement_row_float(row, "sell_price", "卖出价格", "平仓均价", "卖出均价", "卖出成交价")

        if not buy_date and not sell_date and generic_date:
            if any(token in side for token in ("buy", "买")):
                buy_date = generic_date
                buy_price = buy_price if buy_price is not None else generic_price
            elif any(token in side for token in ("sell", "卖")):
                sell_date = generic_date
                sell_price = sell_price if sell_price is not None else generic_price
            else:
                buy_date = generic_date
                buy_price = buy_price if buy_price is not None else generic_price

        ts_code_raw = self._statement_row_value(row, "ts_code", "code", "symbol", "证券代码", "股票代码", "代码")
        name = self._statement_row_value(row, "name", "证券名称", "股票名称", "名称")
        ts_code = normalize_ts_code(ts_code_raw) if ts_code_raw else ""
        quantity = self._statement_row_float(row, "quantity", "qty", "成交数量", "数量")
        amount = self._statement_row_float(row, "amount", "成交金额", "金额")
        fee = self._statement_row_float(row, "fee", "手续费", "佣金", "税费")
        note_parts = [
            "[statement-import]",
            f"side={side or '-'}",
        ]
        if quantity is not None:
            note_parts.append(f"quantity={quantity}")
        if amount is not None:
            note_parts.append(f"amount={amount}")
        if fee is not None:
            note_parts.append(f"fee={fee}")
        note_parts.append(self._statement_row_value(row, "note", "notes", "备注", "说明"))
        notes = " | ".join(part for part in note_parts if part and part != " | ")

        trade_date = normalize_trade_date(default_trade_date or buy_date or sell_date or generic_date or self._today())
        normalized = {
            "ts_code": ts_code,
            "name": name,
            "buy_date": normalize_trade_date(buy_date or trade_date) if buy_date else "",
            "buy_price": buy_price,
            "sell_date": normalize_trade_date(sell_date) if sell_date else "",
            "sell_price": sell_price,
            "quantity": quantity,
            "amount": amount,
            "fee": fee,
            "notes": notes,
            "source_row": row,
        }
        if normalized["buy_date"] and normalized["sell_date"]:
            normalized["journal_kind"] = "closed_trade"
        elif normalized["buy_date"] and normalized["buy_price"] is not None:
            normalized["journal_kind"] = "open_trade"
        elif normalized["sell_date"] and normalized["sell_price"] is not None:
            normalized["journal_kind"] = "close_only"
        else:
            normalized["journal_kind"] = "invalid"
        return normalized

    def _trade_price_matches(self, left: Any, right: Any, tolerance: float = 1e-6) -> bool:
        left_value = _coalesce_float(left)
        right_value = _coalesce_float(right)
        if left_value is None or right_value is None:
            return False
        return abs(left_value - right_value) <= tolerance

    def _find_statement_trade_matches(self, normalized: dict[str, Any]) -> list[dict[str, Any]]:
        ts_code = normalized.get("ts_code") or ""
        if not ts_code:
            return []
        candidates = self.db.fetchall(
            "SELECT * FROM trades WHERE ts_code = ? ORDER BY updated_at DESC LIMIT 50",
            (ts_code,),
        )
        matches: list[dict[str, Any]] = []
        for trade in candidates:
            if normalized.get("buy_date") and trade.get("buy_date") != normalized.get("buy_date"):
                continue
            if normalized.get("buy_price") is not None and not self._trade_price_matches(trade.get("buy_price"), normalized.get("buy_price")):
                continue
            if normalized.get("sell_date") and trade.get("sell_date") != normalized.get("sell_date"):
                continue
            if normalized.get("sell_price") is not None and trade.get("sell_date") and not self._trade_price_matches(trade.get("sell_price"), normalized.get("sell_price")):
                continue
            matches.append(trade)
        return matches

    def _statement_follow_up_payload(self, trade_row: dict[str, Any]) -> dict[str, Any]:
        fields = self._trade_to_journal_fields(trade_row)
        journal_kind = "closed_trade" if trade_row.get("sell_date") else "open_trade"
        evaluation = evaluate_journal_fields(fields, journal_kind)
        reflection_prompts = build_reflection_prompts(fields, journal_kind, evaluation["missing_fields"])
        return {
            "trade_id": trade_row.get("trade_id") or "",
            "journal_kind": journal_kind,
            "standardized_record": build_standardized_record(fields, journal_kind),
            "missing_fields": evaluation["missing_fields"],
            "follow_up_questions": evaluation["follow_up_questions"],
            "reflection_prompts": reflection_prompts,
            "polling_bundle": build_polling_bundle(
                fields,
                journal_kind,
                evaluation["missing_fields"],
                evaluation["follow_up_questions"],
                reflection_prompts=reflection_prompts,
            ),
            "fact_alignment": {
                "ts_code": trade_row.get("ts_code") or "",
                "buy_date": trade_row.get("buy_date") or "",
                "buy_price": trade_row.get("buy_price"),
                "sell_date": trade_row.get("sell_date") or "",
                "sell_price": trade_row.get("sell_price"),
            },
            "assistant_message": (
                f"已根据交割单对齐 {trade_row.get('name') or trade_row.get('ts_code')} 的价格与日期。"
                f" 下一步建议补：{(evaluation['follow_up_questions'][0] if evaluation['follow_up_questions'] else '选股原因 / 触发信号 / 仓位理由')}。"
            ),
        }

    def import_statement_file(
        self,
        statement_path: str,
        *,
        trade_date: str | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        path = Path(statement_path)
        if not path.exists():
            raise FileNotFoundError(f"statement file not found: {path}")
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                rows = payload.get("rows") or payload.get("items") or []
            else:
                rows = payload
        else:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        if not isinstance(rows, list):
            raise ValueError("statement payload must be a list of row objects")

        imported_items: list[dict[str, Any]] = []
        normalized_trade_date = normalize_trade_date(trade_date or self._today())
        for index, raw_row in enumerate(rows, start=1):
            row = dict(raw_row or {})
            normalized = self._normalize_statement_row(row, default_trade_date=normalized_trade_date)
            if not normalized.get("ts_code"):
                imported_items.append(
                    {
                        "row_index": index,
                        "status": "invalid",
                        "reason": "missing_ts_code",
                        "normalized_row": normalized,
                    }
                )
                continue
            if normalized.get("journal_kind") == "invalid":
                imported_items.append(
                    {
                        "row_index": index,
                        "status": "invalid",
                        "reason": "missing_required_trade_facts",
                        "normalized_row": normalized,
                    }
                )
                continue

            if normalized["journal_kind"] in {"open_trade", "closed_trade"}:
                exact_matches = self._find_statement_trade_matches(normalized)
                exact_trade = next(
                    (
                        item
                        for item in exact_matches
                        if (
                            (normalized["journal_kind"] == "open_trade" and not item.get("sell_date"))
                            or (
                                normalized["journal_kind"] == "closed_trade"
                                and item.get("sell_date") == normalized.get("sell_date")
                                and self._trade_price_matches(item.get("sell_price"), normalized.get("sell_price"))
                            )
                        )
                    ),
                    None,
                )
                if exact_trade:
                    follow_up = self._statement_follow_up_payload(exact_trade)
                    imported_items.append(
                        {
                            "row_index": index,
                            "status": "matched_existing",
                            "trade_id": exact_trade.get("trade_id") or "",
                            "trade": exact_trade,
                            "normalized_row": normalized,
                            "follow_up": follow_up,
                        }
                    )
                    continue

                if normalized["journal_kind"] == "closed_trade":
                    open_candidates = [
                        item for item in exact_matches if not item.get("sell_date") and not item.get("sell_price")
                    ]
                    if len(open_candidates) == 1:
                        closed_trade = self.close_trade(
                            open_candidates[0]["trade_id"],
                            sell_date=normalized["sell_date"],
                            sell_price=float(normalized["sell_price"]),
                            notes=normalized.get("notes") or "",
                        )
                        follow_up = self._statement_follow_up_payload(closed_trade)
                        imported_items.append(
                            {
                                "row_index": index,
                                "status": "closed_existing",
                                "trade_id": closed_trade.get("trade_id") or "",
                                "trade": closed_trade,
                                "normalized_row": normalized,
                                "follow_up": follow_up,
                            }
                        )
                        continue

                trade_row = self.log_trade(
                    ts_code=normalized["ts_code"],
                    name=normalized.get("name") or None,
                    buy_date=normalized["buy_date"],
                    buy_price=float(normalized["buy_price"]),
                    sell_date=normalized.get("sell_date") or None,
                    sell_price=float(normalized["sell_price"]) if normalized.get("sell_price") is not None else None,
                    thesis="",
                    notes=normalized.get("notes") or "",
                )
                follow_up = self._statement_follow_up_payload(trade_row)
                imported_items.append(
                    {
                        "row_index": index,
                        "status": "imported_new",
                        "trade_id": trade_row.get("trade_id") or "",
                        "trade": trade_row,
                        "normalized_row": normalized,
                        "follow_up": follow_up,
                    }
                )
                continue

            open_candidates = self._open_trade_candidates(normalized["ts_code"])
            if len(open_candidates) == 1:
                closed_trade = self.close_trade(
                    open_candidates[0]["trade_id"],
                    sell_date=normalized["sell_date"],
                    sell_price=float(normalized["sell_price"]),
                    notes=normalized.get("notes") or "",
                )
                follow_up = self._statement_follow_up_payload(closed_trade)
                imported_items.append(
                    {
                        "row_index": index,
                        "status": "closed_existing",
                        "trade_id": closed_trade.get("trade_id") or "",
                        "trade": closed_trade,
                        "normalized_row": normalized,
                        "follow_up": follow_up,
                    }
                )
            else:
                imported_items.append(
                    {
                        "row_index": index,
                        "status": "needs_manual_match",
                        "reason": "open_trade_not_resolved",
                        "normalized_row": normalized,
                        "candidates": [
                            {
                                "trade_id": item.get("trade_id"),
                                "name": item.get("name") or item.get("ts_code"),
                                "buy_date": item.get("buy_date"),
                                "buy_price": item.get("buy_price"),
                            }
                            for item in open_candidates[:5]
                        ],
                    }
                )

        summary = {
            "total_rows": len(rows),
            "imported_new": sum(1 for item in imported_items if item.get("status") == "imported_new"),
            "matched_existing": sum(1 for item in imported_items if item.get("status") == "matched_existing"),
            "closed_existing": sum(1 for item in imported_items if item.get("status") == "closed_existing"),
            "needs_manual_match": sum(1 for item in imported_items if item.get("status") == "needs_manual_match"),
            "invalid": sum(1 for item in imported_items if item.get("status") == "invalid"),
        }
        follow_up_queue = [
            {
                "trade_id": item.get("trade_id") or "",
                "status": item.get("status") or "",
                "journal_kind": (item.get("follow_up") or {}).get("journal_kind") or "",
                "next_question": ((item.get("follow_up") or {}).get("polling_bundle") or {}).get("next_question") or "",
                "assistant_message": (item.get("follow_up") or {}).get("assistant_message") or "",
            }
            for item in imported_items
            if isinstance(item.get("follow_up"), dict)
        ]
        if len(follow_up_queue) == 1:
            assistant_message = follow_up_queue[0]["assistant_message"] or "已完成交割单对齐，下一步可继续补充主观轨迹。"
        else:
            assistant_message = (
                "交割单已完成事实对齐："
                f" 新增 {summary['imported_new']} 条，匹配已有 {summary['matched_existing']} 条，"
                f"补全平仓 {summary['closed_existing']} 条。"
            )
        payload: dict[str, Any] = {
            "route": "statement_import",
            "statement_path": str(path),
            "summary": summary,
            "items": imported_items,
            "follow_up_queue": follow_up_queue,
            "assistant_message": assistant_message,
            "pending_question": follow_up_queue[0]["next_question"] if len(follow_up_queue) == 1 else "",
        }

        successful_items = [item for item in imported_items if item.get("trade_id")]
        if session_key and len(successful_items) == 1:
            target = successful_items[0]
            follow_up = target.get("follow_up") or {}
            next_memory = self._update_session_memory_from_fields(
                {},
                self._trade_to_journal_fields(target.get("trade") or {}),
                trade_date=normalize_trade_date((target.get("trade") or {}).get("buy_date") or normalized_trade_date),
                journal_kind=follow_up.get("journal_kind") or "open_trade",
            )
            self._upsert_session_thread(
                session_key,
                active_draft_id="",
                active_entity_kind="trade",
                active_entity_id=target.get("trade_id") or "",
                active_mode="trade",
                trade_date=normalize_trade_date((target.get("trade") or {}).get("buy_date") or normalized_trade_date),
                last_user_text=f"statement import: {path.name}",
                last_assistant_text=follow_up.get("assistant_message") or "",
                last_route="statement_import",
                last_result=payload,
                memory=next_memory,
            )
            payload["session_state"] = self._build_session_state_payload(session_key)
        return payload

    def _evolution_source_rows(self, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        trades = self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'closed' AND buy_date >= ? AND buy_date <= ? ORDER BY sell_date DESC, buy_date DESC",
            (start_date, end_date),
        )
        reviews = self.db.fetchall(
            "SELECT * FROM reviews WHERE sell_date >= ? AND sell_date <= ? ORDER BY review_due_date DESC, sell_date DESC",
            (start_date, end_date),
        )
        return trades, reviews

    def generate_evolution_report(
        self,
        lookback_days: int = 365,
        trade_date: str | None = None,
        min_samples: int = 2,
        write_artifact: bool = True,
    ) -> dict[str, Any]:
        end_date = normalize_trade_date(trade_date or self._today())
        start_date = shift_calendar_date(end_date, -int(lookback_days))
        trades, reviews = self._evolution_source_rows(start_date, end_date)
        payload = build_evolution_report(
            trades,
            reviews=reviews,
            lookback_days=int(lookback_days),
            min_samples=int(min_samples),
        )
        payload["period_start"] = start_date
        payload["period_end"] = end_date
        if write_artifact:
            stem = f"evolution_report_{start_date}_{end_date}"
            payload["artifact_paths"] = self._write_artifact(end_date, stem, payload, payload.get("markdown"))
        return payload

    def generate_evolution_reminder(
        self,
        logic_tags: list[str] | str | None = None,
        pattern_tags: list[str] | str | None = None,
        market_stage: str | None = None,
        environment_tags: list[str] | str | None = None,
        lookback_days: int = 365,
        trade_date: str | None = None,
        min_samples: int = 2,
        write_artifact: bool = False,
    ) -> dict[str, Any]:
        end_date = normalize_trade_date(trade_date or self._today())
        start_date = shift_calendar_date(end_date, -int(lookback_days))
        trades, reviews = self._evolution_source_rows(start_date, end_date)
        payload = build_evolution_reminder(
            trades,
            reviews=reviews,
            logic_tags=split_tags(logic_tags),
            pattern_tags=split_tags(pattern_tags),
            market_stage=market_stage,
            environment_tags=split_tags(environment_tags),
            lookback_days=int(lookback_days),
            min_samples=int(min_samples),
        )
        payload["period_start"] = start_date
        payload["period_end"] = end_date
        if write_artifact:
            stem = "evolution_reminder_" + safe_filename(
                "_".join(split_tags(logic_tags) + split_tags(pattern_tags) + split_tags(environment_tags) + ([market_stage] if market_stage else []))
                or "query"
            )
            payload["artifact_paths"] = self._write_artifact(end_date, stem, payload, payload.get("markdown"))
        return payload

    def generate_style_portrait(
        self,
        lookback_days: int = 365,
        trade_date: str | None = None,
        min_samples: int = 2,
        write_artifact: bool = True,
    ) -> dict[str, Any]:
        end_date = normalize_trade_date(trade_date or self._today())
        start_date = shift_calendar_date(end_date, -int(lookback_days))
        trades, reviews = self._evolution_source_rows(start_date, end_date)
        payload = build_style_portrait(
            trades,
            reviews=reviews,
            lookback_days=int(lookback_days),
            min_samples=int(min_samples),
        )
        payload["period_start"] = start_date
        payload["period_end"] = end_date
        if write_artifact:
            stem = f"style_portrait_{start_date}_{end_date}"
            payload["artifact_paths"] = self._write_artifact(end_date, stem, payload, payload.get("markdown"))
        return payload

    def generate_reference(
        self,
        logic_tags: list[str] | str | None = None,
        market_stage: str | None = None,
        environment_tags: list[str] | str | None = None,
        lookback_days: int = 365,
        trade_date: str | None = None,
        write_artifact: bool = True,
    ) -> dict[str, Any]:
        end_date = normalize_trade_date(trade_date or self._today())
        start_date = shift_calendar_date(end_date, -int(lookback_days))
        trades = self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'closed' AND buy_date >= ? AND buy_date <= ? ORDER BY sell_date DESC, buy_date DESC",
            (start_date, end_date),
        )
        payload = build_reference_report(trades, split_tags(logic_tags), market_stage, split_tags(environment_tags), int(lookback_days))
        if write_artifact:
            stem = "plan_reference_" + safe_filename("_".join(split_tags(logic_tags)) or market_stage or "all")
            payload["artifact_paths"] = self._write_artifact(end_date, stem, payload, payload.get("markdown"))
        return payload

    def _review_due_date(self, sell_date: str, review_window_days: int) -> str:
        token = normalize_trade_date(sell_date)
        if self.market:
            try:
                return self.market.next_trade_date(token, int(review_window_days))
            except Exception:
                pass
        return shift_calendar_date(token, int(review_window_days))

    def run_review_cycle(self, as_of_date: str | None = None) -> dict[str, Any]:
        token = normalize_trade_date(as_of_date or self._today())
        review_window = int(self.config.get("monitoring", {}).get("review_window_days", 5))
        sell_fly_threshold = float(self.config.get("monitoring", {}).get("sell_fly_threshold_pct", 8.0))
        escape_top_threshold = float(self.config.get("monitoring", {}).get("escape_top_threshold_pct", 8.0))
        candidates = self.db.fetchall(
            """
            SELECT * FROM trades
            WHERE status = 'closed'
              AND sell_date IS NOT NULL
              AND trade_id NOT IN (SELECT trade_id FROM reviews)
            ORDER BY sell_date ASC, trade_id ASC
            """
        )
        created: list[dict[str, Any]] = []
        skipped: list[str] = []
        for trade in candidates:
            due_date = self._review_due_date(trade["sell_date"], review_window)
            if due_date > token:
                continue
            if not self.market:
                skipped.append(f"{trade['trade_id']}: market data disabled")
                continue
            try:
                start = self.market.next_trade_date(trade["sell_date"], 1)
                bars = self.market.get_daily_bars(trade["ts_code"], start_date=start, end_date=due_date)
            except Exception as exc:
                skipped.append(f"{trade['trade_id']}: {exc}")
                continue
            if not bars:
                skipped.append(f"{trade['trade_id']}: no bars in review window")
                continue
            sell_price = float(trade["sell_price"])
            high_price = max(_coalesce_float(item.get("high")) or sell_price for item in bars)
            low_price = min(_coalesce_float(item.get("low")) or sell_price for item in bars)
            max_gain = compute_return_pct(sell_price, high_price)
            max_drawdown = compute_return_pct(sell_price, low_price)
            review_type = "flat"
            triggered = 0
            prompt = "走势平淡，本次不触发额外回顾。"
            if max_gain is not None and max_gain > sell_fly_threshold:
                review_type = "sell_fly"
                triggered = 1
                prompt = (
                    f"您于 {trade['sell_date']} 卖出 {trade.get('name') or trade['ts_code']}，"
                    f"此后 {review_window} 个交易日最高涨到 {high_price:.2f}（较卖出价 {max_gain:.2f}%）。"
                    f"当时卖出理由：{trade.get('sell_reason') or '未填写'}。"
                )
            elif max_drawdown is not None and max_drawdown < -escape_top_threshold:
                review_type = "good_exit"
                triggered = 1
                prompt = (
                    f"您于 {trade['sell_date']} 卖出 {trade.get('name') or trade['ts_code']} 后，"
                    f"此后 {review_window} 个交易日最低回撤 {max_drawdown:.2f}%，本次卖出属于有效保护。"
                )
            review_id = make_id("review")
            now_value = now_ts()
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO reviews(
                        review_id, trade_id, ts_code, name, sell_date, review_due_date, review_window_days,
                        sell_price, highest_price, lowest_price, max_gain_pct, max_drawdown_pct,
                        review_type, triggered_flag, feedback, weight_action, status, prompt_text,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        trade["trade_id"],
                        trade["ts_code"],
                        trade.get("name") or "",
                        trade["sell_date"],
                        due_date,
                        review_window,
                        sell_price,
                        high_price,
                        low_price,
                        max_gain,
                        max_drawdown,
                        review_type,
                        triggered,
                        "",
                        "",
                        "pending" if triggered else "flat",
                        prompt,
                        now_value,
                        now_value,
                    ),
                )
                conn.execute(
                    "UPDATE trades SET review_status = ?, updated_at = ? WHERE trade_id = ?",
                    ("generated" if triggered else "flat", now_value, trade["trade_id"]),
                )
            created.append(self.db.fetchone("SELECT * FROM reviews WHERE review_id = ?", (review_id,)) or {})
        payload = {"as_of_date": token, "created_reviews": created, "skipped": skipped}
        payload["artifact_paths"] = self._write_artifact(token, "review_cycle", payload, None)
        if self._vault_enabled() and created:
            payload["vault_notes"] = [self.export_review_note(item["review_id"]) for item in created if item.get("review_id")]
            payload["daily_vault_note"] = self.export_daily_note(token)
        return payload

    def list_reviews(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT * FROM reviews WHERE 1 = 1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY review_due_date DESC, created_at DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        return self.db.fetchall(sql, tuple(params))

    def respond_review(self, review_id: str, feedback: str, weight_action: str = "") -> dict[str, Any]:
        review = self.db.fetchone("SELECT * FROM reviews WHERE review_id = ?", (review_id,))
        if not review:
            raise ValueError(f"review not found: {review_id}")
        self.db.execute(
            "UPDATE reviews SET feedback = ?, weight_action = ?, status = 'answered', updated_at = ? WHERE review_id = ?",
            (feedback, weight_action, now_ts(), review_id),
        )
        review_row = self.db.fetchone("SELECT * FROM reviews WHERE review_id = ?", (review_id,)) or {}
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_review", True):
            review_row["vault_note"] = self.export_review_note(review_id)
            review_row["daily_vault_note"] = self.export_daily_note(review_row.get("review_due_date") or review_row.get("sell_date") or self._today())
        return review_row

    def generate_health_report(self, period_start: str, period_end: str, period_kind: str = "custom") -> dict[str, Any]:
        start = normalize_trade_date(period_start)
        end = normalize_trade_date(period_end)
        plans = self.db.fetchall(
            "SELECT * FROM plans WHERE valid_to >= ? AND valid_from <= ? ORDER BY valid_from ASC",
            (start, end),
        )
        trades = self.db.fetchall(
            "SELECT * FROM trades WHERE status = 'closed' AND sell_date >= ? AND sell_date <= ? ORDER BY sell_date ASC",
            (start, end),
        )
        reviews = self.db.fetchall(
            "SELECT * FROM reviews WHERE review_due_date >= ? AND review_due_date <= ? ORDER BY review_due_date ASC",
            (start, end),
        )
        payload = generate_health_report_payload(plans, trades, reviews, start, end)
        report_id = make_id("health")
        markdown = payload.pop("markdown")
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO health_reports(report_id, period_kind, period_start, period_end, report_markdown, report_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (report_id, period_kind, start, end, markdown, json.dumps(payload, ensure_ascii=False), now_ts()),
            )
        payload["report_id"] = report_id
        payload["period_kind"] = period_kind
        payload["artifact_paths"] = self._write_artifact(end, f"health_report_{period_kind}_{start}_{end}", payload, markdown)
        payload["markdown"] = markdown
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_health_report", True):
            payload["vault_note"] = self.export_report_note(report_id)
            payload["dashboard_vault_note"] = self.export_dashboard_note()
        return payload

    def _slot_exists(self, slot_key: str) -> bool:
        return self.db.fetchone("SELECT slot_key FROM schedule_runs WHERE slot_key = ?", (slot_key,)) is not None

    def _record_slot(self, slot_key: str, artifact_path: str = "", notes: str = "") -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO schedule_runs(slot_key, last_run_at, artifact_path, notes) VALUES(?, ?, ?, ?)",
                (slot_key, now_ts(), artifact_path, notes),
            )

    def _is_trade_day(self, trade_date: str) -> bool:
        if self.market:
            try:
                return self.market.is_trade_day(trade_date)
            except Exception:
                pass
        return to_date(trade_date).weekday() < 5

    def _first_trade_day_of_month(self, trade_date: str) -> bool:
        first_calendar_day = f"{trade_date[:4]}{trade_date[4:6]}01"
        if self.market:
            try:
                days = self.market.get_trade_calendar(first_calendar_day, shift_calendar_date(first_calendar_day, 10), is_open=1)
                return bool(days) and days[0] == trade_date
            except Exception:
                pass
        return trade_date[-2:] == "01"

    def _schedule_time_list(self, value: Any) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, (list, tuple, set)):
            items = [str(item).strip() for item in value]
        else:
            items = [item.strip() for item in str(value).split(",")]
        result = [item for item in items if re.fullmatch(r"\d{2}:\d{2}", item)]
        return sorted(dict.fromkeys(result))

    def run_schedule(self, now: str | None = None, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
        current = datetime.strptime(now, "%Y-%m-%dT%H:%M") if now else datetime.now()
        today = current.strftime("%Y%m%d")
        if not self._is_trade_day(today):
            return {"now": current.isoformat(timespec="minutes"), "actions": [], "message": "today is not a trade day"}
        actions: list[dict[str, Any]] = []
        schedules = self.config.get("schedules", {})
        current_hhmm = current.strftime("%H:%M")
        has_remote_event_source = bool(self.market or self._configured_url_adapters())
        if has_remote_event_source:
            for slot_time in self._schedule_time_list(schedules.get("event_fetch_times", [])):
                if current_hhmm >= slot_time:
                    actions.append(
                        {
                            "slot": f"event_fetch:{today}:{slot_time.replace(':', '')}",
                            "kind": "event_fetch",
                            "trade_date": today,
                            "scheduled_time": slot_time,
                        }
                    )
        if current_hhmm >= str(schedules.get("morning_brief_time", "08:00")):
            actions.append(
                {
                    "slot": f"morning_brief:{today}",
                    "kind": "morning_brief",
                    "fetch_events": bool(schedules.get("fetch_events_before_morning_brief", False) and has_remote_event_source),
                }
            )
        if current_hhmm >= str(schedules.get("review_run_time", "17:30")):
            actions.append({"slot": f"review_cycle:{today}", "kind": "review_cycle"})
        if current_hhmm >= str(schedules.get("health_report_time", "08:10")) and self._first_trade_day_of_month(today):
            first_day_of_month = datetime.strptime(f"{today[:4]}-{today[4:6]}-01", "%Y-%m-%d")
            previous_month_end_dt = first_day_of_month - timedelta(days=1)
            previous_month_end = previous_month_end_dt.strftime("%Y%m%d")
            previous_month_start = previous_month_end_dt.strftime("%Y%m") + "01"
            actions.append(
                {
                    "slot": f"health_report:{previous_month_end}",
                    "kind": "health_report",
                    "period_start": previous_month_start,
                    "period_end": previous_month_end,
                }
            )
        if dry_run:
            return {"now": current.isoformat(timespec="minutes"), "actions": actions, "dry_run": True}
        executed: list[dict[str, Any]] = []
        for item in actions:
            if not force and self._slot_exists(item["slot"]):
                continue
            if item["kind"] == "event_fetch":
                result = self.fetch_watchlist_events(end_date=item.get("trade_date") or today)
                artifact_paths = self._write_artifact(today, f"event_poll_{item['slot'].replace(':', '_')}", result)
                artifact = artifact_paths.get("json") or ""
            elif item["kind"] == "morning_brief":
                result = self.generate_morning_brief(trade_date=today, fetch_events=bool(item.get("fetch_events")))
                artifact = result.get("artifact_paths", {}).get("markdown") or result.get("artifact_paths", {}).get("json") or ""
            elif item["kind"] == "review_cycle":
                result = self.run_review_cycle(as_of_date=today)
                artifact = result.get("artifact_paths", {}).get("json") or ""
            else:
                result = self.generate_health_report(item["period_start"], item["period_end"], period_kind="monthly")
                artifact = result.get("artifact_paths", {}).get("markdown") or result.get("artifact_paths", {}).get("json") or ""
            self._record_slot(item["slot"], artifact_path=artifact, notes=item["kind"])
            executed.append({"slot": item["slot"], "kind": item["kind"], "artifact": artifact})
        return {"now": current.isoformat(timespec="minutes"), "actions": executed}


def create_app(anchor_path: Path, runtime_root: str | None = None, enable_market_data: bool = True) -> FinanceJournalApp:
    skill_root = Path(anchor_path).resolve().parents[1]
    repo_root = skill_root.parent
    return FinanceJournalApp(repo_root, skill_root, runtime_root=runtime_root, enable_market_data=enable_market_data)
