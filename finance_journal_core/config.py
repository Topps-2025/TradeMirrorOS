from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "default_root": "",
    "timezone": "Asia/Shanghai",
    "database": {
        "relative_path": "data/finance_journal.db",
    },
    "schedules": {
        "event_fetch_times": [],
        "fetch_events_before_morning_brief": False,
        "morning_brief_time": "08:00",
        "plan_reminder_time": "08:30",
        "review_run_time": "17:30",
        "health_report_time": "08:10",
    },
    "monitoring": {
        "announcement_lookback_days": 1,
        "review_window_days": 5,
        "sell_fly_threshold_pct": 8.0,
        "escape_top_threshold_pct": 8.0,
    },
    "notifications": {
        "include_watchlist_snapshot": True,
        "include_plan_reference_in_morning_brief": False,
        "include_evolution_reminders_in_morning_brief": True,
    },
    "vault": {
        "enabled": True,
        "relative_path": "obsidian-vault",
        "auto_export_after_plan": True,
        "auto_export_after_trade": True,
        "auto_export_after_review": True,
        "auto_export_after_health_report": True,
    },
    "tushare": {
        "enabled": True,
        "token_env_keys": ["TUSHARE_TOKEN", "TS_TOKEN"],
        "announcement_endpoint": "anns_d",
        "news_endpoint": "news",
        "macro_endpoint": "major_news",
    },
    "url_sources": {
        "enabled": False,
        "timeout_seconds": 20,
        "user_agent": "Mozilla/5.0 (FinanceJournalBot)",
        "adapters": [],
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_runtime_config(repo_root: Path, skill_root: Path, runtime_root: str | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    example_path = skill_root / "config" / "runtime.example.json"
    local_path = skill_root / "config" / "runtime.local.json"
    for path in (example_path, local_path):
        config = _deep_merge(config, _load_json_if_exists(path))

    resolved_root = runtime_root or str(config.get("default_root") or "").strip() or str(repo_root / "_runtime")
    runtime_dir = Path(resolved_root).expanduser().resolve()

    config["default_root"] = str(runtime_dir)
    config["runtime_root"] = runtime_dir
    config["data_dir"] = runtime_dir / "data"
    config["artifacts_dir"] = runtime_dir / "artifacts"
    config["memory_dir"] = runtime_dir / "memory"
    config["status_dir"] = runtime_dir / "status"
    vault_value = str(config.get("vault", {}).get("relative_path") or "obsidian-vault")
    vault_path = Path(vault_value)
    if not vault_path.is_absolute():
        vault_path = runtime_dir / vault_path
    config["vault_root"] = vault_path.resolve()

    db_value = str(config.get("database", {}).get("relative_path") or "data/finance_journal.db")
    db_path = Path(db_value)
    if not db_path.is_absolute():
        db_path = runtime_dir / db_path
    config["db_path"] = db_path.resolve()
    return config
