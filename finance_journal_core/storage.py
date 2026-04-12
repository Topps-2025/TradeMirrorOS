from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watchlist (
    ts_code TEXT PRIMARY KEY,
    name TEXT,
    notes TEXT,
    source TEXT DEFAULT 'manual',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keywords (
    keyword TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT 'industry',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    ts_code TEXT NOT NULL,
    name TEXT,
    direction TEXT NOT NULL,
    thesis TEXT NOT NULL,
    logic_tags_json TEXT NOT NULL DEFAULT '[]',
    market_stage_tag TEXT,
    environment_tags_json TEXT NOT NULL DEFAULT '[]',
    buy_zone TEXT,
    sell_zone TEXT,
    stop_loss TEXT,
    holding_period TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    reminder_time TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    linked_trade_id TEXT,
    abandon_reason TEXT,
    decision_context_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_status_dates ON plans(status, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_plans_code ON plans(ts_code);

CREATE TABLE IF NOT EXISTS market_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    ts_code TEXT,
    name TEXT,
    sh_change_pct REAL,
    cyb_change_pct REAL,
    up_down_ratio REAL,
    limit_up_count INTEGER,
    limit_down_count INTEGER,
    sector_name TEXT,
    sector_change_pct REAL,
    sector_strength_tag TEXT,
    raw_payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_trade_date ON market_snapshots(trade_date);

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    plan_id TEXT,
    ts_code TEXT NOT NULL,
    name TEXT,
    direction TEXT NOT NULL DEFAULT 'long',
    thesis TEXT,
    buy_date TEXT NOT NULL,
    buy_price REAL NOT NULL,
    buy_reason TEXT,
    buy_position TEXT,
    sell_date TEXT,
    sell_price REAL,
    sell_reason TEXT,
    sell_position TEXT,
    position_size_pct REAL,
    logic_type_tags_json TEXT NOT NULL DEFAULT '[]',
    pattern_tags_json TEXT NOT NULL DEFAULT '[]',
    theme TEXT,
    market_stage_tag TEXT,
    environment_tags_json TEXT NOT NULL DEFAULT '[]',
    snapshot_id TEXT,
    benchmark_return_pct REAL,
    actual_return_pct REAL,
    timing_alpha_pct REAL,
    holding_days INTEGER,
    plan_execution_deviation_json TEXT,
    decision_context_json TEXT NOT NULL DEFAULT '{}',
    review_status TEXT NOT NULL DEFAULT 'pending',
    status TEXT NOT NULL DEFAULT 'open',
    emotion_notes TEXT,
    mistake_tags_json TEXT NOT NULL DEFAULT '[]',
    lessons_learned TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_dates ON trades(buy_date, sell_date);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_code ON trades(ts_code);

CREATE TABLE IF NOT EXISTS info_events (
    event_id TEXT PRIMARY KEY,
    ts_code TEXT,
    name TEXT,
    event_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    source TEXT,
    url TEXT,
    published_at TEXT,
    trade_date TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    raw_payload_json TEXT,
    pushed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_info_events_trade_date ON info_events(trade_date, priority);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL,
    ts_code TEXT NOT NULL,
    name TEXT,
    sell_date TEXT NOT NULL,
    review_due_date TEXT NOT NULL,
    review_window_days INTEGER NOT NULL,
    sell_price REAL NOT NULL,
    highest_price REAL,
    lowest_price REAL,
    max_gain_pct REAL,
    max_drawdown_pct REAL,
    review_type TEXT,
    triggered_flag INTEGER NOT NULL DEFAULT 0,
    feedback TEXT,
    weight_action TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    prompt_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_due_date ON reviews(review_due_date, status);
CREATE INDEX IF NOT EXISTS idx_reviews_trade ON reviews(trade_id);

CREATE TABLE IF NOT EXISTS health_reports (
    report_id TEXT PRIMARY KEY,
    period_kind TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    report_markdown TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_reports_period ON health_reports(period_kind, period_start, period_end);

CREATE TABLE IF NOT EXISTS journal_drafts (
    draft_id TEXT PRIMARY KEY,
    session_key TEXT,
    mode TEXT NOT NULL,
    journal_kind TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source_text TEXT,
    latest_input_text TEXT,
    raw_inputs_json TEXT NOT NULL DEFAULT '[]',
    fields_json TEXT NOT NULL,
    missing_fields_json TEXT NOT NULL,
    follow_up_questions_json TEXT NOT NULL,
    next_field TEXT,
    last_question TEXT,
    applied_entity_kind TEXT,
    applied_entity_id TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_journal_drafts_status ON journal_drafts(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_journal_drafts_session ON journal_drafts(session_key, status, updated_at);

CREATE TABLE IF NOT EXISTS session_threads (
    session_key TEXT PRIMARY KEY,
    active_draft_id TEXT,
    active_entity_kind TEXT,
    active_entity_id TEXT,
    active_mode TEXT,
    trade_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    memory_json TEXT NOT NULL DEFAULT '{}',
    last_user_text TEXT,
    last_assistant_text TEXT,
    last_route TEXT,
    last_result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_threads_status ON session_threads(status, updated_at);

CREATE TABLE IF NOT EXISTS schedule_runs (
    slot_key TEXT PRIMARY KEY,
    last_run_at TEXT NOT NULL,
    artifact_path TEXT,
    notes TEXT
);
"""


MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "plans": {
        "decision_context_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "trades": {
        "emotion_notes": "TEXT",
        "mistake_tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "lessons_learned": "TEXT",
        "decision_context_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "journal_drafts": {
        "session_key": "TEXT",
    },
    "info_events": {
        "url": "TEXT",
        "raw_payload_json": "TEXT",
    },
}


def now_ts() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def safe_filename(text: str, max_len: int = 96) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\[\]]', '_', str(text)).strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    cleaned = cleaned.strip('._')
    return (cleaned[:max_len] or 'artifact').strip('._')


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows if row is not None]


def ensure_runtime_dirs(config: dict[str, Any]) -> None:
    for key in ('runtime_root', 'data_dir', 'artifacts_dir', 'memory_dir', 'status_dir'):
        Path(config[key]).mkdir(parents=True, exist_ok=True)


class FinanceJournalDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            for table_name, columns in MIGRATION_COLUMNS.items():
                existing_columns = {
                    row["name"]
                    for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                }
                for column_name, column_type in columns.items():
                    if column_name in existing_columns:
                        continue
                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return rows_to_dicts(rows)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row_to_dict(row)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as conn:
            conn.execute(sql, params)
