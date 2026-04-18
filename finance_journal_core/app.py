from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
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
    MISTAKE_RULES,
    build_completeness_report,
    build_polling_bundle,
    build_reflection_prompts,
    build_standardized_record,
    evaluate_journal_fields,
    extract_field_value,
    field_prompt_label,
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
from .memory import (
    build_memory_provenance,
    build_memory_quality,
    build_memory_summary,
    build_memory_text,
    build_memory_title,
    extract_tags,
    hyperedge_specs_for_row,
    memory_query_tokens,
    scene_keys_for_row,
    score_memory_row,
    strategy_line_from_context,
    summarize_scene,
)
from .storage import FinanceJournalDB, ensure_runtime_dirs, json_dumps, json_loads, make_id, now_ts, safe_filename
from .vault import (
    ensure_vault_dirs,
    file_stem,
    render_daily_note,
    render_dashboard_note,
    render_graph_note,
    render_health_report_note,
    render_memory_note,
    render_plan_note,
    render_review_note,
    render_skill_note,
    render_trade_note,
)


def _coalesce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _statement_text_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith('="') and text.endswith('"'):
        text = text[2:-1]
    elif text.startswith("'") and len(text) > 1:
        text = text[1:]
    return text.strip()


def _statement_side_kind(value: Any) -> str:
    text = _statement_text_value(value).lower()
    if not text:
        return ""
    if any(token in text for token in ("buy", "买")):
        return "buy"
    if any(token in text for token in ("sell", "卖")):
        return "sell"
    return ""


POSITIVE_LESSON_HINTS = (
    "完美",
    "平稳",
    "拿住了",
    "保住了收益",
    "优先做核心",
    "好票",
    "说明还是要",
)
HIGH_CONFIDENCE_HINTS = (
    "龙头",
    "核心",
    "主线",
    "确定",
    "确认",
    "趋势",
    "强度",
    "看好",
)
LOW_CONFIDENCE_HINTS = (
    "试错",
    "玩玩",
    "犹豫",
    "不相信自己",
    "慌",
    "怕",
    "担心",
    "可惜",
)
LESSON_MISTAKE_RULES = [
    (r"(卖飞|拿不住|拿不稳|提前卖|本来可以赚更多)", "拿不稳"),
    (r"(破位必须走|破趋势.*先走|跌停应该要先走|不止损|扛单)", "止损拖延"),
    (r"(只是玩玩|临时起意|随手|随便)", "计划外交易"),
    (r"(不相信自己|犹豫|错过|不要怕)", "犹豫错失"),
    (r"(追高|冲动|炸板票.*不着急)", "冲动追高"),
    (r"(满仓|重仓)", "仓位过重"),
]


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
        self.market = None
        if enable_market_data and self.config.get("tushare", {}).get("enabled", True):
            self.market = TushareMarketData(token=token)

    def init_runtime(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        self.db.init_schema()
        vault_info = self.init_vault()
        self.ensure_objective_review_subskill()
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

    def _recent_skill_cards(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM memory_skill_cards ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (int(limit),),
        )

    def _recent_memory_cells(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM memory_cells ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (int(limit),),
        )

    def _recent_memory_scenes(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM memory_scenes ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (int(limit),),
        )

    def _recent_memory_hyperedges(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.db.fetchall(
            "SELECT * FROM memory_hyperedges ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (int(limit),),
        )

    def _build_local_graph_prompt(self, graph_state: dict[str, Any]) -> str:
        stats = graph_state.get("stats") or {}
        scenes = graph_state.get("recent_scenes") or []
        hyperedges = graph_state.get("recent_hyperedges") or []
        skills = graph_state.get("recent_skill_cards") or []
        memory_rows = graph_state.get("recent_memory_cells") or []
        scene_titles = [str(item.get("title") or item.get("scene_key") or "").strip() for item in scenes if str(item.get("title") or item.get("scene_key") or "").strip()]
        edge_labels = [str(item.get("label") or item.get("edge_key") or "").strip() for item in hyperedges if str(item.get("label") or item.get("edge_key") or "").strip()]
        skill_titles = [str(item.get("title") or item.get("skill_id") or "").strip() for item in skills if str(item.get("title") or item.get("skill_id") or "").strip()]
        memory_titles = [str(item.get("title") or item.get("memory_id") or "").strip() for item in memory_rows if str(item.get("title") or item.get("memory_id") or "").strip()]
        lines = [
            "你正在使用本地 TradeMirrorOS 账本。",
            "每次完成记账、补充、平仓回顾、行为体检或记忆修订后，都要把结构化结果同步到本地 Obsidian vault（_runtime/obsidian-vault）。",
            (
                "当前数据库规模："
                f" trades={stats.get('trade_count') or 0},"
                f" memory_cells={stats.get('memory_count') or 0},"
                f" scenes={stats.get('scene_count') or 0},"
                f" hyperedges={stats.get('hyperedge_count') or 0},"
                f" skill_cards={stats.get('skill_count') or 0}。"
            ),
        ]
        if scene_titles:
            lines.append(f"优先参考最近场景：{' / '.join(scene_titles[:5])}。")
        if edge_labels:
            lines.append(f"优先参考最近关系簇：{' / '.join(edge_labels[:5])}。")
        if skill_titles:
            lines.append(f"如需给出可执行建议，优先复用技能卡：{' / '.join(skill_titles[:5])}。")
        if memory_titles:
            lines.append(f"如需回忆历史相似案例，优先查看记忆单元：{' / '.join(memory_titles[:5])}。")
        lines.extend(
            [
                "本轮若已经落库，回复里要明确说明：已同步本地 Obsidian，并提醒可查看 00-dashboard 与 08-graph。",
                "不要把知识图谱当作交易信号源；它只是帮助回看历史结构、错误模式、技能沉淀与场景关系。",
            ]
        )
        return "\n".join(lines)

    def _graph_state_snapshot(self, limit: int = 10) -> dict[str, Any]:
        state = {
            "stats": {
                "plan_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM plans", ()) or {}).get("count") or 0),
                "trade_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM trades", ()) or {}).get("count") or 0),
                "review_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM reviews", ()) or {}).get("count") or 0),
                "memory_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM memory_cells", ()) or {}).get("count") or 0),
                "scene_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM memory_scenes", ()) or {}).get("count") or 0),
                "hyperedge_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM memory_hyperedges", ()) or {}).get("count") or 0),
                "skill_count": int((self.db.fetchone("SELECT COUNT(*) AS count FROM memory_skill_cards", ()) or {}).get("count") or 0),
            },
            "recent_scenes": self._recent_memory_scenes(limit=limit),
            "recent_hyperedges": self._recent_memory_hyperedges(limit=limit),
            "recent_memory_cells": self._recent_memory_cells(limit=limit),
            "recent_skill_cards": self._recent_skill_cards(limit=limit),
        }
        state["prompt_text"] = self._build_local_graph_prompt(state)
        return state

    def export_dashboard_note(self) -> dict[str, Any]:
        if not self._vault_enabled():
            return {"enabled": False}
        markdown = render_dashboard_note(
            self.list_trades(limit=20),
            self._recent_health_reports(limit=12),
            self._recent_skill_cards(limit=12),
        )
        path = self._vault_write("dashboard", "trade_journal_dashboard", markdown)
        return {"path": path}

    def export_graph_note(self) -> dict[str, Any]:
        if not self._vault_enabled():
            return {"enabled": False}
        graph_state = self._graph_state_snapshot(limit=10)
        markdown = render_graph_note(graph_state)
        path = self._vault_write("graph", "local_knowledge_graph_snapshot", markdown)
        return {"path": path, "stats": graph_state.get("stats") or {}}

    def _export_vault_companion_notes(self) -> dict[str, Any]:
        if not self._vault_enabled():
            return {}
        return {
            "dashboard": self.export_dashboard_note(),
            "graph": self.export_graph_note(),
        }

    def _clear_vault_exports(self) -> dict[str, Any]:
        dirs = ensure_vault_dirs(Path(self.config["vault_root"]))
        deleted: list[str] = []
        for folder in dirs.values():
            for path in folder.glob("*.md"):
                path.unlink()
                deleted.append(str(path))
        return {"deleted_count": len(deleted), "deleted_paths": deleted[:20]}

    def _clear_runtime_memory_snapshots(self) -> dict[str, Any]:
        memory_dir = Path(self.config["memory_dir"])
        deleted: list[str] = []
        if not memory_dir.exists():
            return {"deleted_count": 0, "deleted_paths": []}
        for path in memory_dir.glob("*"):
            if path.is_file():
                path.unlink()
                deleted.append(str(path))
        return {"deleted_count": len(deleted), "deleted_paths": deleted[:20]}

    def _replace_tree(self, source: Path, destination: Path) -> dict[str, Any]:
        if not source.exists():
            raise ValueError(f"source path does not exist: {source}")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        file_count = sum(1 for path in destination.rglob("*") if path.is_file())
        dir_count = sum(1 for path in destination.rglob("*") if path.is_dir())
        return {
            "source": str(source),
            "destination": str(destination),
            "file_count": file_count,
            "dir_count": dir_count,
        }

    def _file_sha1(self, path: Path) -> str:
        digest = hashlib.sha1()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _path_state(self, path: Path, sample_limit: int = 5) -> dict[str, Any]:
        target = Path(path).resolve()
        state: dict[str, Any] = {"path": str(target), "exists": target.exists()}
        if not target.exists():
            return state
        stat = target.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        if target.is_file():
            state.update(
                {
                    "kind": "file",
                    "size": stat.st_size,
                    "modified_at": modified_at,
                    "sha1": self._file_sha1(target),
                }
            )
            return state
        files = [item for item in target.rglob("*") if item.is_file()]
        dirs = [item for item in target.rglob("*") if item.is_dir()]
        sample_files = [str(item.relative_to(target)).replace("\\", "/") for item in files[:sample_limit]]
        latest_file = max(files, key=lambda item: item.stat().st_mtime, default=None)
        state.update(
            {
                "kind": "directory",
                "file_count": len(files),
                "dir_count": len(dirs),
                "modified_at": modified_at,
                "sample_files": sample_files,
                "latest_file": str(latest_file.relative_to(target)).replace("\\", "/") if latest_file else "",
            }
        )
        return state

    def _compare_export_file(self, runtime_path: Path, repo_path: Path) -> dict[str, Any]:
        runtime_state = self._path_state(runtime_path)
        repo_state = self._path_state(repo_path)
        same_content = bool(
            runtime_state.get("exists")
            and repo_state.get("exists")
            and runtime_state.get("kind") == "file"
            and repo_state.get("kind") == "file"
            and runtime_state.get("sha1") == repo_state.get("sha1")
        )
        return {
            "runtime": runtime_state,
            "repo_root": repo_state,
            "same_content": same_content,
        }

    def mirror_runtime_exports_to_repo_root(self) -> dict[str, Any]:
        runtime_artifacts = Path(self.config["artifacts_dir"])
        runtime_vault = Path(self.config["vault_root"])
        root_artifacts = self.repo_root / "artifacts"
        root_vault = self.repo_root / "obsidian-vault"
        artifacts_result = self._replace_tree(runtime_artifacts, root_artifacts)
        vault_result = self._replace_tree(runtime_vault, root_vault)
        return {
            "artifacts": artifacts_result,
            "obsidian_vault": vault_result,
            "repo_root": str(self.repo_root),
        }

    def sync_repo_snapshot(self) -> dict[str, Any]:
        vault_sync = self.sync_vault(full=True, clean=True)
        mirror = self.mirror_runtime_exports_to_repo_root()
        self_check = self.runtime_self_check()
        return {
            "vault_sync": vault_sync,
            "mirror": mirror,
            "self_check": self_check,
        }

    def runtime_self_check(self) -> dict[str, Any]:
        runtime_root = Path(self.config["runtime_root"]).resolve()
        expected_runtime_root = (self.repo_root / "_runtime").resolve()
        db_path = Path(self.config["db_path"]).resolve()
        runtime_artifacts = Path(self.config["artifacts_dir"]).resolve()
        runtime_memory = Path(self.config["memory_dir"]).resolve()
        runtime_status = Path(self.config["status_dir"]).resolve()
        runtime_vault = Path(self.config["vault_root"]).resolve()
        repo_artifacts = (self.repo_root / "artifacts").resolve()
        repo_vault = (self.repo_root / "obsidian-vault").resolve()

        table_counts: dict[str, int] = {}
        for table_name in (
            "plans",
            "trades",
            "reviews",
            "health_reports",
            "memory_cells",
            "memory_scenes",
            "memory_hyperedges",
            "memory_skill_cards",
        ):
            row = self.db.fetchone(f"SELECT COUNT(*) AS count FROM {table_name}", ()) or {}
            table_counts[table_name] = int(row.get("count") or 0)

        latest_trade = self.db.fetchone(
            """
            SELECT trade_id, ts_code, name, buy_date, sell_date, updated_at
            FROM trades
            ORDER BY COALESCE(sell_date, buy_date) DESC, updated_at DESC
            LIMIT 1
            """,
            (),
        ) or {}
        latest_memory = self.db.fetchone(
            """
            SELECT memory_id, title, trade_date, updated_at
            FROM memory_cells
            ORDER BY trade_date DESC, updated_at DESC
            LIMIT 1
            """,
            (),
        ) or {}
        latest_report = self.db.fetchone(
            """
            SELECT report_id, period_start, period_end, created_at
            FROM health_reports
            ORDER BY period_end DESC, created_at DESC
            LIMIT 1
            """,
            (),
        ) or {}

        runtime_artifacts_state = self._path_state(runtime_artifacts)
        repo_artifacts_state = self._path_state(repo_artifacts)
        runtime_vault_state = self._path_state(runtime_vault)
        repo_vault_state = self._path_state(repo_vault)
        graph_compare = self._compare_export_file(
            runtime_vault / "08-graph" / "local_knowledge_graph_snapshot.md",
            repo_vault / "08-graph" / "local_knowledge_graph_snapshot.md",
        )
        dashboard_compare = self._compare_export_file(
            runtime_vault / "00-dashboard" / "trade_journal_dashboard.md",
            repo_vault / "00-dashboard" / "trade_journal_dashboard.md",
        )
        mirror_in_sync = bool(
            runtime_artifacts_state.get("exists")
            and runtime_vault_state.get("exists")
            and repo_artifacts_state.get("exists")
            and repo_vault_state.get("exists")
            and runtime_artifacts_state.get("file_count") == repo_artifacts_state.get("file_count")
            and runtime_vault_state.get("file_count") == repo_vault_state.get("file_count")
            and graph_compare.get("same_content")
            and dashboard_compare.get("same_content")
        )

        warnings: list[str] = []
        if runtime_root != expected_runtime_root:
            warnings.append("runtime_root is not repo_root/_runtime; OpenClaw may be reading a different ledger than the current repository snapshot.")
        if not db_path.exists():
            warnings.append("SQLite database file is missing under the resolved runtime_root.")
        if not runtime_vault.exists():
            warnings.append("Runtime Obsidian vault is missing; markdown exports have not been generated yet.")
        if not mirror_in_sync:
            warnings.append("Top-level artifacts/obsidian-vault are stale or missing; run `vault sync-all` before pushing or mirroring to cloud.")

        return {
            "status": "warning" if warnings else "ok",
            "warnings": warnings,
            "repo_root": str(self.repo_root),
            "skill_root": str(self.skill_root),
            "runtime_root": str(runtime_root),
            "expected_runtime_root": str(expected_runtime_root),
            "matches_repo_runtime": runtime_root == expected_runtime_root,
            "paths": {
                "runtime_root": self._path_state(runtime_root),
                "db_path": self._path_state(db_path),
                "artifacts_dir": runtime_artifacts_state,
                "memory_dir": self._path_state(runtime_memory),
                "status_dir": self._path_state(runtime_status),
                "vault_root": runtime_vault_state,
                "repo_artifacts": repo_artifacts_state,
                "repo_obsidian_vault": repo_vault_state,
            },
            "database": {
                "table_counts": table_counts,
                "latest_trade": latest_trade,
                "latest_memory": latest_memory,
                "latest_report": latest_report,
            },
            "mirror_state": {
                "in_sync": mirror_in_sync,
                "graph_note": graph_compare,
                "dashboard_note": dashboard_compare,
            },
            "suggested_commands": {
                "refresh_runtime_exports": "python .\\finance-journal-orchestrator\\scripts\\finance_journal_cli.py vault sync-all",
                "show_runtime_diagnosis": "python .\\finance-journal-orchestrator\\scripts\\finance_journal_cli.py maintenance self-check",
                "pin_current_runtime_root": "python .\\finance-journal-orchestrator\\scripts\\finance_journal_cli.py --root .\\_runtime maintenance self-check",
            },
        }

    def _clear_daily_artifacts_in_range(self, start_date: str, end_date: str) -> dict[str, Any]:
        daily_root = Path(self.config["artifacts_dir"]) / "daily"
        deleted: list[str] = []
        if not daily_root.exists():
            return {"deleted_count": 0, "deleted_paths": []}
        for path in daily_root.iterdir():
            if not path.is_dir() or not re.fullmatch(r"\d{8}", path.name or ""):
                continue
            if start_date <= path.name <= end_date:
                deleted.append(str(path))
                shutil.rmtree(path)
        return {"deleted_count": len(deleted), "deleted_paths": deleted[:20]}

    def _cleanup_stale_session_refs(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE session_threads
                SET active_draft_id = ''
                WHERE active_draft_id != '' AND active_draft_id NOT IN (SELECT draft_id FROM journal_drafts)
                """
            )
            conn.execute(
                """
                UPDATE session_threads
                SET active_entity_kind = '', active_entity_id = ''
                WHERE active_entity_kind = 'trade' AND active_entity_id != '' AND active_entity_id NOT IN (SELECT trade_id FROM trades)
                """
            )
            conn.execute(
                """
                UPDATE session_threads
                SET active_entity_kind = '', active_entity_id = ''
                WHERE active_entity_kind = 'plan' AND active_entity_id != '' AND active_entity_id NOT IN (SELECT plan_id FROM plans)
                """
            )
            conn.execute(
                """
                UPDATE session_threads
                SET active_entity_kind = '', active_entity_id = ''
                WHERE active_entity_kind = 'review' AND active_entity_id != '' AND active_entity_id NOT IN (SELECT review_id FROM reviews)
                """
            )

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

    def export_memory_note(self, memory_id: str) -> dict[str, Any]:
        row = self.db.fetchone("SELECT * FROM memory_cells WHERE memory_id = ?", (memory_id,))
        if not row:
            raise ValueError(f"memory cell not found: {memory_id}")
        markdown = render_memory_note(row)
        stem = file_stem("memory", row.get("trade_date") or "", row.get("ts_code") or "", memory_id)
        path = self._vault_write("memory", stem, markdown)
        return {"path": path, "memory_id": memory_id}

    def export_skill_note(self, skill_id: str) -> dict[str, Any]:
        row = self.db.fetchone("SELECT * FROM memory_skill_cards WHERE skill_id = ?", (skill_id,))
        if not row:
            raise ValueError(f"skill card not found: {skill_id}")
        markdown = render_skill_note(row)
        stem = file_stem("skill", row.get("title") or "", skill_id)
        path = self._vault_write("skills", stem, markdown)
        return {"path": path, "skill_id": skill_id}

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
        memory_result = self.query_memory(trade_date=token, limit=8)
        markdown = render_daily_note(
            token,
            plans,
            trades,
            reviews,
            memory_result.get("matched_cells", []),
            memory_result.get("linked_skill_cards", []),
        )
        stem = file_stem("daily", token, "review")
        path = self._vault_write("daily", stem, markdown)
        return {"path": path, "trade_date": token}

    def _daily_note_dates(self) -> list[str]:
        rows = self.db.fetchall(
            """
            SELECT trade_date FROM (
                SELECT buy_date AS trade_date FROM trades WHERE buy_date IS NOT NULL AND buy_date != ''
                UNION
                SELECT sell_date AS trade_date FROM trades WHERE sell_date IS NOT NULL AND sell_date != ''
                UNION
                SELECT review_due_date AS trade_date FROM reviews WHERE review_due_date IS NOT NULL AND review_due_date != ''
            )
            ORDER BY trade_date DESC
            """,
            (),
        )
        return [str(row.get("trade_date") or "").strip() for row in rows if str(row.get("trade_date") or "").strip()]

    def sync_vault(self, trade_date: str | None = None, limit: int = 200, full: bool = False, clean: bool = False) -> dict[str, Any]:
        if not self._vault_enabled():
            return {"enabled": False, "paths": []}
        self.init_vault()
        cleanup: dict[str, Any] = {}
        if clean:
            cleanup = self._clear_vault_exports()
        paths: list[str] = []
        plan_sql = "SELECT plan_id FROM plans ORDER BY updated_at DESC"
        trade_sql = "SELECT trade_id FROM trades ORDER BY updated_at DESC"
        review_sql = "SELECT review_id FROM reviews ORDER BY updated_at DESC"
        memory_sql = "SELECT memory_id FROM memory_cells ORDER BY updated_at DESC"
        skill_sql = "SELECT skill_id FROM memory_skill_cards ORDER BY updated_at DESC, created_at DESC"
        params = () if full else (int(limit),)
        if not full:
            plan_sql += " LIMIT ?"
            trade_sql += " LIMIT ?"
            review_sql += " LIMIT ?"
            memory_sql += " LIMIT ?"
            skill_sql += " LIMIT ?"
        for plan in self.db.fetchall(plan_sql, params):
            paths.append(self.export_plan_note(plan["plan_id"])["path"])
        for trade in self.db.fetchall(trade_sql, params):
            paths.append(self.export_trade_note(trade["trade_id"])["path"])
        for review in self.db.fetchall(review_sql, params):
            paths.append(self.export_review_note(review["review_id"])["path"])
        for report in self._recent_health_reports(limit=limit):
            paths.append(self.export_report_note(report["report_id"])["path"])
        if full:
            report_rows = self.db.fetchall(
                "SELECT report_id FROM health_reports ORDER BY period_end DESC, created_at DESC",
                (),
            )
            paths = [path for path in paths if "04-reports" not in path]
            for report in report_rows:
                paths.append(self.export_report_note(report["report_id"])["path"])
        for memory in self.db.fetchall(memory_sql, params):
            paths.append(self.export_memory_note(memory["memory_id"])["path"])
        for skill in self.db.fetchall(skill_sql, params):
            paths.append(self.export_skill_note(skill["skill_id"])["path"])
        daily_dates = [normalize_trade_date(trade_date)] if trade_date else (self._daily_note_dates() if full else [])
        for token in daily_dates:
            paths.append(self.export_daily_note(token)["path"])
        companion = self._export_vault_companion_notes()
        if companion.get("dashboard", {}).get("path"):
            paths.append(companion["dashboard"]["path"])
        if companion.get("graph", {}).get("path"):
            paths.append(companion["graph"]["path"])
        return {"enabled": True, "paths": paths, "full": bool(full), "clean": bool(clean), "cleanup": cleanup}

    def purge_records_in_date_range(
        self,
        start_date: str,
        end_date: str,
        *,
        rebuild_memory_views: bool = True,
        sync_vault_after: bool = True,
    ) -> dict[str, Any]:
        start = normalize_trade_date(start_date)
        end = normalize_trade_date(end_date)
        if start > end:
            raise ValueError(f"invalid date range: {start} > {end}")

        plan_ids = [str(row.get("plan_id") or "") for row in self.db.fetchall("SELECT plan_id FROM plans WHERE valid_from <= ? AND valid_to >= ?", (end, start))]
        trade_ids = [
            str(row.get("trade_id") or "")
            for row in self.db.fetchall(
                """
                SELECT trade_id FROM trades
                WHERE (buy_date >= ? AND buy_date <= ?) OR (sell_date >= ? AND sell_date <= ?)
                """,
                (start, end, start, end),
            )
        ]
        review_ids = [
            str(row.get("review_id") or "")
            for row in self.db.fetchall(
                """
                SELECT review_id FROM reviews
                WHERE (review_due_date >= ? AND review_due_date <= ?) OR (sell_date >= ? AND sell_date <= ?)
                """,
                (start, end, start, end),
            )
        ]
        report_ids = [
            str(row.get("report_id") or "")
            for row in self.db.fetchall(
                "SELECT report_id FROM health_reports WHERE period_start <= ? AND period_end >= ?",
                (end, start),
            )
        ]
        snapshot_ids = [
            str(row.get("snapshot_id") or "")
            for row in self.db.fetchall(
                "SELECT snapshot_id FROM market_snapshots WHERE trade_date >= ? AND trade_date <= ?",
                (start, end),
            )
        ]
        draft_ids = [
            str(row.get("draft_id") or "")
            for row in self.db.fetchall(
                "SELECT draft_id FROM journal_drafts WHERE trade_date >= ? AND trade_date <= ?",
                (start, end),
            )
        ]

        with self.db.connect() as conn:
            if review_ids:
                conn.executemany("DELETE FROM reviews WHERE review_id = ?", [(item,) for item in review_ids])
            if trade_ids:
                conn.executemany("DELETE FROM trades WHERE trade_id = ?", [(item,) for item in trade_ids])
            if plan_ids:
                conn.executemany("DELETE FROM plans WHERE plan_id = ?", [(item,) for item in plan_ids])
            if report_ids:
                conn.executemany("DELETE FROM health_reports WHERE report_id = ?", [(item,) for item in report_ids])
            if snapshot_ids:
                conn.executemany("DELETE FROM market_snapshots WHERE snapshot_id = ?", [(item,) for item in snapshot_ids])
            if draft_ids:
                conn.executemany("DELETE FROM journal_drafts WHERE draft_id = ?", [(item,) for item in draft_ids])
            conn.execute("DELETE FROM memory_hyperedge_members")
            conn.execute("DELETE FROM memory_hyperedges")
            conn.execute("DELETE FROM memory_scenes")
            conn.execute("DELETE FROM memory_skill_cards")
            conn.execute("DELETE FROM memory_cells_fts")
            conn.execute("DELETE FROM memory_cells")

        self._cleanup_stale_session_refs()
        memory_cleanup = self._clear_runtime_memory_snapshots()
        artifact_cleanup = self._clear_daily_artifacts_in_range(start, end)

        rebuild: dict[str, Any] = {}
        skillize: dict[str, Any] = {}
        if rebuild_memory_views:
            rebuild = self.rebuild_memory(limit=0)
            skillize = self.skillize_memory(lookback_days=365, trade_date=end)

        vault_sync: dict[str, Any] = {}
        if sync_vault_after and self._vault_enabled():
            vault_sync = self.sync_vault(full=True, clean=True)

        return {
            "start_date": start,
            "end_date": end,
            "deleted": {
                "plans": len(plan_ids),
                "trades": len(trade_ids),
                "reviews": len(review_ids),
                "health_reports": len(report_ids),
                "market_snapshots": len(snapshot_ids),
                "journal_drafts": len(draft_ids),
            },
            "memory_cleanup": memory_cleanup,
            "artifact_cleanup": artifact_cleanup,
            "rebuild": rebuild,
            "skillize": skillize,
            "vault_sync": vault_sync,
        }

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

    def _derive_mistake_tags_from_lessons(
        self,
        lessons_learned: Any,
        *,
        existing_tags: Any = None,
        actual_return_pct: float | None = None,
    ) -> list[str]:
        explicit_tags = [tag for tag in self._merge_unique_tags(existing_tags) if tag != "无"]
        if explicit_tags:
            return explicit_tags
        text = str(lessons_learned or "").strip()
        if not text:
            return []
        derived: list[str] = []
        for pattern, label in [*MISTAKE_RULES, *LESSON_MISTAKE_RULES]:
            if re.search(pattern, text, re.IGNORECASE):
                derived.append(label)
        derived = [tag for tag in self._merge_unique_tags(derived) if tag != "无"]
        if derived:
            return derived
        if (actual_return_pct is not None and actual_return_pct > 0) or any(hint in text for hint in POSITIVE_LESSON_HINTS):
            return ["无"]
        return []

    def _derive_position_confidence(
        self,
        *,
        existing_value: Any = None,
        thesis: Any = None,
        buy_reason: Any = None,
        sell_reason: Any = None,
        notes: Any = None,
        emotion_notes: Any = None,
        lessons_learned: Any = None,
    ) -> int | None:
        if existing_value not in (None, ""):
            try:
                return int(existing_value)
            except (TypeError, ValueError):
                pass
        text_sources = [
            str(thesis or "").strip(),
            str(buy_reason or "").strip(),
            str(sell_reason or "").strip(),
            str(notes or "").strip(),
            str(emotion_notes or "").strip(),
            str(lessons_learned or "").strip(),
        ]
        combined = "\n".join(part for part in text_sources if part)
        if not combined:
            return 5
        explicit = extract_field_value(
            "position_confidence",
            combined,
            symbol_index=self._symbol_index(),
            anchor_date=self._today(),
        )
        if explicit not in (None, ""):
            try:
                return int(explicit)
            except (TypeError, ValueError):
                pass
        score = 6
        if str(thesis or "").strip() or str(buy_reason or "").strip():
            score += 1
        if any(hint in combined for hint in HIGH_CONFIDENCE_HINTS):
            score += 1
        if any(hint in combined for hint in LOW_CONFIDENCE_HINTS):
            score -= 2
        if any(hint in str(emotion_notes or "") for hint in ("急", "慌", "怕", "犹豫")):
            score -= 1
        return max(3, min(score, 8))

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
        tags = split_tags(environment_tags)
        for tag in tags:
            if tag.endswith("市") or "分歧" in tag or "主升" in tag or "冰点" in tag or "下跌" in tag or "上涨" in tag:
                return tag
        if tags:
            return tags[0]
        return str(fallback or "").strip()

    def _align_market_stage_and_environment_tags(
        self,
        market_stage: str | None,
        environment_tags: list[str] | str | None,
    ) -> tuple[str, list[str]]:
        stage = str(market_stage or "").strip()
        env_tags = self._merge_unique_tags(environment_tags)
        if stage:
            env_tags = self._merge_unique_tags(env_tags, [stage])
        if not stage:
            fallback = env_tags[0] if env_tags else ""
            stage = self._pick_market_stage(env_tags, fallback=fallback)
        elif stage not in env_tags:
            env_tags = self._merge_unique_tags(env_tags, [stage])
        return stage, env_tags

    def _plan_to_journal_fields(self, plan: dict[str, Any]) -> dict[str, Any]:
        market_stage, environment_tags = self._align_market_stage_and_environment_tags(
            plan.get("market_stage_tag"),
            json_loads(plan.get("environment_tags_json"), []),
        )
        fields = {
            "ts_code": plan.get("ts_code") or "",
            "name": plan.get("name") or "",
            "direction": plan.get("direction") or "buy",
            "thesis": plan.get("thesis") or "",
            "logic_tags": split_tags(json_loads(plan.get("logic_tags_json"), [])),
            "pattern_tags": [],
            "environment_tags": environment_tags,
            "market_stage": market_stage,
            "user_focus": [],
            "observed_signals": [],
            "position_reason": "",
            "position_confidence": None,
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
        market_stage, environment_tags = self._align_market_stage_and_environment_tags(
            trade.get("market_stage_tag"),
            json_loads(trade.get("environment_tags_json"), []),
        )
        fields = {
            "ts_code": trade.get("ts_code") or "",
            "name": trade.get("name") or "",
            "direction": trade.get("direction") or "long",
            "thesis": trade.get("thesis") or "",
            "logic_tags": split_tags(json_loads(trade.get("logic_type_tags_json"), [])),
            "pattern_tags": split_tags(json_loads(trade.get("pattern_tags_json"), [])),
            "environment_tags": environment_tags,
            "market_stage": market_stage,
            "user_focus": [],
            "observed_signals": [],
            "position_reason": "",
            "position_confidence": None,
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
        polling_bundle = draft.get("polling_bundle") or {}
        examples = (polling_bundle.get("examples") or [])
        example_text = f" 例如：{examples[0]}。" if examples else ""
        reuse_prefix = self._session_reuse_summary(draft.get("session_reuse") or [])
        guided_prompt = (polling_bundle.get("guided_prompt") or {}).get("reply_template") or ""
        template_text = f"\n{guided_prompt}" if guided_prompt else ""
        return f"{reuse_prefix}我先帮你起草好了，当前还缺：{missing or '无'}。下一问：{next_question}{example_text}{template_text}"

    def _answer_template_for_fields(self, field_names: list[str]) -> str:
        lines: list[str] = []
        for index, field_name in enumerate(field_names, start=1):
            lines.append(f"{index}. {field_prompt_label(field_name)}：...")
        return "\n".join(lines)

    def _polish_thesis_variant(self, thesis: str) -> str:
        text = re.sub(r"\s+", " ", str(thesis or "").strip(" ，,；;。"))
        if not text:
            return ""
        parts = [part.strip(" ，,；;。") for part in re.split(r"[，,；;。]+", text) if part.strip(" ，,；;。")]
        if len(parts) <= 1:
            return text
        polished = [parts[0]]
        if len(parts) >= 2:
            polished.append(f"叠加{parts[1]}")
        if len(parts) >= 3:
            polished.append(f"且{parts[2]}")
        if len(parts) > 3:
            polished.extend(parts[3:])
        return "，".join(polished)

    def _collect_thesis_polish_hints(self, items: list[dict[str, Any]]) -> list[str]:
        source_texts = [
            str(item.get("thesis") or "").strip()
            for item in items
            if str(item.get("thesis") or "").strip()
        ]
        if len(source_texts) < 2:
            return []
        normalized = [re.sub(r"[，,；;。\s]+", "", text) for text in source_texts]
        if len(set(normalized)) == len(normalized):
            return []
        polished: list[str] = []
        seen: set[str] = set()
        for text in source_texts:
            candidate = self._polish_thesis_variant(text)
            key = re.sub(r"[，,；;。\s]+", "", candidate)
            if not candidate or key in seen:
                continue
            seen.add(key)
            polished.append(candidate)
        return polished[:2]

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
        sync_tail = " 已同步本地 Obsidian。" if self._vault_enabled() else ""
        return f"{reuse_prefix}{prefix}。{summary}{sync_tail}"

    def _assistant_message_for_enrich(self, entity_kind: str, updated_fields: list[str], reflection_prompts: list[dict[str, Any]]) -> str:
        label = "计划" if entity_kind == "plan" else "交易"
        changed = "、".join(updated_fields[:6]) or "备注"
        tail = " 已同步本地 Obsidian。" if self._vault_enabled() else ""
        if reflection_prompts:
            tail += f" 下一步可继续想一想：{reflection_prompts[0].get('question') or ''}"
        return f"已把补充内容沉淀回原{label}，这次更新了：{changed}.{tail}".strip()

    def _resolve_self_check_trade_date(
        self,
        fields: dict[str, Any] | None,
        journal_kind: str,
        fallback_trade_date: str | None = None,
    ) -> str:
        if fallback_trade_date:
            return normalize_trade_date(fallback_trade_date)
        payload = fields or {}
        if journal_kind == "close_only":
            return normalize_trade_date(payload.get("sell_date") or self._today())
        return normalize_trade_date(payload.get("buy_date") or payload.get("sell_date") or self._today())

    def _build_daily_self_check(self, trade_date: str | None) -> dict[str, Any]:
        if not trade_date:
            return {}
        token = normalize_trade_date(trade_date)
        backlog = self.build_trade_follow_up_backlog(trade_date=token, include_complete=False)
        items = list(backlog.get("items") or [])
        field_label_map = {
            "thesis": "核心逻辑",
            "user_focus": "关注对象",
            "observed_signals": "触发信号",
            "position_reason": "仓位理由",
            "environment_tags": "环境标签",
            "position_confidence": "把握度",
            "emotion_notes": "情绪记录",
            "mistake_tags": "错误标签",
            "lessons_learned": "复盘教训",
        }
        field_counts: dict[str, int] = {}
        for item in items:
            for field_name in list(item.get("blocking_missing_fields") or []) + list(item.get("missing_context_fields") or []):
                token_name = str(field_name or "").strip()
                if not token_name:
                    continue
                field_counts[token_name] = field_counts.get(token_name, 0) + 1
        top_missing_fields = [
            field_label_map.get(name, name)
            for name, _ in sorted(field_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:4]
        ]
        summary = backlog.get("summary") or {}
        incomplete = int(summary.get("incomplete_trades") or 0)
        total_scanned = int(summary.get("total_scanned") or 0)
        next_question = str(items[0].get("next_question") or "").strip() if items else ""
        if total_scanned == 0:
            assistant_message = f" 今日自检：{token} 还没有交易记录。"
            status = "empty"
        elif incomplete == 0:
            assistant_message = f" 今日自检通过：{token} 当前没有待补字段。"
            status = "passed"
        else:
            field_text = "、".join(top_missing_fields) if top_missing_fields else "主观轨迹字段"
            tail = f" 下一问建议先补：{next_question}" if next_question else ""
            assistant_message = f" 今日自检：{token} 还有 {incomplete} 笔记录待补，优先补 {field_text}。{tail}".rstrip()
            status = "needs_follow_up"
        return {
            "trade_date": token,
            "status": status,
            "assistant_message": assistant_message,
            "summary": summary,
            "top_missing_fields": top_missing_fields,
            "next_question": next_question,
            "items": items[:5],
            "parallel_groups": list((backlog.get("parallel_groups") or [])[:3]),
        }

    def _append_daily_self_check_message(self, message: str, daily_self_check: dict[str, Any] | None) -> str:
        extra = str((daily_self_check or {}).get("assistant_message") or "").strip()
        if not extra:
            return message
        base = str(message or "").rstrip()
        if not base:
            return extra
        return f"{base} {extra}".strip()

    def _attach_post_apply_checks(
        self,
        payload: dict[str, Any],
        *,
        fields: dict[str, Any] | None,
        journal_kind: str,
        trade_date: str | None = None,
    ) -> dict[str, Any]:
        enriched = dict(payload or {})
        if journal_kind not in {"open_trade", "closed_trade", "close_only"}:
            return enriched
        self_check = self._build_daily_self_check(
            self._resolve_self_check_trade_date(fields, journal_kind, fallback_trade_date=trade_date)
        )
        if self_check:
            enriched["daily_self_check"] = self_check
        return enriched

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
        apply_result = self._attach_post_apply_checks(
            apply_result,
            fields=draft.get("fields") or {},
            journal_kind=draft.get("journal_kind") or "open_trade",
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
        if apply_result.get("daily_self_check"):
            fresh["daily_self_check"] = apply_result.get("daily_self_check") or {}
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
        apply_result = self._attach_post_apply_checks(
            apply_result,
            fields=draft.get("fields") or {},
            journal_kind=draft.get("journal_kind") or "open_trade",
            trade_date=trade_date,
        )
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
            "daily_self_check": apply_result.get("daily_self_check") or {},
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
                assistant_message = self._append_daily_self_check_message(
                    assistant_message,
                    (draft.get("result") or {}).get("daily_self_check") or {},
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
            return self._attach_memory_context({
                "session_key": token,
                "route": route,
                "assistant_message": assistant_message,
                "draft": draft,
                "session_state": self._build_session_state_payload(token),
            }, fields=draft.get("fields") or {}, entity_kind=draft.get("applied_entity_kind") or "", entity_id=draft.get("applied_entity_id") or "")

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
            return self._attach_memory_context({
                "session_key": token,
                "route": "entity_enriched",
                "assistant_message": assistant_message,
                "result": enriched,
                "session_state": self._build_session_state_payload(token),
            }, fields=memory_fields, entity_kind=entity_kind or active_entity_kind, entity_id=entity_id or active_entity_id)

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
            apply_result = self._attach_post_apply_checks(
                apply_result,
                fields=parsed.get("fields") or {},
                journal_kind=parsed.get("journal_kind") or "open_trade",
                trade_date=resolved_trade_date,
            )
            entity_kind, entity_id = self._applied_entity_info(apply_result)
            assistant_message = self._assistant_message_for_applied(
                parsed["journal_kind"],
                parsed["fields"],
                entity_kind,
                session_reuse=parsed.get("session_reuse") or [],
            )
            assistant_message = self._append_daily_self_check_message(
                assistant_message,
                apply_result,
            )
            if (parsed.get("reflection_prompts") or []):
                assistant_message += f" 接下来可以继续补一句：{parsed['reflection_prompts'][0].get('question') or ''}"
            result = {
                "applied": bool(apply_result.get("applied")),
                "journal_kind": parsed["journal_kind"],
                "draft": parsed,
                "result": apply_result.get("result") or {},
                "resolved_trade_id": apply_result.get("resolved_trade_id") or "",
                "daily_self_check": apply_result.get("daily_self_check") or {},
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
            return self._attach_memory_context({
                "session_key": token,
                "route": "applied_from_session",
                "assistant_message": assistant_message,
                "result": result,
                "session_state": self._build_session_state_payload(token),
            }, fields=parsed.get("fields") or {}, entity_kind=entity_kind, entity_id=entity_id)

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
        return self._attach_memory_context({
            "session_key": token,
            "route": "draft_started",
            "assistant_message": assistant_message,
            "draft": draft,
            "session_state": self._build_session_state_payload(token),
        }, fields=draft.get("fields") or {})

    def _memory_cell_id(self, entity_kind: str, entity_id: str) -> str:
        return f"memory_{entity_kind}_{safe_filename(entity_id)}"

    def _write_memory_snapshot(self, memory_row: dict[str, Any]) -> None:
        memory_dir = Path(self.config["memory_dir"])
        memory_dir.mkdir(parents=True, exist_ok=True)
        stem = safe_filename(f"{memory_row.get('trade_date') or 'undated'}_{memory_row.get('memory_id') or ''}")
        payload_path = memory_dir / f"{stem}.json"
        markdown_path = memory_dir / f"{stem}.md"
        payload_path.write_text(json.dumps(memory_row, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(render_memory_note(memory_row), encoding="utf-8")

    def _scene_id(self, scene_key: str) -> str:
        return "scene_" + safe_filename(scene_key, max_len=80)

    def _edge_id(self, edge_key: str) -> str:
        return "edge_" + safe_filename(edge_key, max_len=80)

    def _skill_id(self, source_kind: str, source_id: str) -> str:
        return f"skill_{safe_filename(source_kind)}_{safe_filename(source_id)}"

    def _reindex_memory_cell(self, payload: dict[str, Any]) -> None:
        tag_values = split_tags(payload.get("tags_json", []))
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memory_cells_fts WHERE memory_id = ?", (payload["memory_id"],))
            conn.execute(
                """
                INSERT INTO memory_cells_fts(memory_id, title, text_body, tag_text, strategy_line, market_stage)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["memory_id"],
                    payload["title"],
                    payload["text_body"],
                    " ".join(tag_values),
                    payload["strategy_line"],
                    payload["market_stage"],
                ),
            )

    def _memory_scene_specs_from_cell(self, memory_row: dict[str, Any]) -> list[tuple[str, str, str]]:
        tags = split_tags(memory_row.get("tags_json", []))
        keys: list[tuple[str, str, str]] = []
        ts_code = str(memory_row.get("ts_code") or "").strip()
        if ts_code:
            keys.append((f"symbol:{ts_code}", "symbol", f"Symbol Scene | {memory_row.get('ts_code') or ts_code}"))
        strategy_line = str(memory_row.get("strategy_line") or "").strip()
        if strategy_line:
            keys.append((f"strategy:{strategy_line}", "strategy", f"Strategy Scene | {strategy_line}"))
        market_stage = str(memory_row.get("market_stage") or "").strip()
        if market_stage:
            keys.append((f"stage:{market_stage}", "stage", f"Stage Scene | {market_stage}"))
        top_logic = next((tag.split(":", 1)[1] for tag in tags if tag.startswith("logic:")), "")
        top_pattern = next((tag.split(":", 1)[1] for tag in tags if tag.startswith("pattern:")), "")
        if top_logic or top_pattern:
            label = " / ".join(part for part in (top_logic, top_pattern) if part)
            keys.append((f"setup:{safe_filename(label)}", "setup", f"Setup Scene | {label}"))
        return keys

    def _memory_hyperedge_specs_from_cell(self, memory_row: dict[str, Any]) -> list[dict[str, str]]:
        specs: list[dict[str, str]] = []
        for tag in split_tags(memory_row.get("tags_json", [])):
            if ":" not in tag:
                continue
            edge_type, label = tag.split(":", 1)
            specs.append(
                {
                    "edge_key": f"{edge_type}:{label}",
                    "edge_type": edge_type,
                    "label": label,
                }
            )
        return specs

    def _refresh_links_from_specs(
        self,
        memory_id: str,
        *,
        specs: list[dict[str, str]],
        scenes: list[tuple[str, str, str]],
        metadata: dict[str, Any] | None = None,
        member_role: str = "",
    ) -> None:
        if not memory_id:
            return
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memory_hyperedge_members WHERE member_kind = 'memory' AND member_id = ?", (memory_id,))
            for spec in specs:
                edge_id = self._edge_id(spec["edge_key"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_hyperedges(
                        edge_id, edge_key, edge_type, label, tags_json, metadata_json, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge_id,
                        spec["edge_key"],
                        spec["edge_type"],
                        spec["label"],
                        json_dumps([spec["edge_type"], spec["label"]]),
                        json_dumps(metadata or {}),
                        now_ts(),
                        now_ts(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO memory_hyperedge_members(membership_id, edge_id, member_kind, member_id, member_role, created_at)
                    VALUES(?, ?, 'memory', ?, ?, ?)
                    """,
                    (make_id("membership"), edge_id, memory_id, member_role or "memory", now_ts()),
                )
        for scene_key, scene_type, title in scenes:
            scene = self._rebuild_scene(scene_key, scene_type, title)
            if not scene:
                continue
            edge_id = self._edge_id(scene_key)
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_hyperedges(
                        edge_id, edge_key, edge_type, label, tags_json, metadata_json, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge_id,
                        scene_key,
                        scene_type,
                        title,
                        json_dumps(split_tags(json_loads(scene.get("tags_json"), []))),
                        json_dumps({"scene_id": scene.get("scene_id")}),
                        now_ts(),
                        now_ts(),
                    ),
                )
                conn.execute("DELETE FROM memory_hyperedge_members WHERE edge_id = ? AND member_kind = 'scene'", (edge_id,))
                conn.execute(
                    """
                    INSERT INTO memory_hyperedge_members(membership_id, edge_id, member_kind, member_id, member_role, created_at)
                    VALUES(?, ?, 'scene', ?, 'scene', ?)
                    """,
                    (make_id("membership"), edge_id, scene.get("scene_id") or "", now_ts()),
                )

    def _upsert_memory_cell(self, entity_kind: str, row: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(row.get("plan_id") or row.get("trade_id") or row.get("review_id") or "").strip()
        if not entity_id:
            raise ValueError(f"cannot build memory cell without entity id: {entity_kind}")
        memory_id = self._memory_cell_id(entity_kind, entity_id)
        decision_context = json_loads(row.get("decision_context_json"), {}) or {}
        strategy_line = strategy_line_from_context(decision_context)
        trade_date = normalize_trade_date(
            row.get("buy_date")
            or row.get("valid_from")
            or row.get("review_due_date")
            or row.get("sell_date")
            or self._today()
        )
        payload = {
            "memory_id": memory_id,
            "memory_kind": entity_kind,
            "source_entity_kind": entity_kind,
            "source_entity_id": entity_id,
            "trade_date": trade_date,
            "ts_code": str(row.get("ts_code") or "").strip(),
            "strategy_line": strategy_line,
            "market_stage": str(row.get("market_stage_tag") or "").strip(),
            "title": build_memory_title(entity_kind, row),
            "text_body": build_memory_text(entity_kind, row),
            "summary_json": build_memory_summary(entity_kind, row),
            "tags_json": extract_tags(entity_kind, row),
            "quality_json": build_memory_quality(entity_kind, row),
            "provenance_json": build_memory_provenance(entity_kind, row),
            "created_at": row.get("created_at") or now_ts(),
            "updated_at": now_ts(),
        }
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_cells(
                    memory_id, memory_kind, source_entity_kind, source_entity_id, trade_date, ts_code, strategy_line,
                    market_stage, title, text_body, summary_json, tags_json, quality_json, provenance_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["memory_id"],
                    payload["memory_kind"],
                    payload["source_entity_kind"],
                    payload["source_entity_id"],
                    payload["trade_date"],
                    payload["ts_code"],
                    payload["strategy_line"],
                    payload["market_stage"],
                    payload["title"],
                    payload["text_body"],
                    json_dumps(payload["summary_json"]),
                    json_dumps(payload["tags_json"]),
                    json_dumps(payload["quality_json"]),
                    json_dumps(payload["provenance_json"]),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
        self._reindex_memory_cell(payload)
        stored = self.db.fetchone("SELECT * FROM memory_cells WHERE memory_id = ?", (memory_id,)) or {}
        self._write_memory_snapshot(stored)
        return stored

    def _rebuild_scene(self, scene_key: str, scene_type: str, title: str) -> dict[str, Any]:
        if scene_type == "symbol":
            rows = self.db.fetchall("SELECT * FROM memory_cells WHERE ts_code = ? ORDER BY updated_at DESC LIMIT 200", (scene_key.split(':', 1)[1],))
        elif scene_type == "strategy":
            rows = self.db.fetchall("SELECT * FROM memory_cells WHERE strategy_line = ? ORDER BY updated_at DESC LIMIT 200", (scene_key.split(':', 1)[1],))
        elif scene_type == "stage":
            rows = self.db.fetchall("SELECT * FROM memory_cells WHERE market_stage = ? ORDER BY updated_at DESC LIMIT 200", (scene_key.split(':', 1)[1],))
        else:
            token = scene_key.split(":", 1)[1]
            rows = self.db.fetchall("SELECT * FROM memory_cells ORDER BY updated_at DESC LIMIT 200")
            rows = [row for row in rows if token and token in " ".join(split_tags(json_loads(row.get("tags_json"), [])))]
        scene_payload = summarize_scene(rows, scene_key=scene_key, scene_type=scene_type, title=title)
        scene_payload["scene_id"] = self._scene_id(scene_key)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_scenes(
                    scene_id, scene_key, scene_type, title, description, trade_date, ts_code, strategy_line,
                    market_stage, tags_json, memory_ids_json, stats_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_payload["scene_id"],
                    scene_payload["scene_key"],
                    scene_payload["scene_type"],
                    scene_payload["title"],
                    scene_payload["description"],
                    scene_payload["trade_date"],
                    scene_payload["ts_code"],
                    scene_payload["strategy_line"],
                    scene_payload["market_stage"],
                    json_dumps([item[0] for item in scene_payload["tags_json"]]),
                    json_dumps(scene_payload["memory_ids_json"]),
                    json_dumps(scene_payload["stats_json"]),
                    now_ts(),
                    now_ts(),
                ),
            )
        return self.db.fetchone("SELECT * FROM memory_scenes WHERE scene_id = ?", (scene_payload["scene_id"],)) or {}

    def _refresh_memory_links(self, entity_kind: str, row: dict[str, Any], memory_row: dict[str, Any]) -> None:
        memory_id = str(memory_row.get("memory_id") or "")
        if not memory_id:
            return
        self._refresh_links_from_specs(
            memory_id,
            specs=hyperedge_specs_for_row(entity_kind, row),
            scenes=scene_keys_for_row(entity_kind, row),
            metadata={"source_entity_kind": entity_kind},
            member_role=entity_kind,
        )

    def _refresh_manual_memory_links(self, memory_row: dict[str, Any]) -> None:
        memory_id = str(memory_row.get("memory_id") or "")
        if not memory_id:
            return
        self._refresh_links_from_specs(
            memory_id,
            specs=self._memory_hyperedge_specs_from_cell(memory_row),
            scenes=self._memory_scene_specs_from_cell(memory_row),
            metadata={"source_entity_kind": memory_row.get("source_entity_kind") or "memory"},
            member_role=str(memory_row.get("memory_kind") or "memory"),
        )

    def _sync_memory_for_entity(self, entity_kind: str, entity_id: str) -> dict[str, Any]:
        if entity_kind == "plan":
            row = self.get_plan(entity_id)
        elif entity_kind == "trade":
            row = self.get_trade(entity_id)
        elif entity_kind == "review":
            row = self.db.fetchone("SELECT * FROM reviews WHERE review_id = ?", (entity_id,))
        else:
            row = None
        if not row:
            return {}
        memory_row = self._upsert_memory_cell(entity_kind, row)
        self._refresh_memory_links(entity_kind, row, memory_row)
        return memory_row

    def rebuild_memory(self, limit: int = 0) -> dict[str, Any]:
        plan_rows = self.db.fetchall("SELECT plan_id FROM plans ORDER BY updated_at DESC")
        trade_rows = self.db.fetchall("SELECT trade_id FROM trades ORDER BY updated_at DESC")
        review_rows = self.db.fetchall("SELECT review_id FROM reviews ORDER BY updated_at DESC")
        inserted: list[str] = []
        for entity_kind, rows, field_name in (
            ("plan", plan_rows, "plan_id"),
            ("trade", trade_rows, "trade_id"),
            ("review", review_rows, "review_id"),
        ):
            for row in rows[: int(limit) if limit and int(limit) > 0 else None]:
                memory_row = self._sync_memory_for_entity(entity_kind, str(row.get(field_name) or ""))
                if memory_row.get("memory_id"):
                    inserted.append(memory_row["memory_id"])
        return {
            "rebuild_count": len(inserted),
            "memory_ids": inserted[:20],
            "scene_count": self.db.fetchone("SELECT COUNT(*) AS count FROM memory_scenes", ())["count"],
            "skill_count": self.db.fetchone("SELECT COUNT(*) AS count FROM memory_skill_cards", ())["count"],
        }

    def query_memory(
        self,
        *,
        text: str = "",
        ts_code: str | None = None,
        strategy_line: str | None = None,
        market_stage: str | None = None,
        tags: list[str] | str | None = None,
        trade_date: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        token_code = normalize_ts_code(ts_code) if ts_code else ""
        requested_tags = split_tags(tags)
        query_tokens = memory_query_tokens(
            text=text,
            ts_code=token_code,
            strategy_line=str(strategy_line or ""),
            market_stage=str(market_stage or ""),
            tags=requested_tags,
        )
        candidate_limit = int(limit or self.config.get("memory", {}).get("default_query_limit", 8))
        base_limit = max(candidate_limit * 3, int(self.config.get("memory", {}).get("max_query_candidates", 24)))
        if text.strip():
            query_terms = [part.replace('"', " ").strip() for part in split_tags(text) if part.strip()]
            if not query_terms:
                query_terms = [text.replace('"', " ").strip()]
            query_text = " ".join(f'"{term}"' for term in query_terms if term)
            rows = self.db.fetchall(
                """
                SELECT c.*
                FROM memory_cells_fts f
                JOIN memory_cells c ON c.memory_id = f.memory_id
                WHERE memory_cells_fts MATCH ?
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (query_text, base_limit),
            )
        else:
            rows = self.db.fetchall("SELECT * FROM memory_cells ORDER BY updated_at DESC LIMIT ?", (base_limit,))
        if trade_date:
            token_date = normalize_trade_date(trade_date)
            rows = [row for row in rows if str(row.get("trade_date") or "") == token_date]
        needs_filter = bool(text or token_code or strategy_line or market_stage or requested_tags)
        memory_scores: dict[str, dict[str, Any]] = {}

        def add_memory_candidate(row: dict[str, Any], *, base_score: float | None = None, scene_boost: float = 0.0, hyperedge_boost: float = 0.0) -> None:
            memory_id = str(row.get("memory_id") or "")
            if not memory_id:
                return
            scored = score_memory_row(
                row,
                text=text,
                ts_code=token_code,
                strategy_line=str(strategy_line or ""),
                market_stage=str(market_stage or ""),
                tags=requested_tags,
            ) if base_score is None else float(base_score)
            if scored <= 0 and scene_boost <= 0 and hyperedge_boost <= 0 and needs_filter:
                return
            entry = memory_scores.get(memory_id)
            if not entry:
                row_copy = dict(row)
                row_copy["base_score"] = round(float(scored), 4)
                row_copy["scene_boost"] = round(float(scene_boost), 4)
                row_copy["hyperedge_boost"] = round(float(hyperedge_boost), 4)
                row_copy["score"] = round(float(scored) + float(scene_boost) + float(hyperedge_boost), 4)
                memory_scores[memory_id] = row_copy
                return
            entry["base_score"] = max(float(entry.get("base_score") or 0.0), float(scored))
            entry["scene_boost"] = round(float(entry.get("scene_boost") or 0.0) + float(scene_boost), 4)
            entry["hyperedge_boost"] = round(float(entry.get("hyperedge_boost") or 0.0) + float(hyperedge_boost), 4)
            entry["score"] = round(float(entry["base_score"]) + float(entry["scene_boost"]) + float(entry["hyperedge_boost"]), 4)

        for row in rows:
            add_memory_candidate(row)

        scene_candidates = self.db.fetchall("SELECT * FROM memory_scenes ORDER BY updated_at DESC LIMIT 100")
        matched_scenes: list[dict[str, Any]] = []
        for scene in scene_candidates:
            scene_score = 0.0
            scene_tags = set(split_tags(json_loads(scene.get("tags_json"), [])))
            if token_code and scene.get("ts_code") == token_code:
                scene_score += 3.0
            if strategy_line and scene.get("strategy_line") == strategy_line:
                scene_score += 2.0
            if market_stage and scene.get("market_stage") == market_stage:
                scene_score += 1.5
            scene_score += float(len(scene_tags & set(requested_tags))) * 1.5
            scene_text = " ".join(
                [
                    str(scene.get("title") or ""),
                    str(scene.get("description") or ""),
                    str(scene.get("scene_key") or ""),
                    " ".join(scene_tags),
                ]
            ).lower()
            for token in query_tokens:
                if token and token.lower() in scene_text:
                    scene_score += 0.35
            if scene_score > 0 or not needs_filter:
                scene_copy = dict(scene)
                scene_copy["score"] = round(scene_score, 4)
                matched_scenes.append(scene_copy)
        matched_scenes.sort(key=lambda item: (item.get("score") or 0.0, item.get("updated_at") or ""), reverse=True)

        scene_expansion_ids: set[str] = set()
        for scene in matched_scenes[: max(candidate_limit, 5)]:
            scene_memory_ids = split_tags(json_loads(scene.get("memory_ids_json"), []))
            scene_bonus = max(0.4, round(float(scene.get("score") or 0.0) * 0.35, 4))
            for memory_id in scene_memory_ids[: max(candidate_limit * 2, 8)]:
                if memory_id:
                    scene_expansion_ids.add(memory_id)
                    if memory_id in memory_scores:
                        memory_scores[memory_id]["scene_boost"] = round(float(memory_scores[memory_id].get("scene_boost") or 0.0) + scene_bonus, 4)
                        memory_scores[memory_id]["score"] = round(
                            float(memory_scores[memory_id].get("base_score") or 0.0)
                            + float(memory_scores[memory_id].get("scene_boost") or 0.0)
                            + float(memory_scores[memory_id].get("hyperedge_boost") or 0.0),
                            4,
                        )

        matched_hyperedges: list[dict[str, Any]] = []
        edge_candidates = self.db.fetchall("SELECT * FROM memory_hyperedges ORDER BY updated_at DESC LIMIT 200")
        requested_tag_set = set(requested_tags)
        for edge in edge_candidates:
            edge_score = 0.0
            edge_key = str(edge.get("edge_key") or "")
            edge_label = str(edge.get("label") or "")
            edge_tags = set(split_tags(json_loads(edge.get("tags_json"), [])))
            if token_code and edge_key == f"symbol:{token_code}":
                edge_score += 3.0
            if strategy_line and edge_key == f"strategy:{strategy_line}":
                edge_score += 2.5
            if market_stage and edge_key == f"stage:{market_stage}":
                edge_score += 1.5
            edge_score += float(len(edge_tags & requested_tag_set)) * 1.5
            edge_text = f"{edge_key} {edge_label} {' '.join(edge_tags)}".lower()
            for token in query_tokens:
                if token and token.lower() in edge_text:
                    edge_score += 0.35
            if edge_score > 0 or not needs_filter:
                edge_copy = dict(edge)
                edge_copy["score"] = round(edge_score, 4)
                matched_hyperedges.append(edge_copy)
        matched_hyperedges.sort(key=lambda item: (item.get("score") or 0.0, item.get("updated_at") or ""), reverse=True)

        hyperedge_expansion_ids: set[str] = set()
        for edge in matched_hyperedges[: max(candidate_limit * 2, 8)]:
            memberships = self.db.fetchall(
                "SELECT member_kind, member_id FROM memory_hyperedge_members WHERE edge_id = ?",
                (edge.get("edge_id") or "",),
            )
            edge_bonus = max(0.35, round(float(edge.get("score") or 0.0) * 0.3, 4))
            for membership in memberships:
                if membership.get("member_kind") == "memory":
                    memory_id = str(membership.get("member_id") or "")
                    if not memory_id:
                        continue
                    hyperedge_expansion_ids.add(memory_id)
                    if memory_id in memory_scores:
                        memory_scores[memory_id]["hyperedge_boost"] = round(float(memory_scores[memory_id].get("hyperedge_boost") or 0.0) + edge_bonus, 4)
                        memory_scores[memory_id]["score"] = round(
                            float(memory_scores[memory_id].get("base_score") or 0.0)
                            + float(memory_scores[memory_id].get("scene_boost") or 0.0)
                            + float(memory_scores[memory_id].get("hyperedge_boost") or 0.0),
                            4,
                        )
                    continue
                if membership.get("member_kind") == "scene":
                    scene_row = self.db.fetchone("SELECT * FROM memory_scenes WHERE scene_id = ?", (membership.get("member_id") or "",))
                    if not scene_row:
                        continue
                    for memory_id in split_tags(json_loads(scene_row.get("memory_ids_json"), []))[: max(candidate_limit * 2, 8)]:
                        if not memory_id:
                            continue
                        hyperedge_expansion_ids.add(memory_id)
                        if memory_id in memory_scores:
                            memory_scores[memory_id]["hyperedge_boost"] = round(float(memory_scores[memory_id].get("hyperedge_boost") or 0.0) + edge_bonus * 0.8, 4)
                            memory_scores[memory_id]["score"] = round(
                                float(memory_scores[memory_id].get("base_score") or 0.0)
                                + float(memory_scores[memory_id].get("scene_boost") or 0.0)
                                + float(memory_scores[memory_id].get("hyperedge_boost") or 0.0),
                                4,
                            )

        expansion_ids = (scene_expansion_ids | hyperedge_expansion_ids) - set(memory_scores.keys())
        for memory_id in sorted(expansion_ids):
            row = self.db.fetchone("SELECT * FROM memory_cells WHERE memory_id = ?", (memory_id,))
            if not row:
                continue
            add_memory_candidate(
                row,
                scene_boost=max(0.0, 0.5 if memory_id in scene_expansion_ids else 0.0),
                hyperedge_boost=max(0.0, 0.45 if memory_id in hyperedge_expansion_ids else 0.0),
            )

        matched_cells = sorted(
            memory_scores.values(),
            key=lambda item: (item.get("score") or 0.0, item.get("updated_at") or ""),
            reverse=True,
        )[:candidate_limit]
        skill_rows = self.db.fetchall("SELECT * FROM memory_skill_cards ORDER BY updated_at DESC LIMIT 100")
        linked_skill_cards: list[dict[str, Any]] = []
        for skill in skill_rows:
            skill_tags = set(split_tags(json_loads(skill.get("trigger_conditions_json"), [])))
            score = float(len(skill_tags & set(requested_tags))) * 2.0
            if token_code and any(tag == f"symbol:{token_code}" for tag in skill_tags):
                score += 3.0
            if score > 0:
                skill_copy = dict(skill)
                skill_copy["score"] = round(score, 4)
                linked_skill_cards.append(skill_copy)
        linked_skill_cards.sort(key=lambda item: (item.get("score") or 0.0, item.get("sample_size") or 0), reverse=True)
        checklist: list[str] = []
        for item in linked_skill_cards[:3]:
            checklist.append(f"Skill card check: {item.get('title') or item.get('skill_id')}")
        for item in matched_cells[:2]:
            checklist.append(f"Memory check: revisit {item.get('title') or item.get('memory_id')}")
        return {
            "query": {
                "text": text,
                "ts_code": token_code,
                "strategy_line": str(strategy_line or ""),
                "market_stage": str(market_stage or ""),
                "tags": requested_tags,
                "trade_date": normalize_trade_date(trade_date) if trade_date else "",
            },
            "matched_cells": matched_cells,
            "matched_scenes": matched_scenes[:candidate_limit],
            "matched_hyperedges": matched_hyperedges[:candidate_limit],
            "linked_skill_cards": linked_skill_cards[:candidate_limit],
            "memory_checklist": checklist[:5],
            "retrieval_debug": {
                "base_candidate_count": len(rows),
                "scored_cell_count": len(memory_scores),
                "scene_expanded_cell_count": len(scene_expansion_ids),
                "hyperedge_expanded_cell_count": len(hyperedge_expansion_ids),
            },
        }

    def skillize_memory(self, lookback_days: int = 365, trade_date: str | None = None, min_samples: int | None = None) -> dict[str, Any]:
        end_date = normalize_trade_date(trade_date or self._today())
        start_date = shift_calendar_date(end_date, -int(lookback_days))
        threshold = int(min_samples or self.config.get("memory", {}).get("skillize_min_samples", 2))
        report = self.generate_evolution_report(lookback_days=lookback_days, trade_date=end_date, min_samples=threshold, write_artifact=False)
        created: list[dict[str, Any]] = []
        share_threshold = int(self.config.get("memory", {}).get("community_share_min_samples", 3))
        with self.db.connect() as conn:
            for item in report.get("quality_paths", [])[:8]:
                source_id = str(item.get("path_key") or "")
                if not source_id:
                    continue
                skill_id = self._skill_id("quality_path", source_id)
                trigger_conditions = item.get("components") or []
                do_not_use_when = [
                    "when the setup only matches by name but not by market stage",
                    "when current risk controls are missing",
                ]
                summary_markdown = "\n".join(
                    [
                        f"- Path: {item.get('path_key') or '-'}",
                        f"- Sample size: {item.get('sample_size') or 0}",
                        f"- Win rate: {item.get('win_rate_pct') or '-'}%",
                        f"- Avg return: {item.get('avg_actual_return_pct') or '-'}%",
                    ]
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_skill_cards(
                        skill_id, source_kind, source_id, title, intent, trigger_conditions_json, do_not_use_when_json,
                        evidence_trade_ids_json, sample_size, bandit_snapshot_json, summary_markdown, community_shareable,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        skill_id,
                        "quality_path",
                        source_id,
                        f"Reusable Trade Skill | {source_id}",
                        "Reuse a historically strong trade memory path as a pre-trade review checklist.",
                        json_dumps(trigger_conditions),
                        json_dumps(do_not_use_when),
                        json_dumps([example.get("trade_id") for example in item.get("examples", []) if example.get("trade_id")]),
                        int(item.get("sample_size") or 0),
                        json_dumps(
                            {
                                "ucb_score": item.get("ucb_score"),
                                "posterior_mean": item.get("posterior_mean"),
                                "conservative_score": item.get("conservative_score"),
                            }
                        ),
                        summary_markdown,
                        1 if int(item.get("sample_size") or 0) >= share_threshold else 0,
                        now_ts(),
                        now_ts(),
                    ),
                )
                created.append(
                    {
                        "skill_id": skill_id,
                        "source_kind": "quality_path",
                        "source_id": source_id,
                        "title": f"Reusable Trade Skill | {source_id}",
                        "intent": "Reuse a historically strong trade memory path as a pre-trade review checklist.",
                        "trigger_conditions_json": json_dumps(trigger_conditions),
                        "do_not_use_when_json": json_dumps(do_not_use_when),
                        "evidence_trade_ids_json": json_dumps([example.get("trade_id") for example in item.get("examples", []) if example.get("trade_id")]),
                        "sample_size": int(item.get("sample_size") or 0),
                        "bandit_snapshot_json": json_dumps(
                            {
                                "ucb_score": item.get("ucb_score"),
                                "posterior_mean": item.get("posterior_mean"),
                                "conservative_score": item.get("conservative_score"),
                            }
                        ),
                        "summary_markdown": summary_markdown,
                        "community_shareable": 1 if int(item.get("sample_size") or 0) >= share_threshold else 0,
                    }
                )
        if self._vault_enabled():
            for row in created:
                if row.get("skill_id"):
                    self.export_skill_note(row["skill_id"])
            if created:
                companion = self._export_vault_companion_notes()
            else:
                companion = {}
        else:
            companion = {}
        return {
            "period_start": start_date,
            "period_end": end_date,
            "created_skills": created,
            "vault_companion_notes": companion,
        }

    def revise_memory_cell(
        self,
        memory_id: str,
        *,
        title: str | None = None,
        text_body: str | None = None,
        trade_date: str | None = None,
        market_stage: str | None = None,
        strategy_line: str | None = None,
        tags: list[str] | str | None = None,
        add_tags: list[str] | str | None = None,
        remove_tags: list[str] | str | None = None,
        summary_patch: dict[str, Any] | None = None,
        quality_patch: dict[str, Any] | None = None,
        quality_score: float | None = None,
        correction_note: str | None = None,
    ) -> dict[str, Any]:
        memory_row = self.db.fetchone("SELECT * FROM memory_cells WHERE memory_id = ?", (memory_id,))
        if not memory_row:
            raise ValueError(f"memory cell not found: {memory_id}")
        summary = json_loads(memory_row.get("summary_json"), {}) or {}
        quality = json_loads(memory_row.get("quality_json"), {}) or {}
        current_tags = split_tags(json_loads(memory_row.get("tags_json"), []))
        if tags is not None:
            updated_tags = split_tags(tags)
        else:
            updated_tags = list(current_tags)
        for tag in split_tags(add_tags):
            if tag not in updated_tags:
                updated_tags.append(tag)
        for tag in split_tags(remove_tags):
            updated_tags = [item for item in updated_tags if item != tag]
        memory_kind = str(memory_row.get("memory_kind") or memory_row.get("source_entity_kind") or "").strip()
        if memory_kind and memory_kind not in updated_tags:
            updated_tags.insert(0, memory_kind)
        effective_trade_date = normalize_trade_date(trade_date or memory_row.get("trade_date") or self._today())
        effective_market_stage = str(market_stage if market_stage is not None else memory_row.get("market_stage") or "").strip()
        effective_strategy_line = str(strategy_line if strategy_line is not None else memory_row.get("strategy_line") or "").strip()
        ts_code = str(memory_row.get("ts_code") or "").strip()
        if ts_code and f"symbol:{ts_code}" not in updated_tags:
            updated_tags.append(f"symbol:{ts_code}")
        if effective_market_stage and f"stage:{effective_market_stage}" not in updated_tags:
            updated_tags.append(f"stage:{effective_market_stage}")
        if effective_strategy_line and f"strategy:{effective_strategy_line}" not in updated_tags:
            updated_tags.append(f"strategy:{effective_strategy_line}")
        updated_tags = list(dict.fromkeys(updated_tags))
        if summary_patch:
            summary.update(summary_patch)
        if quality_patch:
            quality.update(quality_patch)
        if quality_score is not None:
            quality["quality_score"] = float(quality_score)
        if correction_note:
            quality["correction_note"] = str(correction_note).strip()
        payload = {
            "title": title if title is not None else memory_row.get("title") or "",
            "text_body": text_body if text_body is not None else memory_row.get("text_body") or "",
            "trade_date": effective_trade_date,
            "market_stage": effective_market_stage,
            "strategy_line": effective_strategy_line,
            "summary_json": summary,
            "quality_json": quality,
            "tags_json": updated_tags,
            "updated_at": now_ts(),
            "memory_id": memory_id,
        }
        self.db.execute(
            """
            UPDATE memory_cells
            SET title = ?, text_body = ?, trade_date = ?, market_stage = ?, strategy_line = ?,
                summary_json = ?, quality_json = ?, tags_json = ?, updated_at = ?
            WHERE memory_id = ?
            """,
            (
                payload["title"],
                payload["text_body"],
                payload["trade_date"],
                payload["market_stage"],
                payload["strategy_line"],
                json_dumps(payload["summary_json"]),
                json_dumps(payload["quality_json"]),
                json_dumps(payload["tags_json"]),
                payload["updated_at"],
                payload["memory_id"],
            ),
        )
        stored = self.db.fetchone("SELECT * FROM memory_cells WHERE memory_id = ?", (memory_id,)) or {}
        self._reindex_memory_cell(stored)
        self._refresh_manual_memory_links(stored)
        self._write_memory_snapshot(stored)
        result = {"memory_cell": self.db.fetchone("SELECT * FROM memory_cells WHERE memory_id = ?", (memory_id,)) or {}}
        if self._vault_enabled():
            result["vault_note"] = self.export_memory_note(memory_id)
            result["vault_companion_notes"] = self._export_vault_companion_notes()
        return result

    def revise_skill_card(
        self,
        skill_id: str,
        *,
        title: str | None = None,
        intent: str | None = None,
        trigger_conditions: list[str] | str | None = None,
        add_trigger_conditions: list[str] | str | None = None,
        remove_trigger_conditions: list[str] | str | None = None,
        do_not_use_when: list[str] | str | None = None,
        add_do_not_use_when: list[str] | str | None = None,
        remove_do_not_use_when: list[str] | str | None = None,
        summary_markdown: str | None = None,
        community_shareable: bool | None = None,
    ) -> dict[str, Any]:
        skill_row = self.db.fetchone("SELECT * FROM memory_skill_cards WHERE skill_id = ?", (skill_id,))
        if not skill_row:
            raise ValueError(f"skill card not found: {skill_id}")
        triggers = split_tags(json_loads(skill_row.get("trigger_conditions_json"), []))
        if trigger_conditions is not None:
            triggers = split_tags(trigger_conditions)
        for tag in split_tags(add_trigger_conditions):
            if tag not in triggers:
                triggers.append(tag)
        for tag in split_tags(remove_trigger_conditions):
            triggers = [item for item in triggers if item != tag]
        guards = split_tags(json_loads(skill_row.get("do_not_use_when_json"), []))
        if do_not_use_when is not None:
            guards = split_tags(do_not_use_when)
        for tag in split_tags(add_do_not_use_when):
            if tag not in guards:
                guards.append(tag)
        for tag in split_tags(remove_do_not_use_when):
            guards = [item for item in guards if item != tag]
        payload = {
            "title": title if title is not None else skill_row.get("title") or "",
            "intent": intent if intent is not None else skill_row.get("intent") or "",
            "trigger_conditions_json": list(dict.fromkeys(triggers)),
            "do_not_use_when_json": list(dict.fromkeys(guards)),
            "summary_markdown": summary_markdown if summary_markdown is not None else skill_row.get("summary_markdown") or "",
            "community_shareable": int(community_shareable) if community_shareable is not None else int(skill_row.get("community_shareable") or 0),
            "updated_at": now_ts(),
            "skill_id": skill_id,
        }
        self.db.execute(
            """
            UPDATE memory_skill_cards
            SET title = ?, intent = ?, trigger_conditions_json = ?, do_not_use_when_json = ?,
                summary_markdown = ?, community_shareable = ?, updated_at = ?
            WHERE skill_id = ?
            """,
            (
                payload["title"],
                payload["intent"],
                json_dumps(payload["trigger_conditions_json"]),
                json_dumps(payload["do_not_use_when_json"]),
                payload["summary_markdown"],
                payload["community_shareable"],
                payload["updated_at"],
                payload["skill_id"],
            ),
        )
        result = {"skill_card": self.db.fetchone("SELECT * FROM memory_skill_cards WHERE skill_id = ?", (skill_id,)) or {}}
        if self._vault_enabled():
            result["vault_note"] = self.export_skill_note(skill_id)
            result["vault_companion_notes"] = self._export_vault_companion_notes()
        return result

    def _attach_memory_context(self, payload: dict[str, Any], *, fields: dict[str, Any] | None = None, entity_kind: str = "", entity_id: str = "") -> dict[str, Any]:
        merged = dict(payload)
        ts_code = str((fields or {}).get("ts_code") or "").strip()
        market_stage = str((fields or {}).get("market_stage") or (fields or {}).get("market_stage_tag") or "").strip()
        tag_values: list[str] = []
        if fields:
            for key in ("logic_tags", "pattern_tags", "environment_tags", "mistake_tags"):
                tag_values.extend(split_tags((fields or {}).get(key, [])))
            if not market_stage:
                market_stage = self._pick_market_stage((fields or {}).get("environment_tags"), fallback=market_stage)
        if not ts_code and entity_kind == "trade" and entity_id:
            trade = self.get_trade(entity_id) or {}
            ts_code = str(trade.get("ts_code") or "")
            market_stage = str(trade.get("market_stage_tag") or market_stage or "")
            tag_values.extend(split_tags(json_loads(trade.get("logic_type_tags_json"), [])))
            tag_values.extend(split_tags(json_loads(trade.get("pattern_tags_json"), [])))
            tag_values.extend(split_tags(json_loads(trade.get("environment_tags_json"), [])))
        if not ts_code and entity_kind == "plan" and entity_id:
            plan = self.get_plan(entity_id) or {}
            ts_code = str(plan.get("ts_code") or "")
            market_stage = str(plan.get("market_stage_tag") or market_stage or "")
            tag_values.extend(split_tags(json_loads(plan.get("logic_tags_json"), [])))
            tag_values.extend(split_tags(json_loads(plan.get("environment_tags_json"), [])))
        memory_result = self.query_memory(ts_code=ts_code or None, market_stage=market_stage or None, tags=tag_values, limit=5)
        merged["memory_retrieval"] = {
            "matched_cells": memory_result.get("matched_cells", []),
            "matched_scenes": memory_result.get("matched_scenes", []),
            "linked_skill_cards": memory_result.get("linked_skill_cards", []),
        }
        merged["memory_checklist"] = memory_result.get("memory_checklist", [])
        return merged

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
        aligned_market_stage, aligned_environment_tags = self._align_market_stage_and_environment_tags(market_stage, environment_tags)
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
                    aligned_market_stage,
                    json_dumps(aligned_environment_tags),
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
        plan["memory_cell"] = self._sync_memory_for_entity("plan", plan_id)
        result = {"plan": plan}
        if with_reference:
            result["reference"] = self.generate_reference(
                logic_tags=split_tags(logic_tags),
                market_stage=aligned_market_stage,
                environment_tags=aligned_environment_tags,
                lookback_days=lookback_days,
                write_artifact=False,
            )
        if split_tags(logic_tags) or aligned_market_stage or aligned_environment_tags:
            result["evolution_reminder"] = self.generate_evolution_reminder(
                logic_tags=split_tags(logic_tags),
                market_stage=aligned_market_stage,
                environment_tags=aligned_environment_tags,
                lookback_days=lookback_days,
                write_artifact=False,
            )
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_plan", True):
            result["vault_note"] = self.export_plan_note(plan_id)
            result["vault_companion_notes"] = self._export_vault_companion_notes()
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
        updated_plan = self.get_plan(plan_id) or {}
        updated_plan["memory_cell"] = self._sync_memory_for_entity("plan", plan_id)
        return updated_plan

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
        market_stage, merged_environment_tags = self._align_market_stage_and_environment_tags(
            plan.get("market_stage_tag") or "",
            merged_fields.get("environment_tags"),
        )
        merged_fields["environment_tags"] = merged_environment_tags
        merged_fields["market_stage"] = market_stage
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
        memory_cell = self._sync_memory_for_entity("plan", plan_id)
        reflection_prompts = build_reflection_prompts(merged_fields, "plan", [])
        response = {
            "plan": updated_plan,
            "memory_cell": memory_cell,
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
            response["vault_companion_notes"] = self._export_vault_companion_notes()
        return response

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

    def ensure_objective_review_subskill(self) -> dict[str, Any]:
        source_id = "objective_review_autofill_v1"
        skill_id = self._skill_id("system_subskill", source_id)
        existing = self.db.fetchone("SELECT created_at FROM memory_skill_cards WHERE skill_id = ?", (skill_id,)) or {}
        summary_markdown = "\n".join(
            [
                "- Scope: auto-fill objective review facts that do not depend on the trader's private reasoning.",
                "- Auto facts: holding days, realized return, benchmark return, timing alpha, market snapshot metrics when available.",
                "- Manual only: thesis, user focus, observed signals, position reason, emotion, lessons learned.",
                "- Suggested workflow: let the system fill objective context first, then let the user补主观逻辑和复盘教训.",
            ]
        )
        payload = {
            "skill_id": skill_id,
            "source_kind": "system_subskill",
            "source_id": source_id,
            "title": "Objective Review Autofill",
            "intent": "Auto-complete objective market and execution facts before the user writes subjective review notes.",
            "trigger_conditions_json": json_dumps(["objective_review", "market_snapshot", "auto_review"]),
            "do_not_use_when_json": json_dumps(
                [
                    "when market snapshot data is unavailable and only subjective review is needed",
                    "when the user is editing thesis, emotion, or lessons learned by hand",
                ]
            ),
            "evidence_trade_ids_json": json_dumps([]),
            "sample_size": 0,
            "bandit_snapshot_json": json_dumps({"kind": "system_subskill", "version": 1}),
            "summary_markdown": summary_markdown,
            "community_shareable": 1,
            "created_at": existing.get("created_at") or now_ts(),
            "updated_at": now_ts(),
        }
        self.db.execute(
            """
            INSERT OR REPLACE INTO memory_skill_cards(
                skill_id, source_kind, source_id, title, intent, trigger_conditions_json, do_not_use_when_json,
                evidence_trade_ids_json, sample_size, bandit_snapshot_json, summary_markdown, community_shareable,
                created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["skill_id"],
                payload["source_kind"],
                payload["source_id"],
                payload["title"],
                payload["intent"],
                payload["trigger_conditions_json"],
                payload["do_not_use_when_json"],
                payload["evidence_trade_ids_json"],
                payload["sample_size"],
                payload["bandit_snapshot_json"],
                payload["summary_markdown"],
                payload["community_shareable"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        if self._vault_enabled():
            self.export_skill_note(skill_id)
        return self.db.fetchone("SELECT * FROM memory_skill_cards WHERE skill_id = ?", (skill_id,)) or payload

    def capture_market_snapshot(
        self,
        trade_date: str,
        ts_code: str | None = None,
        *,
        name: str | None = None,
        sector_name: str | None = None,
        sector_change_pct: float | None = None,
    ) -> dict[str, Any]:
        if not self.market:
            return {}
        payload = self.market.build_market_snapshot(
            trade_date=trade_date,
            ts_code=ts_code,
            name=name,
            sector_name=sector_name,
            sector_change_pct=sector_change_pct,
        )
        snapshot_id = make_id("snapshot")
        sh_change = _coalesce_float(payload.get("sh_change_pct"))
        sector_change = _coalesce_float(payload.get("sector_change_pct"))
        sector_strength_tag = ""
        if sector_change is not None:
            reference = sh_change or 0.0
            if sector_change >= reference + 1.0:
                sector_strength_tag = "stronger_than_market"
            elif sector_change <= reference - 1.0:
                sector_strength_tag = "weaker_than_market"
            else:
                sector_strength_tag = "in_line_with_market"
        row = {
            "snapshot_id": snapshot_id,
            "trade_date": normalize_trade_date(payload.get("trade_date") or trade_date),
            "ts_code": normalize_ts_code(payload.get("ts_code") or ts_code or "") if (payload.get("ts_code") or ts_code) else "",
            "name": payload.get("name") or name or "",
            "sh_change_pct": sh_change,
            "cyb_change_pct": _coalesce_float(payload.get("cyb_change_pct")),
            "hs300_change_pct": _coalesce_float(payload.get("hs300_change_pct")),
            "zz1000_change_pct": _coalesce_float(payload.get("zz1000_change_pct")),
            "up_down_ratio": _coalesce_float(payload.get("up_down_ratio")),
            "advancers_count": payload.get("advancers_count"),
            "decliners_count": payload.get("decliners_count"),
            "flat_count": payload.get("flat_count"),
            "limit_up_count": payload.get("limit_up_count"),
            "limit_down_count": payload.get("limit_down_count"),
            "broken_limit_count": payload.get("broken_limit_count"),
            "sector_name": payload.get("sector_name") or sector_name or "",
            "sector_change_pct": sector_change,
            "sector_strength_tag": sector_strength_tag,
            "raw_payload_json": json_dumps(payload.get("raw_payload", {})),
            "created_at": now_ts(),
        }
        self.db.execute(
            """
            INSERT INTO market_snapshots(
                snapshot_id, trade_date, ts_code, name, sh_change_pct, cyb_change_pct, hs300_change_pct, zz1000_change_pct,
                up_down_ratio, advancers_count, decliners_count, flat_count, limit_up_count, limit_down_count, broken_limit_count,
                sector_name, sector_change_pct, sector_strength_tag,
                raw_payload_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["snapshot_id"],
                row["trade_date"],
                row["ts_code"],
                row["name"],
                row["sh_change_pct"],
                row["cyb_change_pct"],
                row["hs300_change_pct"],
                row["zz1000_change_pct"],
                row["up_down_ratio"],
                row["advancers_count"],
                row["decliners_count"],
                row["flat_count"],
                row["limit_up_count"],
                row["limit_down_count"],
                row["broken_limit_count"],
                row["sector_name"],
                row["sector_change_pct"],
                row["sector_strength_tag"],
                row["raw_payload_json"],
                row["created_at"],
            ),
        )
        return self.db.fetchone("SELECT * FROM market_snapshots WHERE snapshot_id = ?", (snapshot_id,)) or row

    def _build_objective_review_payload(
        self,
        trade: dict[str, Any],
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        skill_id = self._skill_id("system_subskill", "objective_review_autofill_v1")

        def _fmt_pct(value: Any) -> str:
            numeric = _coalesce_float(value)
            if numeric is None:
                return "-"
            return f"{numeric:+.2f}%"

        def _fmt_price(value: Any) -> str:
            numeric = _coalesce_float(value)
            if numeric is None:
                return "-"
            return f"{numeric:.2f}".rstrip("0").rstrip(".")

        actual_return = _coalesce_float(trade.get("actual_return_pct"))
        benchmark_return = _coalesce_float(trade.get("benchmark_return_pct"))
        timing_alpha = _coalesce_float(trade.get("timing_alpha_pct"))
        holding_days = trade.get("holding_days")

        data_sources = ["trade_facts"]
        if trade.get("sell_date"):
            execution_facts = (
                f"这笔交易于 {trade.get('buy_date') or '-'} 以 {_fmt_price(trade.get('buy_price'))} 买入，"
                f"于 {trade.get('sell_date') or '-'} 以 {_fmt_price(trade.get('sell_price'))} 卖出。"
            )
        else:
            execution_facts = (
                f"这笔交易于 {trade.get('buy_date') or '-'} 以 {_fmt_price(trade.get('buy_price'))} 开仓，"
                "当前尚未平仓。"
            )
        if actual_return is not None:
            performance_parts = []
            if holding_days is not None:
                performance_parts.append(f"持有 {holding_days} 天")
            performance_parts.append(f"实际收益 {_fmt_pct(actual_return)}")
            performance_parts.append(f"基准收益 {_fmt_pct(benchmark_return)}" if benchmark_return is not None else "基准收益暂缺")
            performance_parts.append(f"时机 Alpha {_fmt_pct(timing_alpha)}" if timing_alpha is not None else "时机 Alpha 暂缺")
            performance_summary = "客观结果：" + "，".join(performance_parts) + "。"
        else:
            performance_summary = "客观结果：当前尚未形成闭环，暂不计算实际收益、基准收益与时机 Alpha。"
        if benchmark_return is not None or timing_alpha is not None:
            data_sources.append("benchmark_compare")

        index_summary = ""
        breadth_summary = ""
        sector_summary = ""
        market_regime_summary = ""
        if snapshot:
            data_sources.append("market_snapshot")
            sh_change = _coalesce_float(snapshot.get("sh_change_pct"))
            cyb_change = _coalesce_float(snapshot.get("cyb_change_pct"))
            hs300_change = _coalesce_float(snapshot.get("hs300_change_pct"))
            zz1000_change = _coalesce_float(snapshot.get("zz1000_change_pct"))
            if any(value is not None for value in (sh_change, cyb_change, hs300_change, zz1000_change)):
                index_summary = (
                    f"宽基表现：上证 {_fmt_pct(sh_change)}，创业板 {_fmt_pct(cyb_change)}，"
                    f"沪深300 {_fmt_pct(hs300_change)}，中证1000 {_fmt_pct(zz1000_change)}。"
                )
            advancers = snapshot.get("advancers_count")
            decliners = snapshot.get("decliners_count")
            flat_count = snapshot.get("flat_count")
            breadth_segments: list[str] = []
            if advancers is not None and decliners is not None:
                breadth_segments.append(f"上涨 {advancers} 家、下跌 {decliners} 家")
            if flat_count is not None:
                breadth_segments.append(f"平盘 {flat_count} 家")
            if snapshot.get("up_down_ratio") is not None:
                breadth_segments.append(f"涨跌比 {snapshot.get('up_down_ratio')}")
            if snapshot.get("limit_up_count") is not None:
                breadth_segments.append(f"涨停 {snapshot.get('limit_up_count')} 家")
            if snapshot.get("limit_down_count") is not None:
                breadth_segments.append(f"跌停 {snapshot.get('limit_down_count')} 家")
            if snapshot.get("broken_limit_count") is not None:
                breadth_segments.append(f"炸板 {snapshot.get('broken_limit_count')} 家")
            if breadth_segments:
                breadth_summary = "市场广度：" + "，".join(breadth_segments) + "。"
            if snapshot.get("sector_name") or snapshot.get("sector_change_pct") is not None:
                sector_label = str(snapshot.get("sector_name") or "关联板块").strip()
                strength_label = str(snapshot.get("sector_strength_tag") or "").strip()
                sector_summary = (
                    f"板块表现：{sector_label} {_fmt_pct(snapshot.get('sector_change_pct'))}"
                    + (f"，相对大盘 {strength_label}。" if strength_label else "。")
                )
            if sh_change is not None and cyb_change is not None and snapshot.get("up_down_ratio") is not None:
                ratio = _coalesce_float(snapshot.get("up_down_ratio")) or 0.0
                if sh_change > 0 and cyb_change > 0 and ratio >= 1.2:
                    market_regime_summary = "客观市场状态：指数共振偏强，市场偏风险偏好。"
                elif sh_change < 0 and cyb_change < 0 and ratio <= 0.8:
                    market_regime_summary = "客观市场状态：指数同步走弱，市场偏风险规避。"
                else:
                    market_regime_summary = "客观市场状态：指数与个股强弱分化，市场更偏结构性。"

        summary_lines = [line for line in (execution_facts, performance_summary, index_summary, breadth_summary, sector_summary, market_regime_summary) if line]
        narrative_summary = " ".join(summary_lines)
        return {
            "skill_id": skill_id,
            "data_sources": data_sources,
            "execution_facts": execution_facts,
            "performance_summary": performance_summary,
            "index_summary": index_summary,
            "breadth_summary": breadth_summary,
            "sector_summary": sector_summary,
            "market_regime_summary": market_regime_summary,
            "narrative_summary": narrative_summary,
            "summary_lines": summary_lines,
            "auto_fill_note": "客观字段已自动补全；主观逻辑、情绪、教训仍需人工确认。",
        }

    def backfill_trade_objective_context(self) -> dict[str, Any]:
        self.ensure_objective_review_subskill()
        summary = {
            "trades_scanned": 0,
            "trades_updated": 0,
            "objective_review_filled": 0,
            "stress_level_removed": 0,
            "emotion_notes_merged": 0,
        }
        changed_trade_ids: list[str] = []
        rows = self.db.fetchall("SELECT * FROM trades ORDER BY buy_date ASC, updated_at ASC")
        summary["trades_scanned"] = len(rows)

        with self.db.connect() as conn:
            for trade in rows:
                context = json_loads(trade.get("decision_context_json"), {}) or {}
                updated_context = dict(context)
                snapshot = None
                if trade.get("snapshot_id"):
                    snapshot = self.db.fetchone("SELECT * FROM market_snapshots WHERE snapshot_id = ?", (trade.get("snapshot_id"),))
                objective_review = self._build_objective_review_payload(trade, snapshot=snapshot)
                merged_emotion = str(trade.get("emotion_notes") or "").strip()
                legacy_stress = updated_context.pop("stress_level", None)
                changed = False
                if legacy_stress not in (None, ""):
                    summary["stress_level_removed"] += 1
                    stress_note = f"压力感受（旧字段）：{legacy_stress}"
                    if stress_note not in merged_emotion:
                        merged_emotion = self._append_text_block(merged_emotion, stress_note)
                        summary["emotion_notes_merged"] += 1
                    changed = True
                if updated_context.get("objective_review") != objective_review:
                    updated_context["objective_review"] = objective_review
                    summary["objective_review_filled"] += 1
                    changed = True
                if not changed and merged_emotion == str(trade.get("emotion_notes") or "").strip():
                    continue
                conn.execute(
                    "UPDATE trades SET decision_context_json = ?, emotion_notes = ?, updated_at = ? WHERE trade_id = ?",
                    (
                        json_dumps({key: value for key, value in updated_context.items() if value not in (None, '', [], {})}),
                        merged_emotion,
                        now_ts(),
                        trade.get("trade_id") or "",
                    ),
                )
                changed_trade_ids.append(str(trade.get("trade_id") or ""))

        for trade_id in changed_trade_ids:
            self._sync_memory_for_entity("trade", trade_id)
        summary["trades_updated"] = len(changed_trade_ids)
        return summary

    def backfill_trade_market_snapshots(self, *, force_refresh: bool = False) -> dict[str, Any]:
        summary = {
            "trades_scanned": 0,
            "snapshots_created": 0,
            "trades_updated": 0,
            "skipped_without_market": 0,
            "errors": [],
        }
        if not self.market:
            summary["skipped_without_market"] = 1
            return summary
        rows = self.db.fetchall("SELECT * FROM trades ORDER BY buy_date ASC, updated_at ASC")
        summary["trades_scanned"] = len(rows)
        changed_trade_ids: list[str] = []
        snapshot_cache: dict[str, dict[str, Any]] = {}

        def _has_core_data(snapshot_row: dict[str, Any] | None) -> bool:
            if not snapshot_row:
                return False
            return any(
                snapshot_row.get(key) is not None
                for key in ("sh_change_pct", "cyb_change_pct", "hs300_change_pct", "zz1000_change_pct", "advancers_count", "limit_up_count")
            )

        for trade in rows:
            trade_date = trade.get("buy_date") or trade.get("sell_date") or self._today()
            existing_snapshot = None
            if trade.get("snapshot_id"):
                existing_snapshot = self.db.fetchone("SELECT * FROM market_snapshots WHERE snapshot_id = ?", (trade.get("snapshot_id"),))
            elif trade_date in snapshot_cache:
                existing_snapshot = snapshot_cache.get(trade_date)
            elif not force_refresh:
                existing_snapshot = self.db.fetchone(
                    """
                    SELECT * FROM market_snapshots
                    WHERE trade_date = ?
                    ORDER BY
                        (CASE WHEN advancers_count IS NOT NULL OR limit_up_count IS NOT NULL OR sh_change_pct IS NOT NULL THEN 1 ELSE 0 END) DESC,
                        created_at DESC
                    LIMIT 1
                    """,
                    (trade_date,),
                )
            needs_snapshot = force_refresh or not existing_snapshot
            if existing_snapshot and not force_refresh:
                needs_snapshot = not _has_core_data(existing_snapshot)
            if not needs_snapshot:
                snapshot = existing_snapshot or {}
            else:
                try:
                    snapshot = self.capture_market_snapshot(
                        trade_date,
                        trade.get("ts_code"),
                        name=trade.get("name"),
                    )
                except Exception as exc:
                    summary["errors"].append(f"{trade.get('trade_id')}: {exc}")
                    continue
                summary["snapshots_created"] += 1
                snapshot_cache[trade_date] = snapshot
            context = json_loads(trade.get("decision_context_json"), {}) or {}
            context["objective_review"] = self._build_objective_review_payload(trade, snapshot=snapshot)
            self.db.execute(
                "UPDATE trades SET snapshot_id = ?, decision_context_json = ?, updated_at = ? WHERE trade_id = ?",
                (
                    snapshot.get("snapshot_id") or "",
                    json_dumps({key: value for key, value in context.items() if value not in (None, '', [], {})}),
                    now_ts(),
                    trade.get("trade_id") or "",
                ),
            )
            changed_trade_ids.append(str(trade.get("trade_id") or ""))
        for trade_id in changed_trade_ids:
            self._sync_memory_for_entity("trade", trade_id)
        summary["trades_updated"] = len(changed_trade_ids)
        return summary

    def backfill_trade_review_fields(self) -> dict[str, Any]:
        summary = {
            "trades_scanned": 0,
            "trades_updated": 0,
            "mistake_tags_filled": 0,
            "position_confidence_filled": 0,
        }
        changed_trade_ids: list[str] = []
        rows = self.db.fetchall("SELECT * FROM trades ORDER BY buy_date ASC, updated_at ASC")
        summary["trades_scanned"] = len(rows)

        with self.db.connect() as conn:
            for trade in rows:
                context = json_loads(trade.get("decision_context_json"), {}) or {}
                updated_context = dict(context)
                updated_context.pop("stress_level", None)
                existing_mistake_tags = split_tags(json_loads(trade.get("mistake_tags_json"), []))
                derived_mistake_tags = self._derive_mistake_tags_from_lessons(
                    trade.get("lessons_learned"),
                    existing_tags=existing_mistake_tags,
                    actual_return_pct=_coalesce_float(trade.get("actual_return_pct")),
                )
                derived_confidence = self._derive_position_confidence(
                    existing_value=updated_context.get("position_confidence"),
                    thesis=trade.get("thesis"),
                    buy_reason=trade.get("buy_reason"),
                    sell_reason=trade.get("sell_reason"),
                    notes=trade.get("notes"),
                    emotion_notes=trade.get("emotion_notes"),
                    lessons_learned=trade.get("lessons_learned"),
                )

                changed = False
                if derived_mistake_tags != existing_mistake_tags:
                    summary["mistake_tags_filled"] += 1
                    changed = True
                if updated_context.get("position_confidence") in (None, "") and derived_confidence is not None:
                    updated_context["position_confidence"] = derived_confidence
                    summary["position_confidence_filled"] += 1
                    changed = True
                if self._merge_unique_tags(updated_context.get("mistake_tags", [])) != self._merge_unique_tags(derived_mistake_tags):
                    if derived_mistake_tags:
                        updated_context["mistake_tags"] = derived_mistake_tags
                    else:
                        updated_context.pop("mistake_tags", None)
                    changed = True
                if not changed:
                    continue

                conn.execute(
                    "UPDATE trades SET mistake_tags_json = ?, decision_context_json = ?, updated_at = ? WHERE trade_id = ?",
                    (
                        json_dumps(derived_mistake_tags),
                        json_dumps({key: value for key, value in updated_context.items() if value not in (None, '', [], {})}),
                        now_ts(),
                        trade.get("trade_id") or "",
                    ),
                )
                changed_trade_ids.append(str(trade.get("trade_id") or ""))

        for trade_id in changed_trade_ids:
            self._sync_memory_for_entity("trade", trade_id)
        summary["trades_updated"] = len(changed_trade_ids)
        return summary

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
        statement_context: dict[str, Any] | None = None,
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
        aligned_market_stage, aligned_environment_tags = self._align_market_stage_and_environment_tags(
            market_stage_tag,
            environment_tags,
        )
        plan = self.get_plan(plan_id) if plan_id else None
        snapshot = None
        if fetch_snapshot:
            snapshot = self.capture_market_snapshot(normalized_buy_date, code, name=resolved_name, sector_name=sector_name, sector_change_pct=sector_change_pct)
        actual_return = compute_return_pct(float(buy_price), float(sell_price)) if sell_price is not None else None
        benchmark_return = self._compute_benchmark_return(code, normalized_buy_date, normalized_sell_date) if normalized_sell_date else None
        timing_alpha = round(actual_return - benchmark_return, 2) if actual_return is not None and benchmark_return is not None else None
        holding_days = self._compute_holding_days(normalized_buy_date, normalized_sell_date) if normalized_sell_date else None
        deviation = calculate_plan_execution_deviation(plan, float(buy_price), float(sell_price) if sell_price is not None else None)
        journal_kind = "closed_trade" if normalized_sell_date else "open_trade"
        derived_mistake_tags = self._derive_mistake_tags_from_lessons(
            lessons_learned,
            existing_tags=mistake_tags,
            actual_return_pct=actual_return,
        )
        derived_position_confidence = self._derive_position_confidence(
            existing_value=(decision_context or {}).get("position_confidence"),
            thesis=thesis,
            buy_reason=buy_reason,
            sell_reason=sell_reason,
            notes=notes,
            emotion_notes=emotion_notes,
            lessons_learned=lessons_learned,
        )
        decision_payload = self._decision_context_from_fields(
            {
                "ts_code": code,
                "name": resolved_name,
                "thesis": thesis,
                "user_focus": (decision_context or {}).get("user_focus", []),
                "observed_signals": (decision_context or {}).get("observed_signals", []),
                "position_reason": (decision_context or {}).get("position_reason", ""),
                "position_confidence": derived_position_confidence,
                "position_size_pct": position_size_pct,
                "emotion_notes": emotion_notes or "",
                "mistake_tags": derived_mistake_tags,
                "environment_tags": aligned_environment_tags,
                "notes": notes or "",
            },
            journal_kind,
            base_context=decision_context or {},
        )
        decision_payload["objective_review"] = self._build_objective_review_payload(
            {
                "buy_date": normalized_buy_date,
                "buy_price": float(buy_price),
                "sell_date": normalized_sell_date,
                "sell_price": float(sell_price) if sell_price is not None else None,
                "actual_return_pct": actual_return,
                "benchmark_return_pct": benchmark_return,
                "timing_alpha_pct": timing_alpha,
                "holding_days": holding_days,
            },
            snapshot=snapshot,
        )
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
                    decision_context_json, statement_context_json,
                    review_status, status, emotion_notes, mistake_tags_json, lessons_learned, notes, created_at, updated_at
                ) VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    aligned_market_stage,
                    json_dumps(aligned_environment_tags),
                    snapshot.get("snapshot_id") if snapshot else "",
                    benchmark_return,
                    actual_return,
                    timing_alpha,
                    holding_days,
                    json_dumps(deviation),
                    json_dumps(decision_payload),
                    json_dumps(statement_context or {}),
                    "pending",
                    "closed" if normalized_sell_date else "open",
                    emotion_notes or "",
                    json_dumps(derived_mistake_tags),
                    lessons_learned or "",
                    notes or "",
                    timestamp,
                    timestamp,
                ),
            )
        if plan_id:
            self.update_plan_status(plan_id, "executed", trade_id=trade_id)
        trade_row = self.get_trade(trade_id) or {}
        trade_row["memory_cell"] = self._sync_memory_for_entity("trade", trade_id)
        if split_tags(logic_type_tags) or split_tags(pattern_tags) or aligned_market_stage or aligned_environment_tags:
            trade_row["evolution_reminder"] = self.generate_evolution_reminder(
                logic_tags=split_tags(logic_type_tags),
                pattern_tags=split_tags(pattern_tags),
                market_stage=aligned_market_stage,
                environment_tags=aligned_environment_tags,
                trade_date=normalized_buy_date,
                write_artifact=False,
            )
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_trade", True):
            trade_row["vault_note"] = self.export_trade_note(trade_id)
            trade_row["daily_vault_note"] = self.export_daily_note(normalized_buy_date)
            trade_row["vault_companion_notes"] = self._export_vault_companion_notes()
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
        statement_context: dict[str, Any] | None = None,
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
        merged_lessons = "\n".join(part for part in [trade.get("lessons_learned") or "", lessons_learned or ""] if part).strip()
        merged_mistake_tags = self._derive_mistake_tags_from_lessons(
            merged_lessons,
            existing_tags=existing_mistakes + [tag for tag in split_tags(mistake_tags) if tag not in existing_mistakes],
            actual_return_pct=actual_return,
        )
        updated_context = self._decision_context_from_fields(
            self._trade_to_journal_fields(
                {
                    **trade,
                    "sell_date": normalized_sell_date,
                    "sell_price": float(sell_price),
                    "sell_reason": sell_reason,
                    "sell_position": sell_position,
                    "emotion_notes": merged_emotion,
                    "notes": merged_notes,
                    "lessons_learned": merged_lessons,
                    "mistake_tags_json": json_dumps(merged_mistake_tags),
                }
            ),
            "closed_trade",
            base_context=json_loads(trade.get("decision_context_json"), {}) or {},
        )
        if updated_context.get("position_confidence") in (None, ""):
            updated_context["position_confidence"] = self._derive_position_confidence(
                existing_value=updated_context.get("position_confidence"),
                thesis=trade.get("thesis"),
                buy_reason=trade.get("buy_reason"),
                sell_reason=sell_reason or trade.get("sell_reason"),
                notes=merged_notes,
                emotion_notes=merged_emotion,
                lessons_learned=merged_lessons,
            )
        snapshot = None
        if trade.get("snapshot_id"):
            snapshot = self.db.fetchone("SELECT * FROM market_snapshots WHERE snapshot_id = ?", (trade.get("snapshot_id"),))
        updated_context["objective_review"] = self._build_objective_review_payload(
            {
                **trade,
                "sell_date": normalized_sell_date,
                "sell_price": float(sell_price),
                "actual_return_pct": actual_return,
                "benchmark_return_pct": benchmark_return,
                "timing_alpha_pct": timing_alpha,
                "holding_days": holding_days,
            },
            snapshot=snapshot,
        )
        merged_statement_context = self._merge_statement_context(
            json_loads(trade.get("statement_context_json"), {}) or {},
            statement_context,
        )
        self.db.execute(
            """
            UPDATE trades
            SET sell_date = ?, sell_price = ?, sell_reason = ?, sell_position = ?, benchmark_return_pct = ?,
                actual_return_pct = ?, timing_alpha_pct = ?, holding_days = ?, plan_execution_deviation_json = ?,
                status = 'closed', updated_at = ?, emotion_notes = ?, mistake_tags_json = ?, lessons_learned = ?, notes = ?,
                statement_context_json = ?, decision_context_json = ?
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
                json_dumps(merged_statement_context),
                json_dumps({key: value for key, value in updated_context.items() if value not in (None, "", [], {})}),
                trade_id,
            ),
        )
        trade_row = self.get_trade(trade_id) or {}
        trade_row["memory_cell"] = self._sync_memory_for_entity("trade", trade_id)
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_trade", True):
            trade_row["vault_note"] = self.export_trade_note(trade_id)
            trade_row["daily_vault_note"] = self.export_daily_note(normalized_sell_date)
            trade_row["vault_companion_notes"] = self._export_vault_companion_notes()
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
        market_stage, merged_environment_tags = self._align_market_stage_and_environment_tags(
            trade.get("market_stage_tag") or "",
            merged_fields.get("environment_tags"),
        )
        merged_fields["environment_tags"] = merged_environment_tags
        merged_fields["market_stage"] = market_stage
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
        merged_fields["mistake_tags"] = self._derive_mistake_tags_from_lessons(
            merged_fields.get("lessons_learned"),
            existing_tags=merged_fields.get("mistake_tags", []),
            actual_return_pct=actual_return,
        )
        merged_fields["position_confidence"] = self._derive_position_confidence(
            existing_value=merged_fields.get("position_confidence"),
            thesis=merged_fields.get("thesis"),
            buy_reason=trade.get("buy_reason"),
            sell_reason=trade.get("sell_reason"),
            notes=merged_fields.get("notes"),
            emotion_notes=merged_fields.get("emotion_notes"),
            lessons_learned=merged_fields.get("lessons_learned"),
        )
        decision_context = self._decision_context_from_fields(
            merged_fields,
            "closed_trade" if normalized_sell_date else "open_trade",
            base_context=json_loads(trade.get("decision_context_json"), {}) or {},
        )
        snapshot = None
        if trade.get("snapshot_id"):
            snapshot = self.db.fetchone("SELECT * FROM market_snapshots WHERE snapshot_id = ?", (trade.get("snapshot_id"),))
        decision_context["objective_review"] = self._build_objective_review_payload(
            {
                **trade,
                "buy_date": normalized_buy_date,
                "buy_price": buy_price,
                "sell_date": normalized_sell_date,
                "sell_price": sell_price,
                "actual_return_pct": actual_return,
                "benchmark_return_pct": benchmark_return,
                "timing_alpha_pct": timing_alpha,
                "holding_days": holding_days,
            },
            snapshot=snapshot,
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
        memory_cell = self._sync_memory_for_entity("trade", trade_id)
        journal_kind = "closed_trade" if normalized_sell_date else "open_trade"
        reflection_prompts = build_reflection_prompts(merged_fields, journal_kind, [])
        response = {
            "trade": updated_trade,
            "memory_cell": memory_cell,
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
            response["vault_companion_notes"] = self._export_vault_companion_notes()
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

    def _load_delimited_statement_rows(
        self,
        path: Path,
        *,
        encoding_candidates: list[str],
        delimiter: str,
    ) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for encoding in encoding_candidates:
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle, delimiter=delimiter)
                    rows = [
                        { _statement_text_value(key): value for key, value in dict(row or {}).items() if _statement_text_value(key) }
                        for row in reader
                        if any(str(value or "").strip() for value in (row or {}).values())
                    ]
                if rows:
                    return rows
            except UnicodeDecodeError as exc:
                last_error = exc
            except csv.Error as exc:
                last_error = exc
        if last_error:
            raise last_error
        return []

    def _load_excel_statement_rows(self, path: Path) -> list[dict[str, Any]]:
        import pandas as pd

        excel_book = pd.ExcelFile(path)
        rows: list[dict[str, Any]] = []
        for sheet_name in excel_book.sheet_names:
            frame = pd.read_excel(path, sheet_name=sheet_name).fillna("")
            rows.extend(
                {_statement_text_value(key): value for key, value in item.items() if _statement_text_value(key)}
                for item in frame.to_dict(orient="records")
            )
        return rows

    def _load_fixed_width_statement_rows(
        self,
        path: Path,
        *,
        encoding_candidates: list[str],
    ) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for encoding in encoding_candidates:
            try:
                with path.open("r", encoding=encoding) as handle:
                    lines = [line.rstrip("\r\n") for line in handle]
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
            except OSError as exc:
                last_error = exc
                continue

            content_lines = [line for line in lines if line.strip() and not set(line.strip()) <= {"-"}]
            if not content_lines:
                return []
            header = [_statement_text_value(part) for part in re.split(r"\s{2,}", content_lines[0].strip()) if _statement_text_value(part)]
            if len(header) < 2:
                continue

            rows: list[dict[str, Any]] = []
            for line in content_lines[1:]:
                parts = [_statement_text_value(part) for part in re.split(r"\s{2,}", line.strip())]
                if len(parts) < len(header):
                    continue
                row = {
                    header[index]: parts[index]
                    for index in range(len(header))
                    if header[index] and index < len(parts) and parts[index] != ""
                }
                if row:
                    rows.append(row)
            if rows:
                return rows
        if last_error:
            raise last_error
        return []

    def _statement_numeric_sum(self, rows: list[dict[str, Any]], *keys: str) -> float | None:
        total = 0.0
        has_value = False
        for row in rows:
            value = self._statement_row_float(row, *keys)
            if value is None:
                continue
            total += value
            has_value = True
        if not has_value:
            return None
        return total

    def _statement_row_total_fee(self, row: dict[str, Any]) -> float | None:
        explicit_fee = self._statement_row_float(row, "手续费", "fee")
        primary_fee = explicit_fee if explicit_fee is not None else self._statement_row_float(row, "佣金", "commission")
        values = [
            primary_fee,
            self._statement_row_float(row, "印花税", "stamp_duty"),
            self._statement_row_float(row, "过户费", "transfer_fee"),
            self._statement_row_float(row, "其他费", "other_fee"),
        ]
        numeric_values = [value for value in values if value is not None]
        if not numeric_values:
            return None
        return sum(numeric_values)

    def _statement_row_effective_price(self, row: dict[str, Any]) -> float | None:
        quantity = self._statement_row_float(row, "quantity", "qty", "成交数量", "数量")
        occurred_amount = self._statement_row_float(row, "发生金额", "occurred_amount", "net_amount", "actual_amount")
        if quantity is None or abs(quantity) <= 1e-6 or occurred_amount is None:
            return None
        return abs(occurred_amount) / quantity

    def _aggregate_statement_group(
        self,
        rows: list[dict[str, Any]],
        *,
        trade_date: str,
        side_kind: str,
        ts_code: str,
        name: str,
        account: str,
    ) -> dict[str, Any]:
        if len(rows) == 1:
            return dict(rows[0])

        ordered_rows = sorted(
            rows,
            key=lambda row: (
                self._statement_row_value(row, "trade_time", "成交时间", "time"),
                self._statement_row_value(row, "成交编号", "委托编号", "statement_id"),
            ),
        )
        quantity = self._statement_numeric_sum(ordered_rows, "quantity", "qty", "成交数量", "数量")
        amount = self._statement_numeric_sum(ordered_rows, "amount", "成交金额", "金额")
        occurred_amount = self._statement_numeric_sum(ordered_rows, "发生金额", "occurred_amount", "net_amount", "actual_amount")
        explicit_fee = self._statement_numeric_sum(ordered_rows, "手续费", "fee")
        commission = self._statement_numeric_sum(ordered_rows, "佣金", "commission")
        stamp_duty = self._statement_numeric_sum(ordered_rows, "印花税", "stamp_duty")
        transfer_fee = self._statement_numeric_sum(ordered_rows, "过户费", "transfer_fee")
        other_fee = self._statement_numeric_sum(ordered_rows, "其他费", "other_fee")
        primary_fee = explicit_fee if explicit_fee is not None else commission
        total_fee = sum(value for value in (primary_fee, stamp_duty, transfer_fee, other_fee) if value is not None)
        weighted_amount = 0.0
        weighted_has_value = False
        for row in ordered_rows:
            row_quantity = self._statement_row_float(row, "quantity", "qty", "成交数量", "数量")
            row_price = self._statement_row_float(row, "trade_price", "成交价格", "成交均价", "price", "均价", "成交价")
            if row_quantity is None or row_price is None:
                continue
            weighted_amount += row_quantity * row_price
            weighted_has_value = True
        trade_price: float | None = None
        if quantity is not None and abs(quantity) > 1e-6:
            if amount is not None:
                trade_price = amount / quantity
            elif weighted_has_value:
                trade_price = weighted_amount / quantity

        first_row = dict(ordered_rows[0])
        first_time = self._statement_row_value(first_row, "trade_time", "成交时间", "time")
        last_time = self._statement_row_value(ordered_rows[-1], "trade_time", "成交时间", "time")
        statement_ids = [
            self._statement_row_value(row, "成交编号", "委托编号", "statement_id")
            for row in ordered_rows
            if self._statement_row_value(row, "成交编号", "委托编号", "statement_id")
        ]
        statement_id_seed = "|".join(statement_ids) or "|".join(
            [
                trade_date,
                account,
                ts_code,
                side_kind,
                first_time,
                last_time,
                str(quantity or ""),
            ]
        )
        aggregated_statement_id = f"agg:{hashlib.sha1(statement_id_seed.encode('utf-8')).hexdigest()[:16]}"
        first_row.update(
            {
                "成交日期": trade_date,
                "trade_date": trade_date,
                "证券代码": ts_code.replace(".SH", "").replace(".SZ", ""),
                "ts_code": ts_code,
                "证券名称": name or self._statement_row_value(first_row, "证券名称", "股票名称", "名称", "name"),
                "name": name or self._statement_row_value(first_row, "证券名称", "股票名称", "名称", "name"),
                "股东账户": account,
                "account": account,
                "委托类别": "买入" if side_kind == "buy" else "卖出",
                "side": "买入" if side_kind == "buy" else "卖出",
                "成交时间": first_time,
                "trade_time": first_time,
                "成交编号": aggregated_statement_id,
                "statement_id": aggregated_statement_id,
                "成交数量": round(quantity, 6) if quantity is not None else "",
                "quantity": round(quantity, 6) if quantity is not None else "",
                "成交金额": round(amount, 6) if amount is not None else "",
                "amount": round(amount, 6) if amount is not None else "",
                "发生金额": round(occurred_amount, 6) if occurred_amount is not None else "",
                "occurred_amount": round(occurred_amount, 6) if occurred_amount is not None else "",
                "佣金": round(commission, 6) if commission is not None else "",
                "commission": round(commission, 6) if commission is not None else "",
                "印花税": round(stamp_duty, 6) if stamp_duty is not None else "",
                "stamp_duty": round(stamp_duty, 6) if stamp_duty is not None else "",
                "过户费": round(transfer_fee, 6) if transfer_fee is not None else "",
                "transfer_fee": round(transfer_fee, 6) if transfer_fee is not None else "",
                "其他费": round(other_fee, 6) if other_fee is not None else "",
                "other_fee": round(other_fee, 6) if other_fee is not None else "",
                "手续费": round(total_fee, 6) if total_fee else "",
                "fee": round(total_fee, 6) if total_fee else "",
                "成交价格": round(trade_price, 6) if trade_price is not None else "",
                "trade_price": round(trade_price, 6) if trade_price is not None else "",
                "__aggregation__": {
                    "mode": "same_day_same_side",
                    "group_size": len(ordered_rows),
                    "trade_time_start": first_time,
                    "trade_time_end": last_time,
                    "statement_ids": statement_ids,
                    "effective_price": round(abs(occurred_amount) / quantity, 6)
                    if occurred_amount is not None and quantity is not None and abs(quantity) > 1e-6
                    else None,
                    "legs": [
                        {
                            "trade_time": self._statement_row_value(row, "trade_time", "成交时间", "time"),
                            "statement_id": self._statement_row_value(row, "成交编号", "委托编号", "statement_id"),
                            "trade_price": self._statement_row_float(row, "trade_price", "成交价格", "成交均价", "price", "均价", "成交价"),
                            "quantity": self._statement_row_float(row, "quantity", "qty", "成交数量", "数量"),
                            "amount": self._statement_row_float(row, "amount", "成交金额", "金额"),
                            "occurred_amount": self._statement_row_float(row, "发生金额", "occurred_amount", "net_amount", "actual_amount"),
                        }
                        for row in ordered_rows
                    ],
                },
            }
        )
        return first_row

    def _aggregate_statement_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        default_trade_date: str | None = None,
    ) -> list[dict[str, Any]]:
        grouped_rows: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        passthrough_rows: list[tuple[int, dict[str, Any]]] = []
        group_order: list[tuple[tuple[str, str, str, str], int]] = []
        normalized_default_trade_date = normalize_trade_date(default_trade_date or self._today())

        for index, raw_row in enumerate(rows):
            row = dict(raw_row or {})
            generic_date = self._statement_row_value(row, "trade_date", "成交日期", "date", "成交时间")
            trade_date = normalize_trade_date(generic_date or normalized_default_trade_date)
            side_kind = _statement_side_kind(self._statement_row_value(row, "side", "direction", "买卖标志", "成交方向", "委托类别", "操作"))
            account = self._statement_row_value(row, "股东账户", "证券账户", "account")
            ts_code_raw = self._statement_row_value(row, "ts_code", "code", "symbol", "证券代码", "股票代码", "代码")
            ts_code = normalize_ts_code(ts_code_raw) if ts_code_raw else ""
            name = self._statement_row_value(row, "name", "证券名称", "股票名称", "名称")
            if not trade_date or not side_kind or not account or not ts_code:
                passthrough_rows.append((index, row))
                continue
            key = (trade_date, account, ts_code, side_kind)
            if key not in grouped_rows:
                grouped_rows[key] = []
                group_order.append((key, index))
            grouped_rows[key].append(row)

        aggregated: list[tuple[int, dict[str, Any]]] = list(passthrough_rows)
        for key, first_index in group_order:
            trade_date, account, ts_code, side_kind = key
            bucket = grouped_rows[key]
            aggregated.append(
                (
                    first_index,
                    self._aggregate_statement_group(
                        bucket,
                        trade_date=trade_date,
                        side_kind=side_kind,
                        ts_code=ts_code,
                        name=self._statement_row_value(bucket[0], "name", "证券名称", "股票名称", "名称"),
                        account=account,
                    ),
                )
            )
        aggregated.sort(key=lambda item: item[0])
        return [row for _, row in aggregated]

    def _load_statement_rows(self, path: Path) -> list[dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                rows = payload.get("rows") or payload.get("items") or []
            else:
                rows = payload
            if not isinstance(rows, list):
                raise ValueError("statement payload must be a list of row objects")
            return [
                {_statement_text_value(key): value for key, value in dict(row or {}).items() if _statement_text_value(key)}
                for row in rows
            ]
        if suffix in {".txt"}:
            return self._load_fixed_width_statement_rows(path, encoding_candidates=["utf-8-sig", "utf-8", "gbk"])
        if suffix in {".csv"}:
            return self._load_delimited_statement_rows(path, encoding_candidates=["utf-8-sig", "utf-8", "gbk"], delimiter=",")
        if suffix in {".tsv"}:
            return self._load_delimited_statement_rows(path, encoding_candidates=["utf-8-sig", "utf-8", "gbk"], delimiter="\t")
        if suffix in {".xls", ".xlsx"}:
            text_rows = self._load_delimited_statement_rows(path, encoding_candidates=["utf-8-sig", "utf-8", "gbk"], delimiter="\t")
            if text_rows:
                return text_rows
            return self._load_excel_statement_rows(path)
        raise ValueError(f"unsupported statement file type: {suffix or path.name}")

    def _statement_row_value(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return _statement_text_value(row.get(key))
        return ""

    def _statement_row_float(self, row: dict[str, Any], *keys: str) -> float | None:
        raw = self._statement_row_value(row, *keys)
        if not raw:
            return None
        cleaned = raw.replace(",", "").replace(" ", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _statement_context_from_row(self, normalized: dict[str, Any], row: dict[str, Any], *, source_file: str = "") -> dict[str, Any]:
        aggregation_meta = dict(row.get("__aggregation__") or {})
        leg_payload = {
            "trade_date": normalized.get("buy_date") or normalized.get("sell_date") or "",
            "trade_time": self._statement_row_value(row, "trade_time", "成交时间", "time"),
            "trade_time_end": aggregation_meta.get("trade_time_end") or "",
            "quantity": normalized.get("quantity"),
            "amount": normalized.get("amount"),
            "fee": normalized.get("fee"),
            "total_fee": self._statement_row_total_fee(row),
            "effective_price": aggregation_meta.get("effective_price") or self._statement_row_effective_price(row),
            "occurred_amount": self._statement_row_float(row, "发生金额", "net_amount", "actual_amount"),
            "commission": self._statement_row_float(row, "佣金", "commission"),
            "stamp_duty": self._statement_row_float(row, "印花税", "stamp_duty"),
            "transfer_fee": self._statement_row_float(row, "过户费", "transfer_fee"),
            "other_fee": self._statement_row_float(row, "其他费", "other_fee"),
            "shareholder_account": self._statement_row_value(row, "股东账户", "证券账户", "account"),
            "statement_id": self._statement_row_value(row, "成交编号", "委托编号", "statement_id"),
            "side": self._statement_row_value(row, "side", "direction", "买卖标志", "成交方向", "委托类别", "操作"),
            "aggregation_mode": aggregation_meta.get("mode") or "",
            "aggregated_row_count": aggregation_meta.get("group_size"),
            "statement_ids": aggregation_meta.get("statement_ids") or [],
            "legs": aggregation_meta.get("legs") or [],
        }
        leg_payload = {key: value for key, value in leg_payload.items() if value not in (None, "", [])}
        payload = {
            "source_file": source_file,
            "last_imported_at": now_ts(),
            "last_normalized_side": normalized.get("journal_kind") or "",
        }
        if normalized.get("journal_kind") == "close_only":
            payload["sell_leg"] = leg_payload
        elif normalized.get("journal_kind") == "closed_trade":
            payload["buy_leg"] = dict(leg_payload)
            payload["sell_leg"] = dict(leg_payload)
        else:
            payload["buy_leg"] = leg_payload
        return payload

    def _merge_statement_context(
        self,
        existing: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in dict(incoming or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged.get(key) or {})
                nested.update({inner_key: inner_value for inner_key, inner_value in value.items() if inner_value not in (None, "", [])})
                merged[key] = nested
            elif value not in (None, "", []):
                merged[key] = value
        return merged

    def _update_trade_statement_context(self, trade_id: str, statement_context: dict[str, Any], notes: str = "") -> dict[str, Any]:
        trade = self.get_trade(trade_id)
        if not trade:
            raise ValueError(f"trade not found: {trade_id}")
        merged_context = self._merge_statement_context(
            json_loads(trade.get("statement_context_json"), {}) or {},
            statement_context,
        )
        merged_notes = "\n".join(part for part in [trade.get("notes") or "", notes] if part).strip()
        self.db.execute(
            "UPDATE trades SET statement_context_json = ?, notes = ?, updated_at = ? WHERE trade_id = ?",
            (json_dumps(merged_context), merged_notes, now_ts(), trade_id),
        )
        return self.get_trade(trade_id) or {}

    def _normalize_statement_row(self, row: dict[str, Any], default_trade_date: str | None = None) -> dict[str, Any]:
        side = self._statement_row_value(row, "side", "direction", "买卖标志", "成交方向", "委托类别", "操作").lower()
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

    def _find_statement_trade_matches(
        self,
        normalized: dict[str, Any],
        statement_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ts_code = normalized.get("ts_code") or ""
        if not ts_code:
            return []
        candidates = self.db.fetchall(
            "SELECT * FROM trades WHERE ts_code = ? ORDER BY updated_at DESC LIMIT 50",
            (ts_code,),
        )
        sell_leg = dict((statement_context or {}).get("sell_leg") or {})
        sell_statement_id = str(sell_leg.get("statement_id") or "").strip()
        sell_account = str(sell_leg.get("shareholder_account") or "").strip()
        target_buy_quantity = _coalesce_float(normalized.get("quantity"))
        target_sell_quantity = _coalesce_float(sell_leg.get("quantity")) or _coalesce_float(normalized.get("quantity"))
        if normalized.get("journal_kind") == "close_only" and sell_statement_id:
            statement_matches: list[dict[str, Any]] = []
            for trade in candidates:
                if trade.get("status") != "closed":
                    continue
                if normalized.get("sell_date") and trade.get("sell_date") != normalized.get("sell_date"):
                    continue
                if normalized.get("sell_price") is not None and trade.get("sell_price") and not self._trade_price_matches(trade.get("sell_price"), normalized.get("sell_price")):
                    continue
                if self._trade_statement_id(trade, leg_key="sell_leg") != sell_statement_id:
                    continue
                candidate_account = self._trade_statement_account(trade, leg_key="sell_leg")
                if sell_account and candidate_account and candidate_account != sell_account:
                    continue
                if not self._trade_statement_quantity_matches(trade, target_sell_quantity, leg_key="sell_leg"):
                    continue
                statement_matches.append(trade)
            if statement_matches:
                return statement_matches
        matches: list[dict[str, Any]] = []
        for trade in candidates:
            if normalized.get("buy_date") and trade.get("buy_date") != normalized.get("buy_date"):
                continue
            if normalized.get("buy_price") is not None and not self._trade_price_matches(trade.get("buy_price"), normalized.get("buy_price")):
                continue
            if not self._trade_statement_quantity_matches(trade, target_buy_quantity, leg_key="buy_leg"):
                continue
            if normalized.get("sell_date") and trade.get("sell_date") != normalized.get("sell_date"):
                continue
            if normalized.get("sell_price") is not None and trade.get("sell_date") and not self._trade_price_matches(trade.get("sell_price"), normalized.get("sell_price")):
                continue
            if normalized.get("sell_date") and not self._trade_statement_quantity_matches(trade, target_sell_quantity, leg_key="sell_leg"):
                continue
            matches.append(trade)
        return matches

    def _trade_statement_leg(self, trade: dict[str, Any], leg_key: str = "buy_leg") -> dict[str, Any]:
        context = json_loads(trade.get("statement_context_json"), {}) or {}
        return dict(context.get(leg_key) or {})

    def _trade_statement_leg_value(self, trade: dict[str, Any], key: str, leg_key: str = "buy_leg") -> Any:
        return self._trade_statement_leg(trade, leg_key=leg_key).get(key)

    def _trade_statement_quantity(self, trade: dict[str, Any], leg_key: str = "buy_leg") -> float | None:
        return _coalesce_float(self._trade_statement_leg_value(trade, "quantity", leg_key=leg_key))

    def _trade_statement_quantity_matches(self, trade: dict[str, Any], quantity: float | None, *, leg_key: str = "buy_leg") -> bool:
        if quantity is None:
            return True
        candidate_quantity = self._trade_statement_quantity(trade, leg_key=leg_key)
        if candidate_quantity is None:
            return True
        return abs(candidate_quantity - quantity) <= 1e-6

    def _trade_statement_account(self, trade: dict[str, Any], leg_key: str = "buy_leg") -> str:
        return str(self._trade_statement_leg_value(trade, "shareholder_account", leg_key=leg_key) or "").strip()

    def _trade_statement_id(self, trade: dict[str, Any], leg_key: str = "buy_leg") -> str:
        return str(self._trade_statement_leg_value(trade, "statement_id", leg_key=leg_key) or "").strip()

    def _trade_sell_date_matches(self, trade: dict[str, Any], sell_date: str) -> bool:
        left = normalize_trade_date(trade.get("sell_date")) if trade.get("sell_date") else ""
        right = normalize_trade_date(sell_date) if sell_date else ""
        return left == right

    def _find_existing_trade_clone(self, source_trade: dict[str, Any]) -> dict[str, Any] | None:
        candidates = self.db.fetchall(
            "SELECT * FROM trades WHERE ts_code = ? AND buy_date = ? ORDER BY updated_at DESC LIMIT 20",
            (source_trade.get("ts_code") or "", source_trade.get("buy_date") or ""),
        )
        source_buy_qty = self._trade_statement_quantity(source_trade, leg_key="buy_leg")
        source_sell_qty = self._trade_statement_quantity(source_trade, leg_key="sell_leg")
        source_sell_price = _coalesce_float(source_trade.get("sell_price"))
        for candidate in candidates:
            if not self._trade_price_matches(candidate.get("buy_price"), source_trade.get("buy_price")):
                continue
            if not self._trade_statement_quantity_matches(candidate, source_buy_qty, leg_key="buy_leg"):
                continue
            if not self._trade_sell_date_matches(candidate, source_trade.get("sell_date") or ""):
                continue
            if source_sell_price is not None and not self._trade_price_matches(candidate.get("sell_price"), source_sell_price):
                continue
            if source_sell_qty is not None and not self._trade_statement_quantity_matches(candidate, source_sell_qty, leg_key="sell_leg"):
                continue
            return candidate
        return None

    def _filtered_statement_close_candidates(
        self,
        normalized: dict[str, Any],
        candidates: list[dict[str, Any]],
        statement_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        sell_date = str(normalized.get("sell_date") or "")
        sell_account = str((statement_context.get("sell_leg") or {}).get("shareholder_account") or "").strip()
        filtered = [
            item
            for item in candidates
            if not sell_date or not item.get("buy_date") or str(item.get("buy_date")) <= sell_date
        ]
        if sell_account:
            exact_account_matches = [item for item in filtered if self._trade_statement_account(item) == sell_account]
            if exact_account_matches:
                return exact_account_matches
            return [
                item
                for item in filtered
                if not self._trade_statement_account(item) or self._trade_statement_account(item) == sell_account
            ]
        return filtered

    def _find_unique_quantity_subset(
        self,
        candidates: list[dict[str, Any]],
        target_quantity: float,
        max_candidates: int = 10,
    ) -> list[dict[str, Any]]:
        quantity_candidates: list[tuple[dict[str, Any], int]] = []
        for candidate in candidates:
            candidate_qty = self._trade_statement_quantity(candidate)
            if candidate_qty is None or candidate_qty <= 0:
                continue
            quantity_candidates.append((candidate, int(round(candidate_qty * 1000))))
        if not quantity_candidates or len(quantity_candidates) > max_candidates:
            return []

        target = int(round(target_quantity * 1000))
        matches: list[list[dict[str, Any]]] = []

        def backtrack(index: int, remaining: int, chosen: list[dict[str, Any]]) -> None:
            if len(matches) > 1:
                return
            if remaining == 0:
                matches.append(list(chosen))
                return
            if remaining < 0 or index >= len(quantity_candidates):
                return
            candidate, quantity = quantity_candidates[index]
            chosen.append(candidate)
            backtrack(index + 1, remaining - quantity, chosen)
            chosen.pop()
            backtrack(index + 1, remaining, chosen)

        backtrack(0, target, [])
        if len(matches) == 1:
            return matches[0]
        return []

    def _resolve_statement_close_candidates(
        self,
        normalized: dict[str, Any],
        candidates: list[dict[str, Any]],
        statement_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        filtered = self._filtered_statement_close_candidates(normalized, candidates, statement_context)
        if len(filtered) == 1:
            return filtered
        sell_quantity = _coalesce_float(normalized.get("quantity"))
        if sell_quantity is None:
            return []

        quantity_matches = []
        for item in filtered:
            candidate_qty = self._trade_statement_quantity(item)
            if candidate_qty is None or abs(candidate_qty - sell_quantity) > 1e-6:
                continue
            quantity_matches.append(item)
        if len(quantity_matches) == 1:
            return quantity_matches

        return self._find_unique_quantity_subset(filtered, sell_quantity)

    def _resolve_statement_close_candidate(self, normalized: dict[str, Any], candidates: list[dict[str, Any]], statement_context: dict[str, Any]) -> dict[str, Any] | None:
        resolved = self._resolve_statement_close_candidates(normalized, candidates, statement_context)
        if len(resolved) == 1:
            return resolved[0]
        return None

    def _allocate_statement_close_context(
        self,
        statement_context: dict[str, Any],
        trade: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(statement_context or {})
        sell_leg = dict(payload.get("sell_leg") or {})
        if not sell_leg:
            return payload
        matched_quantity = self._trade_statement_quantity(trade)
        reported_quantity = _coalesce_float(sell_leg.get("quantity"))
        if matched_quantity is not None:
            sell_leg["matched_quantity"] = matched_quantity
        if matched_quantity is not None and reported_quantity and reported_quantity > 0:
            sell_leg["reported_quantity"] = reported_quantity
            if abs(matched_quantity - reported_quantity) > 1e-6:
                ratio = matched_quantity / reported_quantity
                sell_leg["quantity"] = matched_quantity
                sell_leg["allocation_ratio"] = round(ratio, 6)
                for key in ("amount", "fee", "occurred_amount", "commission", "stamp_duty", "transfer_fee", "other_fee"):
                    value = _coalesce_float(sell_leg.get(key))
                    if value is not None:
                        sell_leg[key] = round(value * ratio, 6)
        payload["sell_leg"] = sell_leg
        return payload

    def _statement_follow_up_payload(self, trade_row: dict[str, Any]) -> dict[str, Any]:
        fields = self._trade_to_journal_fields(trade_row)
        journal_kind = "closed_trade" if trade_row.get("sell_date") else "open_trade"
        evaluation = evaluate_journal_fields(fields, journal_kind)
        reflection_prompts = build_reflection_prompts(fields, journal_kind, evaluation["missing_fields"])
        completeness = build_completeness_report(fields, journal_kind, missing_fields=evaluation["missing_fields"])
        return {
            "trade_id": trade_row.get("trade_id") or "",
            "journal_kind": journal_kind,
            "standardized_record": build_standardized_record(fields, journal_kind),
            "missing_fields": evaluation["missing_fields"],
            "follow_up_questions": evaluation["follow_up_questions"],
            "reflection_prompts": reflection_prompts,
            "completeness": completeness,
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

    def _build_parallel_follow_up_groups(self, backlog_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []

        def add_group(scope: str, group_key: str, label: str, question: str, fields: list[str], items: list[dict[str, Any]]) -> None:
            unique_fields = [field for field in fields if field]
            if len(items) < 2 or not unique_fields:
                return
            trade_ids = [str(item.get("trade_id") or "") for item in items if item.get("trade_id")]
            if len(trade_ids) < 2:
                return
            groups.append(
                {
                    "scope": scope,
                    "group_key": group_key,
                    "label": label,
                    "question": question,
                    "fields": unique_fields,
                    "trade_ids": trade_ids,
                    "trade_count": len(trade_ids),
                }
            )

        grouped_by_date: dict[str, list[dict[str, Any]]] = {}
        grouped_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for item in backlog_items:
            trade_date = str(item.get("trade_date") or "")
            ts_code = str(item.get("ts_code") or "")
            if trade_date:
                grouped_by_date.setdefault(trade_date, []).append(item)
            if ts_code:
                grouped_by_symbol.setdefault(ts_code, []).append(item)

        for trade_date, items in grouped_by_date.items():
            fields = [
                name
                for name in ("user_focus", "environment_tags", "observed_signals")
                if any(name in (entry.get("missing_context_fields") or []) for entry in items)
            ]
            add_group(
                "trade_date",
                trade_date,
                "同日环境并行补问",
                "如果这几笔是同一天的交易，可一次补市场环境、关注对象和触发信号，再按单笔交易回填。",
                fields,
                items,
            )

        for ts_code, items in grouped_by_symbol.items():
            fields = [
                name
                for name in ("thesis", "user_focus", "observed_signals", "position_reason")
                if any(name in (entry.get("missing_context_fields") or []) for entry in items)
            ]
            add_group(
                "symbol",
                ts_code,
                "同票主线并行补问",
                "如果这些成交只是同一只票反复做 T 或沿同一主线交易，可一次补选股理由、触发信号和仓位理由。",
                fields,
                items,
            )
        return groups[:12]

    def build_trade_follow_up_backlog(
        self,
        *,
        trade_ids: list[str] | None = None,
        status: str | None = None,
        limit: int = 200,
        trade_date: str | None = None,
        ts_code: str | None = None,
        include_complete: bool = False,
    ) -> dict[str, Any]:
        if trade_ids:
            placeholders = ",".join("?" for _ in trade_ids)
            rows = self.db.fetchall(
                f"SELECT * FROM trades WHERE trade_id IN ({placeholders}) ORDER BY buy_date DESC, updated_at DESC",
                tuple(trade_ids),
            )
        else:
            sql = "SELECT * FROM trades WHERE 1 = 1"
            params: list[Any] = []
            if status:
                sql += " AND status = ?"
                params.append(status)
            if trade_date:
                token = normalize_trade_date(trade_date)
                sql += " AND (buy_date = ? OR sell_date = ?)"
                params.extend([token, token])
            if ts_code:
                sql += " AND ts_code = ?"
                params.append(normalize_ts_code(ts_code))
            sql += " ORDER BY buy_date DESC, updated_at DESC"
            if limit > 0:
                sql += f" LIMIT {int(limit)}"
            rows = self.db.fetchall(sql, tuple(params))

        backlog_items: list[dict[str, Any]] = []
        incomplete_count = 0
        complete_count = 0
        for trade in rows:
            follow_up = self._statement_follow_up_payload(trade)
            completeness = follow_up.get("completeness") or {}
            is_incomplete = bool(completeness.get("needs_follow_up"))
            if is_incomplete:
                incomplete_count += 1
            else:
                complete_count += 1
                if not include_complete:
                    continue
            missing_context_fields = list(
                dict.fromkeys((completeness.get("core_missing_fields") or []) + (completeness.get("review_missing_fields") or []))
            )
            backlog_items.append(
                {
                    "trade_id": trade.get("trade_id") or "",
                    "status": trade.get("status") or "",
                    "ts_code": trade.get("ts_code") or "",
                    "name": trade.get("name") or "",
                    "thesis": trade.get("thesis") or "",
                    "trade_date": trade.get("buy_date") or trade.get("sell_date") or "",
                    "buy_date": trade.get("buy_date") or "",
                    "sell_date": trade.get("sell_date") or "",
                    "journal_kind": follow_up.get("journal_kind") or "",
                    "missing_required_fields": completeness.get("required_missing_fields") or [],
                    "missing_context_fields": missing_context_fields,
                    "blocking_missing_fields": completeness.get("blocking_missing_fields") or [],
                    "completion_score": completeness.get("completion_score"),
                    "ready_for_evolution": bool(completeness.get("ready_for_evolution")),
                    "next_question": ((follow_up.get("polling_bundle") or {}).get("next_question") or ""),
                    "assistant_message": follow_up.get("assistant_message") or "",
                    "shared_context_hints": ((follow_up.get("polling_bundle") or {}).get("shared_context_hints") or []),
                    "parallel_question_groups": ((follow_up.get("polling_bundle") or {}).get("parallel_question_groups") or []),
                }
            )

        summary = {
            "total_scanned": len(rows),
            "incomplete_trades": incomplete_count,
            "complete_trades": complete_count,
            "reported_items": len(backlog_items),
            "ready_for_evolution": sum(1 for item in backlog_items if item.get("ready_for_evolution")),
            "blocking_missing_total": sum(len(item.get("blocking_missing_fields") or []) for item in backlog_items if item.get("blocking_missing_fields")),
            "context_missing_total": sum(len(item.get("missing_context_fields") or []) for item in backlog_items if item.get("missing_context_fields")),
        }
        return {
            "summary": summary,
            "items": backlog_items,
            "parallel_groups": self._build_parallel_follow_up_groups(backlog_items),
        }

    def _follow_up_trade_label(self, item: dict[str, Any]) -> str:
        return (
            f"{item.get('trade_id') or '-'} | "
            f"{item.get('ts_code') or '-'} {item.get('name') or ''} | "
            f"buy={item.get('buy_date') or '-'} | sell={item.get('sell_date') or '-'}"
        ).strip()

    def _build_group_follow_up_batch(
        self,
        group: dict[str, Any],
        item_map: dict[str, dict[str, Any]],
        *,
        max_group_trades: int,
    ) -> dict[str, Any] | None:
        selected_items = [
            item_map[trade_id]
            for trade_id in list(group.get("trade_ids") or [])[:max_group_trades]
            if trade_id in item_map
        ]
        if len(selected_items) < 2:
            return None

        scope = str(group.get("scope") or "")
        fields = list(group.get("fields") or [])
        thesis_hints = self._collect_thesis_polish_hints(selected_items)
        if scope == "trade_date":
            title = f"{group.get('label')}: {group.get('group_key')}"
            prompt_lines = [
                f"请一次补完 {len(selected_items)} 笔同日交易的共享市场环境。",
                "请尽量按字段名填写，没有就写“无”，这样回填最稳。",
                "相关交易：",
                *[f"- {self._follow_up_trade_label(item)}" for item in selected_items],
                "建议模板：",
                "1. 市场主题/阶段：...",
                "2. 关注对象：...",
                "3. 触发信号：...",
                "4. 逐笔补充：",
                *[
                    f"   - {item.get('trade_id')}：核心逻辑=...；仓位理由=...；差异说明=..."
                    for item in selected_items
                ],
            ]
            if thesis_hints:
                prompt_lines.extend(["可参考润色（不改变原意）：", *[f"- {text}" for text in thesis_hints]])
            prompt = "\n".join(prompt_lines)
            answer_template = "\n".join(
                [
                    "1. 市场主题/阶段：...",
                    "2. 关注对象：...",
                    "3. 触发信号：...",
                    "4. 逐笔补充：",
                    *[
                        f"   - {item.get('trade_id')}：核心逻辑=...；仓位理由=...；差异说明=..."
                        for item in selected_items
                    ],
                ]
            )
        else:
            title = f"{group.get('label')}: {group.get('group_key')}"
            prompt_lines = [
                f"请一次补完 {len(selected_items)} 笔同票/同主线交易的共享原因。",
                "请尽量按字段名填写，没有就写“无”，这样不容易串字段。",
                "相关交易：",
                *[f"- {self._follow_up_trade_label(item)}" for item in selected_items],
                "建议模板：",
                "1. 核心逻辑：...",
                "2. 关注对象：...",
                "3. 触发信号：...",
                "4. 仓位理由：...",
                "5. 逐笔差异：",
                *[
                    f"   - {item.get('trade_id')}：差异说明=...；市场主题/阶段=..."
                    for item in selected_items
                ],
            ]
            if thesis_hints:
                prompt_lines.extend(["可参考润色（不改变原意）：", *[f"- {text}" for text in thesis_hints]])
            prompt = "\n".join(prompt_lines)
            answer_template = "\n".join(
                [
                    "1. 核心逻辑：...",
                    "2. 关注对象：...",
                    "3. 触发信号：...",
                    "4. 仓位理由：...",
                    "5. 逐笔差异：",
                    *[
                        f"   - {item.get('trade_id')}：差异说明=...；市场主题/阶段=..."
                        for item in selected_items
                    ],
                ]
            )
        return {
            "batch_id": f"{scope}:{group.get('group_key')}",
            "kind": "parallel_group",
            "scope": scope,
            "title": title,
            "trade_ids": [str(item.get("trade_id") or "") for item in selected_items],
            "fields": fields,
            "trade_refs": [self._follow_up_trade_label(item) for item in selected_items],
            "prompt": prompt,
            "answer_template": answer_template,
            "question": group.get("question") or "",
        }

    def _build_single_follow_up_batch(self, item: dict[str, Any]) -> dict[str, Any]:
        missing_context_fields = list(item.get("missing_context_fields") or [])
        answer_fields = missing_context_fields[:5] if missing_context_fields else ["thesis", "user_focus", "observed_signals"]
        prompt = "\n".join(
            [
                "请补这笔交易缺失的主观信息。",
                "请尽量逐项按“字段名：内容”填写，没有就写“无”。",
                f"交易：{self._follow_up_trade_label(item)}",
                f"当前优先问题：{item.get('next_question') or '请补核心逻辑与市场环境。'}",
                "建议模板：",
                self._answer_template_for_fields(answer_fields),
            ]
        )
        answer_template = self._answer_template_for_fields(answer_fields)
        return {
            "batch_id": f"trade:{item.get('trade_id')}",
            "kind": "single_trade",
            "scope": "trade",
            "title": f"单笔补问: {item.get('ts_code') or '-'} {item.get('name') or ''}".strip(),
            "trade_ids": [str(item.get("trade_id") or "")],
            "fields": answer_fields,
            "trade_refs": [self._follow_up_trade_label(item)],
            "prompt": prompt,
            "answer_template": answer_template,
            "question": item.get("next_question") or "",
        }

    def build_gateway_follow_up_batches(
        self,
        *,
        trade_ids: list[str] | None = None,
        status: str | None = None,
        limit: int = 200,
        trade_date: str | None = None,
        ts_code: str | None = None,
        include_complete: bool = False,
        max_group_batches: int = 12,
        max_group_trades: int = 6,
        max_single_batches: int = 12,
    ) -> dict[str, Any]:
        backlog = self.build_trade_follow_up_backlog(
            trade_ids=trade_ids,
            status=status,
            limit=limit,
            trade_date=trade_date,
            ts_code=ts_code,
            include_complete=include_complete,
        )
        items = list(backlog.get("items") or [])
        item_map = {str(item.get("trade_id") or ""): item for item in items if item.get("trade_id")}
        covered_trade_ids: set[str] = set()
        batches: list[dict[str, Any]] = []

        for group in list(backlog.get("parallel_groups") or [])[:max_group_batches]:
            batch = self._build_group_follow_up_batch(group, item_map, max_group_trades=max_group_trades)
            if not batch:
                continue
            batches.append(batch)
            covered_trade_ids.update(batch["trade_ids"])

        single_candidates = [item for item in items if str(item.get("trade_id") or "") not in covered_trade_ids]
        for item in single_candidates[:max_single_batches]:
            batches.append(self._build_single_follow_up_batch(item))

        return {
            "summary": {
                **dict(backlog.get("summary") or {}),
                "group_batches": sum(1 for item in batches if item.get("kind") == "parallel_group"),
                "single_batches": sum(1 for item in batches if item.get("kind") == "single_trade"),
                "total_batches": len(batches),
            },
            "batches": batches,
            "backlog": backlog,
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
        normalized_trade_date = normalize_trade_date(trade_date or self._today())
        source_rows = self._load_statement_rows(path)
        rows = self._aggregate_statement_rows(
            source_rows,
            default_trade_date=normalized_trade_date,
        )

        imported_items: list[dict[str, Any]] = []
        for index, raw_row in enumerate(rows, start=1):
            row = dict(raw_row or {})
            normalized = self._normalize_statement_row(row, default_trade_date=normalized_trade_date)
            statement_context = self._statement_context_from_row(normalized, row, source_file=path.name)
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
                exact_matches = self._find_statement_trade_matches(normalized, statement_context=statement_context)
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
                if not exact_trade and normalized["journal_kind"] == "open_trade" and len(exact_matches) == 1:
                    exact_trade = exact_matches[0]
                if exact_trade:
                    exact_trade = self._update_trade_statement_context(
                        exact_trade["trade_id"],
                        statement_context,
                        notes=normalized.get("notes") or "",
                    )
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
                            statement_context=statement_context,
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
                    statement_context=statement_context,
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

            exact_matches = self._find_statement_trade_matches(normalized, statement_context=statement_context)
            if exact_matches:
                for exact_trade in exact_matches:
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

            open_candidates = self._open_trade_candidates(normalized["ts_code"])
            resolved_candidates = self._resolve_statement_close_candidates(normalized, open_candidates, statement_context)
            if resolved_candidates:
                matched_trade_ids = [item.get("trade_id") or "" for item in resolved_candidates]
                for resolved_candidate in resolved_candidates:
                    closed_trade = self.close_trade(
                        resolved_candidate["trade_id"],
                        sell_date=normalized["sell_date"],
                        sell_price=float(normalized["sell_price"]),
                        statement_context=self._allocate_statement_close_context(statement_context, resolved_candidate),
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
                            "matched_trade_ids": matched_trade_ids,
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
            "source_rows": len(source_rows),
            "aggregated_rows": len(rows),
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
        if successful_items:
            payload["completeness_backlog"] = self.build_trade_follow_up_backlog(
                trade_ids=[str(item.get("trade_id") or "") for item in successful_items if item.get("trade_id")],
                include_complete=False,
            )
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

    def adopt_prior_holdings(
        self,
        source_db_path: str,
        *,
        visible_start_date: str,
    ) -> dict[str, Any]:
        source_db = FinanceJournalDB(Path(source_db_path))
        normalized_start = normalize_trade_date(visible_start_date)
        source_trades = source_db.fetchall(
            """
            SELECT * FROM trades
            WHERE buy_date < ? AND (sell_date >= ? OR status = 'open' OR sell_date = '')
            ORDER BY buy_date ASC, updated_at ASC
            """,
            (normalized_start, normalized_start),
        )

        imported_items: list[dict[str, Any]] = []
        for source_trade in source_trades:
            existing = self._find_existing_trade_clone(source_trade)
            if existing:
                imported_items.append(
                    {
                        "status": "matched_existing",
                        "source_trade_id": source_trade.get("trade_id") or "",
                        "trade_id": existing.get("trade_id") or "",
                        "ts_code": source_trade.get("ts_code") or "",
                    }
                )
                continue

            decision_context = json_loads(source_trade.get("decision_context_json"), {}) or {}
            carry_forward_meta = {
                "enabled": True,
                "source_trade_id": source_trade.get("trade_id") or "",
                "source_db_path": str(Path(source_db_path)),
                "visible_start_date": normalized_start,
            }
            decision_context["carry_forward"] = carry_forward_meta

            statement_context = json_loads(source_trade.get("statement_context_json"), {}) or {}
            statement_context["carry_forward"] = carry_forward_meta
            notes_prefix = f"[carry-forward] prior holding adopted for {normalized_start}"
            combined_notes = "\n".join(
                part for part in [notes_prefix, source_trade.get("notes") or ""] if part
            ).strip()

            cloned_trade = self.log_trade(
                ts_code=source_trade["ts_code"],
                name=source_trade.get("name") or None,
                plan_id=source_trade.get("plan_id") or None,
                buy_date=source_trade["buy_date"],
                buy_price=float(source_trade["buy_price"]),
                thesis=source_trade.get("thesis") or "",
                direction=source_trade.get("direction") or "long",
                buy_reason=source_trade.get("buy_reason") or "",
                buy_position=source_trade.get("buy_position") or "",
                sell_date=source_trade.get("sell_date") or None,
                sell_price=float(source_trade["sell_price"]) if source_trade.get("sell_price") is not None else None,
                sell_reason=source_trade.get("sell_reason") or "",
                sell_position=source_trade.get("sell_position") or "",
                position_size_pct=_coalesce_float(source_trade.get("position_size_pct")),
                logic_type_tags=json_loads(source_trade.get("logic_type_tags_json"), []),
                pattern_tags=json_loads(source_trade.get("pattern_tags_json"), []),
                theme=source_trade.get("theme") or None,
                market_stage_tag=source_trade.get("market_stage_tag") or None,
                environment_tags=json_loads(source_trade.get("environment_tags_json"), []),
                emotion_notes=source_trade.get("emotion_notes") or None,
                mistake_tags=json_loads(source_trade.get("mistake_tags_json"), []),
                lessons_learned=source_trade.get("lessons_learned") or None,
                decision_context=decision_context,
                statement_context=statement_context,
                notes=combined_notes,
                fetch_snapshot=False,
            )
            imported_items.append(
                {
                    "status": "imported_prior_holding",
                    "source_trade_id": source_trade.get("trade_id") or "",
                    "trade_id": cloned_trade.get("trade_id") or "",
                    "ts_code": source_trade.get("ts_code") or "",
                    "buy_date": source_trade.get("buy_date") or "",
                    "sell_date": source_trade.get("sell_date") or "",
                }
            )

        return {
            "source_db_path": str(Path(source_db_path)),
            "visible_start_date": normalized_start,
            "summary": {
                "source_candidates": len(source_trades),
                "imported_prior_holding": sum(1 for item in imported_items if item.get("status") == "imported_prior_holding"),
                "matched_existing": sum(1 for item in imported_items if item.get("status") == "matched_existing"),
            },
            "items": imported_items,
        }

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
        payload["data_completeness"] = self.build_trade_follow_up_backlog(
            trade_ids=[str(item.get("trade_id") or "") for item in trades if item.get("trade_id")],
            include_complete=True,
        )
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
        payload["memory_candidates"] = self.query_memory(
            ts_code=None,
            market_stage=market_stage,
            tags=split_tags(logic_tags) + split_tags(pattern_tags) + split_tags(environment_tags),
            limit=5,
        )
        payload["linked_skill_cards"] = payload["memory_candidates"].get("linked_skill_cards", [])
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
        payload["data_completeness"] = self.build_trade_follow_up_backlog(
            trade_ids=[str(item.get("trade_id") or "") for item in trades if item.get("trade_id")],
            include_complete=True,
        )
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
        payload["memory_candidates"] = self.query_memory(
            market_stage=market_stage,
            tags=split_tags(logic_tags) + split_tags(environment_tags),
            limit=5,
        )
        payload["linked_skill_cards"] = payload["memory_candidates"].get("linked_skill_cards", [])
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
            created_review = self.db.fetchone("SELECT * FROM reviews WHERE review_id = ?", (review_id,)) or {}
            if created_review.get("review_id"):
                created_review["memory_cell"] = self._sync_memory_for_entity("review", created_review["review_id"])
            created.append(created_review)
        payload = {"as_of_date": token, "created_reviews": created, "skipped": skipped}
        payload["artifact_paths"] = self._write_artifact(token, "review_cycle", payload, None)
        if self._vault_enabled() and created:
            payload["vault_notes"] = [self.export_review_note(item["review_id"]) for item in created if item.get("review_id")]
            payload["daily_vault_note"] = self.export_daily_note(token)
            payload["vault_companion_notes"] = self._export_vault_companion_notes()
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
        review_row["memory_cell"] = self._sync_memory_for_entity("review", review_id)
        if self._vault_enabled() and self.config.get("vault", {}).get("auto_export_after_review", True):
            review_row["vault_note"] = self.export_review_note(review_id)
            review_row["daily_vault_note"] = self.export_daily_note(review_row.get("review_due_date") or review_row.get("sell_date") or self._today())
            review_row["vault_companion_notes"] = self._export_vault_companion_notes()
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
            payload["graph_vault_note"] = self.export_graph_note()
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
        if current_hhmm >= str(schedules.get("memory_compaction_time", "08:00")):
            actions.append(
                {
                    "slot": f"memory_compaction:{today}",
                    "kind": "memory_compaction",
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
            if item["kind"] == "memory_compaction":
                rebuild = self.rebuild_memory(limit=int(self.config.get("memory", {}).get("compaction_limit", 200)))
                skillize = self.skillize_memory(lookback_days=365, trade_date=today)
                result = {"rebuild": rebuild, "skillize": skillize}
                artifact_paths = self._write_artifact(today, f"memory_compaction_{today}", result)
                artifact = artifact_paths.get("json") or ""
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
