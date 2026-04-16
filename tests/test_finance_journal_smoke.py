from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finance_journal_core.app import FinanceJournalApp
from finance_journal_core.storage import FinanceJournalDB, now_ts
from finance_journal_core.gateway import dispatch


class FinanceJournalSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temp_dir.name) / "runtime"
        self.repo_root = Path(__file__).resolve().parents[1]
        self.skill_root = self.repo_root / "finance-journal-orchestrator"
        self.app = FinanceJournalApp(
            repo_root=self.repo_root,
            skill_root=self.skill_root,
            runtime_root=str(self.runtime_root),
            enable_market_data=False,
        )
        self.app.init_runtime()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_core_trade_memory_flow(self) -> None:
        plan_result = self.app.create_plan(
            ts_code="603083",
            name="剑桥科技",
            direction="buy",
            thesis="回踩 5 日线参与",
            logic_tags=["龙头首阴", "低吸"],
            market_stage="震荡市",
            environment_tags=["修复回流", "CPO"],
            buy_zone="42.5-43.0",
            stop_loss="40.0",
            valid_from="20260410",
            valid_to="20260415",
            decision_context={
                "user_focus": ["剑桥科技", "CPO"],
                "observed_signals": ["回踩 5 日线", "板块修复"],
                "position_reason": "试错仓先参与",
                "strategy_context": {
                    "strategy_line": "cpo_repair_pullback",
                    "strategy_family": "semi_systematic",
                },
            },
            with_reference=True,
        )
        plan_id = plan_result["plan"]["plan_id"]
        self.assertTrue(plan_result["plan"]["memory_cell"]["memory_id"].startswith("memory_plan_"))

        trade = self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            plan_id=plan_id,
            buy_date="20260410",
            buy_price=43.2,
            thesis="回踩 5 日线参与",
            logic_type_tags=["龙头首阴", "低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流", "CPO"],
            emotion_notes="盘中有点急。",
            mistake_tags=["冲动"],
            notes="第一次试错单。",
            decision_context={
                "user_focus": ["剑桥科技"],
                "observed_signals": ["分时止跌"],
                "position_reason": "先拿一笔验证修复",
                "strategy_context": {"strategy_line": "cpo_repair_pullback"},
            },
        )
        trade_id = trade["trade_id"]
        self.assertTrue(trade["memory_cell"]["memory_id"].startswith("memory_trade_"))
        self.assertTrue(Path(trade["vault_note"]["path"]).exists())

        enriched = self.app.enrich_trade_from_text(
            trade_id,
            "补充：更像高位分歧后的修复回流，经验：下次先等量能回暖确认。",
            trade_date="20260410",
        )
        self.assertTrue(enriched["memory_cell"]["memory_id"].startswith("memory_trade_"))

        closed = self.app.close_trade(
            trade_id,
            sell_date="20260415",
            sell_price=46.8,
            sell_reason="达到预设止盈",
            lessons_learned="更适合分批卖出。",
        )
        self.assertEqual(closed["status"], "closed")
        self.assertTrue(closed["memory_cell"]["memory_id"].startswith("memory_trade_"))

        memory_query = self.app.query_memory(
            ts_code="603083",
            market_stage="震荡市",
            tags=["龙头首阴", "低吸", "修复回流"],
            limit=5,
        )
        self.assertTrue(memory_query["matched_cells"])

        reminder = self.app.generate_evolution_reminder(
            logic_tags=["龙头首阴", "低吸"],
            pattern_tags=["均线回踩"],
            market_stage="震荡市",
            environment_tags=["修复回流"],
            trade_date="20260415",
            write_artifact=False,
        )
        self.assertIn("memory_candidates", reminder)
        self.assertIn("linked_skill_cards", reminder)

        skillize = self.app.skillize_memory(trade_date="20260415", lookback_days=365, min_samples=1)
        self.assertTrue(skillize["created_skills"])
        self.assertTrue(skillize["created_skills"][0]["skill_id"].startswith("skill_"))

        sync_result = self.app.sync_vault(trade_date="20260415", limit=20)
        self.assertTrue(sync_result["enabled"])
        self.assertTrue(any("06-memory" in path or "07-skills" in path for path in sync_result["paths"]))

    def test_session_turn_returns_memory_context(self) -> None:
        self.app.log_trade(
            ts_code="600519",
            name="贵州茅台",
            buy_date="20260410",
            buy_price=1350,
            thesis="高股息修复低吸",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["高股息", "防守"],
            decision_context={"strategy_context": {"strategy_line": "dividend_repair"}},
        )

        first = self.app.handle_session_turn(
            "qq:user_a",
            "今天买了600519，1360买的，逻辑还是高股息修复低吸。",
            trade_date="20260411",
        )
        self.assertEqual(first["route"], "applied_from_session")
        self.assertIn("memory_retrieval", first)
        self.assertIn("memory_checklist", first)

        second = self.app.handle_session_turn(
            "qq:user_a",
            "补充：这次还是想按防守仓处理，别追求重仓。",
            trade_date="20260411",
        )
        self.assertEqual(second["route"], "entity_enriched")
        self.assertIn("memory_retrieval", second)

    def test_draft_polling_bundle_includes_guided_template(self) -> None:
        draft_turn = self.app.handle_session_turn(
            "qq:user_draft",
            "\u4eca\u5929\u4e70\u4e86600519",
            trade_date="20260411",
        )
        self.assertEqual(draft_turn["route"], "draft_started")
        draft = draft_turn["draft"]
        guided_prompt = ((draft.get("polling_bundle") or {}).get("guided_prompt") or {})
        self.assertTrue(guided_prompt.get("sections"))
        self.assertTrue(guided_prompt.get("reply_template"))
        self.assertTrue((draft.get("polling_bundle") or {}).get("self_checklist"))

    def test_session_apply_returns_daily_self_check(self) -> None:
        self.app.handle_session_turn(
            "qq:user_self_check",
            "\u4eca\u5929\u4e70\u4e86600519\uff0c\u903b\u8f91\u662f\u9ad8\u80a1\u606f\u4fee\u590d\u4f4e\u5438",
            trade_date="20260411",
        )
        payload = self.app.handle_session_turn(
            "qq:user_self_check",
            "1360",
            trade_date="20260411",
        )
        self.assertEqual(payload["route"], "draft_applied")
        daily_self_check = ((payload.get("draft") or {}).get("result") or {}).get("daily_self_check") or {}
        self.assertEqual(daily_self_check.get("trade_date"), "20260411")
        self.assertEqual(daily_self_check.get("status"), "needs_follow_up")
        self.assertGreaterEqual(((daily_self_check.get("summary") or {}).get("incomplete_trades") or 0), 1)
        self.assertTrue(daily_self_check.get("top_missing_fields"))
        self.assertIn("\u81ea\u68c0", payload.get("assistant_message") or "")


    def test_statement_import_and_memory_rebuild(self) -> None:
        statement_path = self.runtime_root / "statement_rows.csv"
        statement_path.write_text(
            "证券代码,证券名称,成交日期,成交时间,买卖标志,成交价格,成交数量,成交金额,手续费,成交编号\n"
            "603083,剑桥科技,20260410,09:35:00,买入,43.20,100,4320.00,2.10,deal_1\n",
            encoding="utf-8",
        )

        result = self.app.import_statement_file(str(statement_path), trade_date="20260410", session_key="qq:user_a")
        self.assertEqual(result["route"], "statement_import")
        self.assertTrue(result["items"])
        trade_id = result["items"][0]["trade_id"]
        self.assertTrue(trade_id)

        rebuilt = self.app.rebuild_memory()
        self.assertGreaterEqual(rebuilt["rebuild_count"], 1)

        memory_query = self.app.query_memory(ts_code="603083", limit=5)
        self.assertTrue(memory_query["matched_cells"])

    def test_statement_txt_import_aggregates_same_side_rows(self) -> None:
        statement_path = self.runtime_root / "statement_rows.txt"
        statement_path.write_text(
            "-------------------------------------------------------------------------------------------------------\n\n"
            "trade_date        trade_time        account          ts_code        name        side        trade_price        quantity        amount        occurred_amount         commission         stamp_duty        transfer_fee        other_fee        statement_id\n"
            "20260410        09:30:00        A000000001        600000          PFYH        buy            10.000          100             1000.00         -1005.00         5.00         0.00          0.00          0.00          deal_1\n"
            "20260410        09:31:00        A000000001        600000          PFYH        buy            11.000          200             2200.00         -2205.00         5.00         0.00          0.00          0.00          deal_2\n"
            "20260411        10:00:00        A000000001        600000          PFYH        sell            12.000          100             1200.00         1194.00          5.00         1.00          0.00          0.00          deal_3\n"
            "20260411        10:05:00        A000000001        600000          PFYH        sell            12.500          200             2500.00         2492.50          5.00         2.50          0.00          0.00          deal_4\n",
            encoding="gbk",
        )

        result = self.app.import_statement_file(str(statement_path), trade_date="20260411")
        self.assertEqual(result["summary"]["source_rows"], 4)
        self.assertEqual(result["summary"]["aggregated_rows"], 2)
        self.assertEqual(result["summary"]["imported_new"], 1)
        self.assertEqual(result["summary"]["closed_existing"], 1)

        trades = self.app.db.fetchall("SELECT * FROM trades WHERE ts_code = ? ORDER BY buy_date ASC", ("600000.SH",))
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["status"], "closed")
        self.assertAlmostEqual(float(trade["buy_price"]), 3200.0 / 300.0, places=6)
        self.assertAlmostEqual(float(trade["sell_price"]), 3700.0 / 300.0, places=6)

        trade_row = self.app.get_trade(trade["trade_id"])
        context = json.loads(trade_row["statement_context_json"] or "{}")
        self.assertEqual(context["buy_leg"]["aggregated_row_count"], 2)
        self.assertEqual(context["sell_leg"]["aggregated_row_count"], 2)
        self.assertAlmostEqual(float(context["buy_leg"]["quantity"]), 300.0, places=6)
        self.assertAlmostEqual(float(context["sell_leg"]["quantity"]), 300.0, places=6)
        self.assertEqual(len(context["buy_leg"]["statement_ids"]), 2)
        self.assertEqual(len(context["sell_leg"]["statement_ids"]), 2)

    def test_adopt_prior_holdings_copies_pre_range_positions(self) -> None:
        previous_db_path = self.runtime_root / "previous.db"
        previous_db = FinanceJournalDB(previous_db_path)
        previous_db.init_schema()
        timestamp = now_ts()
        previous_db.execute(
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
                "carry_src_1",
                "",
                "600000.SH",
                "PFYH",
                "long",
                "legacy holding",
                "20260228",
                10.5,
                "",
                "",
                "20260303",
                10.8,
                "",
                "",
                None,
                "[]",
                "[]",
                "",
                "",
                "[]",
                "",
                None,
                None,
                None,
                None,
                "{}",
                "{}",
                json.dumps(
                    {
                        "buy_leg": {"quantity": 300, "statement_id": "old_buy_1"},
                        "sell_leg": {"quantity": 300, "statement_id": "old_sell_1"},
                    },
                    ensure_ascii=False,
                ),
                "pending",
                "closed",
                "",
                "[]",
                "",
                "from old ledger",
                timestamp,
                timestamp,
            ),
        )
        previous_db.execute(
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
                "carry_src_2",
                "",
                "600001.SH",
                "TEST",
                "long",
                "legacy open",
                "20260220",
                8.2,
                "",
                "",
                "",
                None,
                "",
                "",
                None,
                "[]",
                "[]",
                "",
                "",
                "[]",
                "",
                None,
                None,
                None,
                None,
                "{}",
                "{}",
                json.dumps({"buy_leg": {"quantity": 500, "statement_id": "old_buy_2"}}, ensure_ascii=False),
                "pending",
                "open",
                "",
                "[]",
                "",
                "",
                timestamp,
                timestamp,
            ),
        )

        payload = self.app.adopt_prior_holdings(str(previous_db_path), visible_start_date="20260302")
        self.assertEqual(payload["summary"]["source_candidates"], 2)
        self.assertEqual(payload["summary"]["imported_prior_holding"], 2)

        trades = self.app.db.fetchall("SELECT * FROM trades ORDER BY buy_date ASC")
        self.assertEqual(len(trades), 2)
        first_context = json.loads(trades[0]["statement_context_json"] or "{}")
        self.assertTrue(first_context.get("carry_forward", {}).get("enabled"))
        self.assertEqual(first_context.get("carry_forward", {}).get("source_trade_id"), "carry_src_2")

        payload_again = self.app.adopt_prior_holdings(str(previous_db_path), visible_start_date="20260302")
        self.assertEqual(payload_again["summary"]["matched_existing"], 2)
        self.assertEqual(self.app.db.fetchall("SELECT * FROM trades"), trades)

    def test_schedule_uses_memory_compaction(self) -> None:
        self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            buy_date="20260410",
            buy_price=43.2,
            thesis="回踩参与",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流"],
        )
        dry_run = self.app.run_schedule(now="2026-04-10T08:31", dry_run=True)
        kinds = {item["kind"] for item in dry_run["actions"]}
        self.assertIn("memory_compaction", kinds)
        self.assertNotIn("event_fetch", kinds)
        self.assertNotIn("morning_brief", kinds)

    def test_gateway_routes_memory_commands(self) -> None:
        self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            buy_date="20260410",
            buy_price=43.2,
            thesis="回踩参与",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流"],
        )
        payload = dispatch(
            "记忆 查询 ts_code=603083 market_stage=震荡市 tags=低吸,均线回踩",
            anchor_path=self.skill_root / "scripts" / "finance_journal_gateway.py",
            runtime_root=str(self.runtime_root),
            enable_market_data=False,
        )
        self.assertIn("matched_cells", payload)
        self.assertTrue(payload["matched_cells"])


if __name__ == "__main__":
    unittest.main()
