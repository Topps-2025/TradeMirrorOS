# Data Contracts

统一要求：先写结构化数据，再写人类可读总结。

## Runtime Layout

- `data/finance_journal.db`: 本地 SQLite 主库
- `artifacts/daily/YYYYMMDD/`: 晨报、参考、回顾、体检等日级产物
- `memory/`: 预留给长期手工总结或后续规则演化
- `status/`: 调度状态与运行记录
- `obsidian-vault/`: 面向展示和长期复盘的 Markdown 知识库

## Core Tables

### `watchlist`

Required keys:
- `ts_code`
- `name`
- `is_active`
- `created_at`
- `updated_at`

### `keywords`

Required keys:
- `keyword`
- `category`
- `enabled`
- `created_at`
- `updated_at`

### `plans`

Required keys:
- `plan_id`
- `ts_code`
- `direction`
- `thesis`
- `logic_tags_json`
- `valid_from`
- `valid_to`
- `status`
- `created_at`
- `updated_at`

Common optional keys:
- `market_stage_tag`
- `environment_tags_json`
- `buy_zone`
- `sell_zone`
- `stop_loss`
- `holding_period`
- `linked_trade_id`
- `abandon_reason`
- `decision_context_json`

`decision_context_json` current base shape:
- `user_focus`: `list[str]`
- `observed_signals`: `list[str]`
- `interpretation`: `str`
- `position_reason`: `str`
- `position_confidence`: `float`
- `stress_level`: `int | float`

Common extended keys:
- `position_size_pct`: `float`
- `emotion_notes`: `str`
- `mistake_tags`: `list[str]`
- `environment_tags`: `list[str]`
- `market_stage`: `str`
- `risk_boundary`: `str`
- `planned_zone`: `{"buy_zone": str, "sell_zone": str}`
- `source_notes`: `str`
- `primary_symbol`: `{"ts_code": str, "name": str}`

Optional nested `strategy_context` for quant / semi-quant journaling:
- `strategy_id`: `str`
- `strategy_name`: `str`
- `strategy_family`: `str`
- `strategy_line`: `str`
- `factor_list`: `list[str]`
- `factor_selection_reason`: `str`
- `activation_reason`: `str`
- `parameter_version`: `str`
- `portfolio_role`: `str`
- `subjective_override`: `str`

### `trades`

Required keys:
- `trade_id`
- `ts_code`
- `buy_date`
- `buy_price`
- `status`
- `created_at`
- `updated_at`

Common optional keys:
- `plan_id`
- `sell_date`
- `sell_price`
- `actual_return_pct`
- `benchmark_return_pct`
- `timing_alpha_pct`
- `holding_days`
- `logic_type_tags_json`
- `pattern_tags_json`
- `market_stage_tag`
- `environment_tags_json`
- `snapshot_id`
- `plan_execution_deviation_json`
- `decision_context_json`
- `emotion_notes`
- `mistake_tags_json`
- `lessons_learned`

### `market_snapshots`

Required keys:
- `snapshot_id`
- `trade_date`
- `created_at`

Common optional keys:
- `sh_change_pct`
- `cyb_change_pct`
- `up_down_ratio`
- `limit_up_count`
- `limit_down_count`
- `sector_name`
- `sector_change_pct`
- `raw_payload_json`

### `info_events`

Required keys:
- `event_id`
- `event_type`
- `priority`
- `headline`
- `created_at`

Common optional keys:
- `ts_code`
- `name`
- `summary`
- `source`
- `published_at`
- `trade_date`
- `tags_json`
- `url`
- `raw_payload_json`

### `reviews`

Required keys:
- `review_id`
- `trade_id`
- `ts_code`
- `sell_date`
- `review_due_date`
- `review_window_days`
- `sell_price`
- `status`
- `created_at`
- `updated_at`

Common optional keys:
- `highest_price`
- `lowest_price`
- `max_gain_pct`
- `max_drawdown_pct`
- `review_type`
- `triggered_flag`
- `feedback`
- `weight_action`
- `prompt_text`

### `health_reports`

Required keys:
- `report_id`
- `period_kind`
- `period_start`
- `period_end`
- `report_markdown`
- `report_json`
- `created_at`

### `schedule_runs`

Required keys:
- `slot_key`
- `last_run_at`

Common optional keys:
- `artifact_path`
- `notes`

## Intake / Session Payloads

### `standardized_record`

Expected keys:
- `summary`
- `index_fields`
- `soft_structure_note`

Common optional keys:
- `user_focus`
- `observed_signals`
- `position_reason`
- `position_confidence`
- `stress_level`

### `polling_bundle`

Expected keys:
- `next_field`
- `next_question`
- `missing_field_queue`
- `reply_strategy`
- `completion_progress`

Common optional keys:
- `reflection_queue`
- `decision_axes`
- `next_axis`
- `shared_context_hints`
- `parallel_question_groups`

`shared_context_hints` is used to tell OpenClaw which answers can be reused across:
- `trade_date`: same-day market environment
- `symbol`: same symbol / same thesis / intraday T reuse
- `strategy`: same strategy line / factor set / parameter version

`parallel_question_groups` is used to tell OpenClaw which related questions can be merged into one reply:
- `fact_block`
- `market_context_block`
- `symbol_context_block`
- `strategy_context_block`

### `session turn`

Expected response keys:
- `assistant_message`
- `session_state`
- `mode`
- `action`

Common optional keys:
- `draft`
- `record`
- `polling_bundle`
- `reflection_prompts`

`session_state.pending_question` may come from:
- an active draft
- a recently imported statement record that still needs thesis / trigger / position follow-up

### `trade import-statement`

Expected response keys:
- `route`
- `statement_path`
- `summary`
- `items`

Common optional keys:
- `assistant_message`
- `pending_question`
- `follow_up_queue`
- `session_state`

`follow_up_queue` is used to expose a "facts first, reasons later" workflow:
- statement facts are aligned first
- subjective reasons are polled later through `pending_question`
- when only one trade is focused, `session_state.pending_question` should usually mirror the same next question

## Artifact Types

### `morning_brief.json/.md`

Required keys:
- `trade_date`
- `high_priority_events`
- `normal_priority_events`
- `active_plans`
- `pending_reviews`

Common optional keys:
- `source_summary`
- `evolution_reminders`

### `plan_reference_*.json/.md`

Required keys:
- `query`
- `lookback_days`
- `sample_size`
- `insufficient_sample`
- `matched_trades`
- `narrative`

### `review_cycle.json`

Required keys:
- `as_of_date`
- `created_reviews`
- `skipped`

### `health_report_*.json/.md`

Required keys:
- `period_start`
- `period_end`
- `trade_count`
- `plan_count`
- `metrics`
