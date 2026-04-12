from __future__ import annotations

import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from finance_journal_core.app import FinanceJournalApp
from finance_journal_core.gateway import dispatch
from finance_journal_core.url_sources import UrlEventFetcher, _load_json_loose


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

    def test_local_journal_flow_without_market_data(self) -> None:
        watch = self.app.add_watchlist("600519", name="贵州茅台")
        self.assertEqual(watch["ts_code"], "600519.SH")
        self.app.add_watchlist("603083", name="剑桥科技")

        keyword = self.app.add_keyword("CPO")
        self.assertEqual(keyword["keyword"], "CPO")

        trade_draft = self.app.parse_journal_text(
            "今天低吸了603083，43.2买的，想博弈CPO回流，盘中有点急，感觉还是拿不稳。",
            mode="trade",
            trade_date="20260410",
        )
        self.assertEqual(trade_draft["fields"]["ts_code"], "603083.SH")
        self.assertEqual(trade_draft["fields"]["buy_price"], 43.2)
        self.assertIn("低吸", trade_draft["fields"]["logic_tags"])
        self.assertIn("拿不稳", trade_draft["fields"]["mistake_tags"])

        plan_apply = self.app.apply_journal_text(
            "计划在42.5-43.0低吸603083，止损40，看CPO回流。",
            mode="plan",
            trade_date="20260410",
        )
        self.assertTrue(plan_apply["applied"])
        auto_plan_id = plan_apply["result"]["plan"]["plan_id"]
        self.assertTrue(Path(plan_apply["result"]["vault_note"]["path"]).exists())

        plan_result = self.app.create_plan(
            ts_code="603083",
            name="剑桥科技",
            direction="buy",
            thesis="回踩 5 日线参与",
            logic_tags=["龙头首阴", "低吸"],
            market_stage="震荡市",
            environment_tags=["高位分歧", "CPO"],
            buy_zone="42.5-43.0",
            stop_loss="40.0",
            holding_period="3-5天",
            valid_from="20260410",
            valid_to="20260415",
        )
        plan_id = plan_result["plan"]["plan_id"]
        self.assertTrue(Path(plan_result["vault_note"]["path"]).exists())
        self.assertNotEqual(auto_plan_id, plan_id)
        self.assertIn("evolution_reminder", plan_result)

        trade = self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            plan_id=plan_id,
            buy_date="20260410",
            buy_price=43.2,
            thesis="回踩 5 日线参与",
            sell_date="20260415",
            sell_price=46.8,
            sell_reason="达到预设止盈",
            logic_type_tags=["龙头首阴", "题材驱动"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["高位分歧", "CPO"],
            emotion_notes="盘中略有急躁，但没有追高。",
            mistake_tags=["拿不稳"],
            lessons_learned="更适合按计划分批止盈。",
        )
        self.assertEqual(trade["status"], "closed")
        self.assertEqual(trade["plan_id"], plan_id)
        self.assertTrue(Path(trade["vault_note"]["path"]).exists())
        self.assertTrue(Path(trade["daily_vault_note"]["path"]).exists())

        event = self.app.add_info_event(
            event_type="announcement",
            headline="剑桥科技发布公告：签订新订单",
            summary="新增算力光模块订单",
            ts_code="603083",
            name="剑桥科技",
            priority="high",
            trade_date="20260411",
        )
        self.assertEqual(event["event_type"], "announcement")

        brief = self.app.generate_morning_brief(trade_date="20260411", fetch_events=False)
        self.assertTrue(Path(brief["artifact_paths"]["markdown"]).exists())

        reference = self.app.generate_reference(
            logic_tags=["龙头首阴"],
            market_stage="震荡市",
            environment_tags=["高位分歧"],
            lookback_days=365,
            trade_date="20260415",
            write_artifact=False,
        )
        self.assertEqual(reference["sample_size"], 1)

        report = self.app.generate_health_report("20260401", "20260430", period_kind="monthly")
        self.assertEqual(report["trade_count"], 1)
        self.assertTrue(Path(report["artifact_paths"]["markdown"]).exists())
        self.assertTrue(Path(report["vault_note"]["path"]).exists())

        sync_result = self.app.sync_vault(trade_date="20260415", limit=20)
        self.assertTrue(sync_result["enabled"])
        self.assertTrue(any(Path(path).exists() for path in sync_result["paths"]))

    def test_morning_brief_can_dedupe_and_group_events(self) -> None:
        self.app.add_info_event(
            event_type="macro",
            headline="美股三大指数期货小幅走高",
            source="cls",
            priority="high",
            trade_date="20260411",
        )
        self.app.add_info_event(
            event_type="macro",
            headline="美股三大指数期货小幅走高",
            source="jin10",
            priority="normal",
            trade_date="20260411",
        )
        self.app.add_info_event(
            event_type="macro",
            headline="离岸人民币短线反弹",
            source="wallstreetcn",
            priority="normal",
            trade_date="20260411",
        )

        brief = self.app.generate_morning_brief(trade_date="20260411", fetch_events=False)
        self.assertEqual(len(brief["deduped_events"]), 2)
        self.assertEqual(len(brief["cross_source_events"]), 1)
        self.assertTrue(brief["source_groups"])
        self.assertIn("按来源分组", Path(brief["artifact_paths"]["markdown"]).read_text(encoding="utf-8"))

    def test_intake_parser_keeps_code_out_of_dates_and_prices(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")

        trade_draft = self.app.parse_journal_text(
            "今天低吸了603083，43.2买的，想博弈CPO回流，盘中有点急，感觉还是拿不稳。",
            mode="trade",
            trade_date="20260410",
        )
        self.assertEqual(trade_draft["fields"]["ts_code"], "603083.SH")
        self.assertEqual(trade_draft["fields"]["name"], "剑桥科技")
        self.assertEqual(trade_draft["fields"]["buy_date"], "20260410")
        self.assertEqual(trade_draft["fields"]["sell_date"], "")
        self.assertEqual(trade_draft["fields"]["buy_price"], 43.2)
        self.assertIsNone(trade_draft["fields"]["sell_price"])
        self.assertEqual(trade_draft["standardized_record"]["index_fields"]["ts_code"], "603083.SH")
        self.assertEqual(trade_draft["polling_bundle"]["completion_progress"]["required_missing"], 0)
        self.assertTrue(trade_draft["polling_bundle"]["reply_strategy"])
        self.assertEqual(trade_draft["polling_bundle"]["next_axis"], "timing")
        self.assertTrue(trade_draft["polling_bundle"]["reflection_queue"])
        self.assertTrue(trade_draft["polling_bundle"]["shared_context_hints"])
        self.assertTrue(trade_draft["polling_bundle"]["parallel_question_groups"])

        plan_draft = self.app.parse_journal_text(
            "计划在42.5-43.0低吸603083，止损40，看CPO回流。",
            mode="plan",
            trade_date="20260410",
        )
        self.assertEqual(plan_draft["fields"]["ts_code"], "603083.SH")
        self.assertEqual(plan_draft["fields"]["buy_date"], "20260410")
        self.assertEqual(plan_draft["fields"]["buy_zone"], "42.5-43.0")
        self.assertEqual(plan_draft["fields"]["sell_zone"], "")
        self.assertEqual(plan_draft["fields"]["stop_loss"], "40.0")
        self.assertIsNone(plan_draft["fields"]["buy_price"])
        self.assertIsNone(plan_draft["fields"]["sell_price"])

    def test_intake_parser_builds_user_view_snapshot_fields(self) -> None:
        self.app.add_watchlist("600519", name="贵州茅台")

        draft = self.app.parse_journal_text(
            "感觉贵州茅台跌到这个位置股息率很有吸引力，消费板块也企稳了，想做个低吸，先上2成试错仓。",
            mode="trade",
            trade_date="20260410",
        )
        self.assertEqual(draft["fields"]["ts_code"], "600519.SH")
        self.assertIn("贵州茅台", draft["fields"]["user_focus"])
        self.assertTrue(any("消费板块" in item for item in draft["fields"]["user_focus"]))
        self.assertTrue(any("企稳" in item or "股息率" in item for item in draft["fields"]["observed_signals"]))
        self.assertTrue(draft["fields"]["position_reason"])
        self.assertEqual(draft["polling_bundle"]["decision_axes"][0]["axis"], "selection")
        self.assertIn("next_axis", draft["polling_bundle"])

    def test_journal_draft_state_machine_can_poll_and_apply(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")

        draft = self.app.start_journal_draft("今天买了603083", mode="trade", trade_date="20260410", session_key="qq:user_a")
        other = self.app.start_journal_draft("计划低吸600519", mode="plan", trade_date="20260410", session_key="qq:user_b")
        self.assertEqual(draft["status"], "active")
        self.assertEqual(draft["fields"]["ts_code"], "603083.SH")
        self.assertIn("buy_price", draft["missing_fields"])
        self.assertIn("thesis", draft["missing_fields"])
        self.assertTrue(draft["next_question"])
        self.assertEqual(draft["polling_bundle"]["next_field"], "buy_price")
        self.assertEqual(draft["polling_bundle"]["completion_progress"]["required_missing"], 2)
        self.assertTrue(draft["polling_bundle"]["missing_field_queue"])
        self.assertTrue(any(item["field"] == "buy_price" for item in draft["polling_bundle"]["missing_field_queue"]))
        self.assertTrue(draft["polling_bundle"]["reflection_queue"])
        self.assertTrue(any(item["scope"] == "trade_date" for item in draft["polling_bundle"]["shared_context_hints"]))
        self.assertTrue(any(item["scope"] == "symbol" for item in draft["polling_bundle"]["parallel_question_groups"]))

        current = self.app.get_journal_draft(session_key="qq:user_a")
        self.assertTrue(current["auto_selected_latest_active"])
        self.assertEqual(current["draft_id"], draft["draft_id"])
        self.assertNotEqual(other["draft_id"], draft["draft_id"])

        draft = self.app.continue_journal_draft(text="43.2", apply_if_ready=True, session_key="qq:user_a")
        self.assertTrue(draft["auto_selected_latest_active"])
        self.assertEqual(draft["status"], "active")
        self.assertEqual(draft["fields"]["buy_price"], 43.2)
        self.assertEqual(draft["fields"]["stop_loss"], "")
        self.assertIn("thesis", draft["missing_fields"])

        draft = self.app.continue_journal_draft(
            text="逻辑是CPO修复回流，想做低吸。",
            apply_if_ready=True,
            session_key="qq:user_a",
        )
        self.assertEqual(draft["status"], "applied")
        self.assertEqual(draft["applied_entity_kind"], "trade")
        self.assertTrue(draft["applied_entity_id"])

        trade = self.app.get_trade(draft["applied_entity_id"])
        self.assertIsNotNone(trade)
        self.assertEqual(trade["buy_price"], 43.2)
        self.assertIn("CPO", trade["thesis"])
        self.assertIn("低吸", trade["notes"])

    def test_trade_persists_decision_context_and_exports_to_vault(self) -> None:
        trade = self.app.log_trade(
            ts_code="600519",
            name="贵州茅台",
            buy_date="20260410",
            buy_price=1350.0,
            thesis="股息率和板块修复共振，先做试错低吸。",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["消费板块", "修复回流"],
            position_size_pct=20,
            decision_context={
                "user_focus": ["贵州茅台", "消费板块", "股息率"],
                "observed_signals": ["消费板块企稳", "股息率回到有吸引力区间"],
                "interpretation": "当前位置更像估值和板块同步修复的低吸窗口。",
                "position_reason": "先上 2 成试错仓，确认板块持续性后再加。",
                "position_confidence": 7,
                "stress_level": 3,
                "strategy_context": {
                    "strategy_line": "高股息修复低吸",
                    "strategy_family": "半量化择时",
                    "factor_list": ["股息率", "板块修复", "估值回归"],
                    "factor_selection_reason": "当前更想验证高股息 + 板块修复的共振窗口。",
                    "activation_reason": "消费板块有企稳迹象，允许策略恢复试仓。",
                    "parameter_version": "dividend_repair_v2",
                    "portfolio_role": "低波防守仓",
                    "subjective_override": "公告前只开观察仓，不直接满配。",
                },
            },
        )
        stored = self.app.get_trade(trade["trade_id"])
        self.assertIsNotNone(stored)
        decision_context = json.loads(stored["decision_context_json"])
        self.assertIn("消费板块企稳", decision_context["observed_signals"])
        self.assertEqual(decision_context["strategy_context"]["parameter_version"], "dividend_repair_v2")
        note_text = Path(trade["vault_note"]["path"]).read_text(encoding="utf-8")
        self.assertIn("用户视角快照", note_text)
        self.assertIn("仓位理由", note_text)
        self.assertIn("策略条线", note_text)
        self.assertIn("dividend_repair_v2", note_text)

    def test_schedule_can_stage_event_fetch_slots(self) -> None:
        self.app.config["url_sources"]["enabled"] = True
        self.app.config["url_sources"]["adapters"] = [
            {
                "name": "demo-news",
                "enabled": True,
                "kind": "macro",
                "source": "demo",
                "url_template": "https://example.com/feed",
                "parser": {"mode": "html_list"},
            }
        ]
        self.app.config["schedules"]["event_fetch_times"] = ["07:55", "12:30"]
        self.app.config["schedules"]["fetch_events_before_morning_brief"] = True

        dry_run = self.app.run_schedule(now="2026-04-10T12:31", dry_run=True)
        slots = [item["slot"] for item in dry_run["actions"]]
        self.assertIn("event_fetch:20260410:0755", slots)
        self.assertIn("event_fetch:20260410:1230", slots)
        morning = next(item for item in dry_run["actions"] if item["kind"] == "morning_brief")
        self.assertTrue(morning["fetch_events"])

    def test_evolution_report_and_reminder_extract_paths(self) -> None:
        first_trade = self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            buy_date="20260401",
            buy_price=40.0,
            sell_date="20260403",
            sell_price=44.0,
            thesis="CPO修复回流低吸",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流"],
        )
        second_trade = self.app.log_trade(
            ts_code="600519",
            name="贵州茅台",
            buy_date="20260405",
            buy_price=1500.0,
            sell_date="20260409",
            sell_price=1560.0,
            thesis="震荡里均线回踩低吸",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流"],
        )
        self.app.log_trade(
            ts_code="000001",
            name="平安银行",
            buy_date="20260406",
            buy_price=12.0,
            sell_date="20260408",
            sell_price=11.0,
            thesis="追高失败",
            logic_type_tags=["半路追涨"],
            pattern_tags=["放量突破"],
            market_stage_tag="高位分歧",
            environment_tags=["高位分歧"],
            mistake_tags=["冲动追高"],
        )
        plan = self.app.create_plan(
            ts_code="603083",
            name="剑桥科技",
            direction="buy",
            thesis="回踩买入",
            logic_tags=["低吸"],
            buy_zone="42-43",
            stop_loss="40",
            valid_from="20260407",
            valid_to="20260410",
        )
        self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            plan_id=plan["plan"]["plan_id"],
            buy_date="20260407",
            buy_price=45.0,
            sell_date="20260410",
            sell_price=42.0,
            thesis="偏离计划去追",
            logic_type_tags=["半路追涨"],
            pattern_tags=["放量突破"],
            market_stage_tag="高位分歧",
            environment_tags=["高位分歧"],
            emotion_notes="有点急，追着买。",
            mistake_tags=["冲动追高"],
        )
        second_plan = self.app.create_plan(
            ts_code="600519",
            name="贵州茅台",
            direction="buy",
            thesis="低吸回踩",
            logic_tags=["低吸"],
            buy_zone="1490-1500",
            stop_loss="1470",
            valid_from="20260408",
            valid_to="20260410",
        )
        self.app.log_trade(
            ts_code="600519",
            name="贵州茅台",
            plan_id=second_plan["plan"]["plan_id"],
            buy_date="20260408",
            buy_price=1525.0,
            sell_date="20260410",
            sell_price=1498.0,
            thesis="偏离低吸区间硬上",
            logic_type_tags=["半路追涨"],
            pattern_tags=["放量突破"],
            market_stage_tag="高位分歧",
            environment_tags=["高位分歧"],
            emotion_notes="有点慌，怕错过。",
            mistake_tags=["冲动追高"],
        )
        with self.app.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews(
                    review_id, trade_id, ts_code, name, sell_date, review_due_date, review_window_days,
                    sell_price, highest_price, lowest_price, max_gain_pct, max_drawdown_pct,
                    review_type, triggered_flag, feedback, weight_action, status, prompt_text, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "review_manual_1",
                    first_trade["trade_id"],
                    first_trade["ts_code"],
                    first_trade["name"],
                    first_trade["sell_date"],
                    "20260408",
                    5,
                    first_trade["sell_price"],
                    48.0,
                    43.0,
                    9.09,
                    -2.27,
                    "sell_fly",
                    1,
                    "是，卖早了。",
                    "降低该卖出理由权重",
                    "answered",
                    "manual",
                    "2026-04-11T00:00:00+08:00",
                    "2026-04-11T00:00:00+08:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO reviews(
                    review_id, trade_id, ts_code, name, sell_date, review_due_date, review_window_days,
                    sell_price, highest_price, lowest_price, max_gain_pct, max_drawdown_pct,
                    review_type, triggered_flag, feedback, weight_action, status, prompt_text, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "review_manual_2",
                    second_trade["trade_id"],
                    second_trade["ts_code"],
                    second_trade["name"],
                    second_trade["sell_date"],
                    "20260414",
                    5,
                    second_trade["sell_price"],
                    1690.0,
                    1540.0,
                    8.33,
                    -1.28,
                    "sell_fly",
                    1,
                    "是，确认卖飞。",
                    "下调该卖点权重",
                    "answered",
                    "manual",
                    "2026-04-11T00:00:00+08:00",
                    "2026-04-11T00:00:00+08:00",
                ),
            )

        report = self.app.generate_evolution_report(lookback_days=30, trade_date="20260410", min_samples=2, write_artifact=False)
        self.assertGreaterEqual(report["sample_size"], 5)
        self.assertTrue(report["quality_paths"])
        self.assertTrue(any(item["gene_label"] == "低吸" for item in report["reusable_genes"]))
        self.assertTrue(any(item["gene_label"] == "买点偏离计划" for item in report["risk_genes"]))
        self.assertTrue(any(item["gene_label"] == "确认卖飞" for item in report["risk_genes"]))
        self.assertTrue(report["bandit_candidates"])
        self.assertEqual(report["policy_stack"]["recommended_mode"], "contextual_bandit")
        self.assertIn("Bandit 视角", report["markdown"])

        reminder = self.app.generate_evolution_reminder(
            logic_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage="震荡市",
            environment_tags=["修复回流"],
            lookback_days=30,
            trade_date="20260410",
            min_samples=2,
            write_artifact=False,
        )
        self.assertTrue(reminder["matched_quality_paths"])
        self.assertTrue(any("优质路径提醒" in item for item in reminder["reminders"]))
        self.assertTrue(reminder["habit_risk_genes"])
        self.assertTrue(reminder["pre_trade_checklist"])
        self.assertTrue(reminder["reflection_prompts"])
        self.assertEqual(reminder["adaptive_policy"]["recommended_mode"], "contextual_bandit")
        self.assertIn("只用于提醒", reminder["soft_structure_note"])
        self.assertTrue(all(item.get("question") for item in reminder["reflection_prompts"]))

    def test_plan_and_trade_enrich_can_accumulate_reflection(self) -> None:
        plan = self.app.create_plan(
            ts_code="603083",
            name="剑桥科技",
            direction="buy",
            thesis="先观察，不着急",
            valid_from="20260410",
            valid_to="20260412",
        )
        enriched_plan = self.app.enrich_plan_from_text(
            plan["plan"]["plan_id"],
            "补充：这是龙头首阴低吸，高位分歧里博弈CPO回流，止损40。",
            trade_date="20260410",
            lookback_days=30,
        )
        self.assertIn("thesis", enriched_plan["updated_fields"])
        self.assertIn("logic_tags", enriched_plan["updated_fields"])
        self.assertIn("environment_tags", enriched_plan["updated_fields"])
        self.assertIn("止损40", enriched_plan["plan"]["notes"])
        self.assertIn("低吸", json.loads(enriched_plan["plan"]["logic_tags_json"]))
        self.assertTrue(enriched_plan["reflection_prompts"])
        self.assertTrue(enriched_plan["polling_bundle"]["reflection_queue"])
        self.assertIn("只用于索引", enriched_plan["standardized_record"]["soft_structure_note"])
        self.assertIn("evolution_reminder", enriched_plan)

        trade = self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            buy_date="20260410",
            buy_price=43.2,
            thesis="先上车再说",
        )
        enriched_trade = self.app.enrich_trade_from_text(
            trade["trade_id"],
            "补充：其实更像高位分歧里的放量突破，当时有点急，属于冲动追高。经验：下次先等回踩确认。",
            trade_date="20260410",
            lookback_days=30,
        )
        self.assertIn("pattern_tags", enriched_trade["updated_fields"])
        self.assertIn("mistake_tags", enriched_trade["updated_fields"])
        self.assertIn("emotion_notes", enriched_trade["updated_fields"])
        self.assertIn("lessons_learned", enriched_trade["updated_fields"])
        self.assertIn("冲动追高", json.loads(enriched_trade["trade"]["mistake_tags_json"]))
        self.assertIn("有点急", enriched_trade["trade"]["emotion_notes"])
        self.assertIn("经验", enriched_trade["trade"]["lessons_learned"])
        self.assertTrue(enriched_trade["reflection_prompts"])
        self.assertTrue(enriched_trade["polling_bundle"]["reflection_queue"])
        self.assertIn("只用于索引", enriched_trade["standardized_record"]["soft_structure_note"])
        self.assertIn("evolution_reminder", enriched_trade)

    def test_style_portrait_can_summarize_personal_profile(self) -> None:
        self.app.log_trade(
            ts_code="603083",
            name="剑桥科技",
            buy_date="20260401",
            buy_price=40.0,
            sell_date="20260403",
            sell_price=44.0,
            thesis="CPO修复回流低吸",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流"],
        )
        self.app.log_trade(
            ts_code="600519",
            name="贵州茅台",
            buy_date="20260405",
            buy_price=1500.0,
            sell_date="20260409",
            sell_price=1560.0,
            thesis="震荡里均线回踩低吸",
            logic_type_tags=["低吸"],
            pattern_tags=["均线回踩"],
            market_stage_tag="震荡市",
            environment_tags=["修复回流"],
        )
        plan = self.app.create_plan(
            ts_code="000001",
            name="平安银行",
            direction="buy",
            thesis="回踩低吸",
            logic_tags=["低吸"],
            buy_zone="11.5-11.8",
            stop_loss="11.2",
            valid_from="20260406",
            valid_to="20260410",
        )
        self.app.log_trade(
            ts_code="000001",
            name="平安银行",
            plan_id=plan["plan"]["plan_id"],
            buy_date="20260406",
            buy_price=12.0,
            sell_date="20260408",
            sell_price=11.0,
            thesis="追高失败",
            logic_type_tags=["半路追涨"],
            pattern_tags=["放量突破"],
            market_stage_tag="高位分歧",
            environment_tags=["高位分歧"],
            emotion_notes="有点急，怕错过。",
            mistake_tags=["冲动追高"],
        )
        second_plan = self.app.create_plan(
            ts_code="000002",
            name="万科A",
            direction="buy",
            thesis="低吸等回流",
            logic_tags=["低吸"],
            buy_zone="9.8-10.0",
            stop_loss="9.6",
            valid_from="20260407",
            valid_to="20260410",
        )
        self.app.log_trade(
            ts_code="000002",
            name="万科A",
            plan_id=second_plan["plan"]["plan_id"],
            buy_date="20260407",
            buy_price=10.3,
            sell_date="20260410",
            sell_price=9.9,
            thesis="偏离计划硬上",
            logic_type_tags=["半路追涨"],
            pattern_tags=["放量突破"],
            market_stage_tag="高位分歧",
            environment_tags=["高位分歧"],
            emotion_notes="有点急，临盘怕错过。",
            mistake_tags=["冲动追高"],
        )

        portrait = self.app.generate_style_portrait(
            lookback_days=30,
            trade_date="20260410",
            min_samples=2,
            write_artifact=False,
        )
        self.assertGreaterEqual(portrait["sample_size"], 4)
        self.assertTrue(portrait["advantage_paths"])
        self.assertTrue(any(item["tag"] == "低吸" for item in portrait["advantage_tags"]))
        self.assertTrue(any(item["gene_label"] == "买点偏离计划" for item in portrait["risk_genes"]))
        self.assertTrue(portrait["emotion_profile"])
        self.assertTrue(portrait["reflection_prompts"])
        self.assertTrue(portrait["adaptive_policy_profile"]["top_exploit_arms"])
        self.assertTrue(portrait["evolution_report"]["bandit_candidates"])
        self.assertIn("不是策略代码", portrait["soft_structure_note"])
        self.assertIn("一句话画像", portrait["markdown"])

    def test_fetch_url_events_can_work_without_market_data(self) -> None:
        html = """
        <html>
          <body>
            <a href="/a1.html">剑桥科技公告：签订新订单</a>
            <a href="/a2.html">剑桥科技业绩预告：一季度增长</a>
          </body>
        </html>
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://example.com/list", "text/html")):
            result = self.app.fetch_url_events(
                url="https://example.com/list",
                event_type="announcement",
                source="demo-web",
                parser_mode="html_list",
                ts_code="603083",
                name="剑桥科技",
                trade_date="20260410",
                include_patterns="公告,业绩",
            )
        self.assertEqual(result["inserted"], 2)
        self.assertTrue(all(item["url"].startswith("https://example.com/") for item in result["events"]))
        self.assertTrue(all(item["raw_payload_json"] for item in result["events"]))

    def test_fetch_watchlist_events_can_use_url_adapters_without_tushare(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")
        self.app.config["url_sources"] = {
            "enabled": True,
            "timeout_seconds": 20,
            "adapters": [
                {
                    "name": "demo-watchlist-ann",
                    "kind": "watchlist",
                    "event_type": "announcement",
                    "source": "demo-web",
                    "url_template": "https://example.com/announcements?code={symbol}",
                    "parser": {
                        "mode": "html_list",
                        "limit": 10,
                        "include_patterns": ["公告"],
                    },
                }
            ],
        }
        self.app.url_fetcher.config = self.app.config["url_sources"]
        html = """
        <html>
          <body>
            <a href="/detail/1.html">剑桥科技公告：算力订单扩容</a>
          </body>
        </html>
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://example.com/announcements?code=603083", "text/html")):
            result = self.app.fetch_watchlist_events(start_date="20260409", end_date="20260410")
        self.assertEqual(result["channels"]["url_adapters"]["inserted"], 1)
        self.assertEqual(result["inserted"], 1)
        self.assertFalse(result["errors"])

    def test_fetch_watchlist_events_can_fail_fast_on_repeated_tushare_errors(self) -> None:
        class DummyMarket:
            def call_endpoint(self, endpoint: str, **_: object) -> pd.DataFrame:
                if endpoint == "anns_d":
                    raise RuntimeError("抱歉，您没有接口访问权限")
                if endpoint == "news":
                    raise RuntimeError("抱歉，您每分钟最多访问该接口1次")
                return pd.DataFrame([])

        self.app.market = DummyMarket()
        self.app.add_watchlist("603083", name="剑桥科技")
        self.app.add_watchlist("300308", name="中际旭创")
        self.app.add_keyword("CPO")
        self.app.add_keyword("算力")

        result = self.app.fetch_watchlist_events(start_date="20260409", end_date="20260410")
        self.assertEqual(len([item for item in result["errors"] if item.startswith("announcement:")]), 1)
        self.assertEqual(len([item for item in result["errors"] if item.startswith("news:")]), 1)

    def test_fetch_url_events_can_parse_timeline_style_pages(self) -> None:
        html = """
        <html>
          <body>
            <div>09:15:00</div>
            <div>财联社电报：美股三大指数期货小幅走高</div>
            <div>市场等待晚间美国通胀数据。</div>
            <div>09:20:00</div>
            <div>金十数据：离岸人民币短线走强</div>
            <div>美元指数回落。</div>
          </body>
        </html>
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://example.com/live", "text/html")):
            result = self.app.fetch_url_events(
                url="https://example.com/live",
                event_type="macro",
                source="timeline-demo",
                parser_mode="html_timeline",
                trade_date="20260410",
                limit=10,
            )
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["events"][0]["source"], "timeline-demo")
        self.assertTrue(result["events"][0]["headline"])

    def test_fetch_url_events_can_clean_cls_style_headlines(self) -> None:
        html = """
        <html>
          <body>
            <div>09:15:00</div>
            <div>【美股盘前】财联社4月11日电，美股三大指数期货小幅走高。</div>
          </body>
        </html>
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://www.cls.cn/telegraph", "text/html")):
            result = self.app.fetch_url_events(
                url="https://www.cls.cn/telegraph",
                event_type="macro",
                source="cls",
                parser_mode="html_timeline",
                trade_date="20260410",
            )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["events"][0]["headline"], "美股盘前")
        self.assertIn("美股三大指数期货小幅走高", result["events"][0]["summary"])

    def test_fetch_url_events_can_filter_timeline_noise_and_combine_date_time(self) -> None:
        html = """
        <html>
          <body>
            <script>window.__BOOTSTRAP__ = {"headline": "不该出现的脚本文本"};</script>
            <div>04-11</div>
            <div>09:15:00</div>
            <div>金十数据：离岸人民币短线走强</div>
            <div>美元指数回落。</div>
            <div>登录后查看更多快讯</div>
            <div>TradingHero</div>
            <div>举报电话：021-54679377转617</div>
          </body>
        </html>
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://www.jin10.com/", "text/html")):
            result = self.app.fetch_url_events(
                url="https://www.jin10.com/",
                event_type="macro",
                source="jin10",
                parser_mode="html_timeline",
                trade_date="20260411",
                summary_lines=2,
                min_headline_length=8,
                ignore_tokens="金十数据,APP,详情,打开APP",
                drop_patterns="登录后查看更多快讯,TradingHero,举报电话",
            )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["events"][0]["headline"], "离岸人民币短线走强")
        self.assertEqual(result["events"][0]["published_at"], "2026-04-11 09:15:00")
        self.assertEqual(result["events"][0]["summary"], "美元指数回落。")

    def test_url_fetcher_can_decode_gbk_payload_without_charset_header(self) -> None:
        payload = "<html><body><div>财联社电报：人民币走强</div></body></html>".encode("gb18030")
        headers = Message()
        headers["Content-Type"] = "text/html"

        class DummyResponse:
            def __init__(self, body: bytes, response_headers: Message, final_url: str) -> None:
                self._body = body
                self.headers = response_headers
                self._final_url = final_url

            def __enter__(self) -> "DummyResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return self._body

            def geturl(self) -> str:
                return self._final_url

        fetcher = UrlEventFetcher(config={"timeout_seconds": 2})
        with patch("finance_journal_core.url_sources.urllib.request.urlopen", return_value=DummyResponse(payload, headers, "https://example.com/live")):
            text, final_url, content_type = fetcher.fetch_text("https://example.com/live")
        self.assertEqual(final_url, "https://example.com/live")
        self.assertEqual(content_type, "text/html")
        self.assertIn("财联社电报：人民币走强", text)

    def test_fetch_url_events_can_parse_embedded_json_blocks(self) -> None:
        html = """
        <html>
          <body>
            <script>
              window.__INITIAL_STATE__ = {"props":{"initialState":{"telegraph":{"telegraphList":[{"title":"巴基斯坦外长：希望美伊以建设性方式开展接触","brief":"财联社4月11日电，巴方希望各方以建设性方式开展接触。","ctime":1775892178,"shareurl":"https://api3.cls.cn/share/article/2341264"}]}}}};
            </script>
          </body>
        </html>
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://www.cls.cn/telegraph", "text/html")):
            result = self.app.fetch_url_events(
                url="https://www.cls.cn/telegraph",
                event_type="macro",
                source="cls",
                parser_mode="html_embedded_json",
                trade_date="20260411",
                script_markers="telegraphList",
                items_path="props.initialState.telegraph.telegraphList",
                headline_path="title",
                summary_path="brief",
                published_path="ctime",
                url_path="shareurl",
            )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["events"][0]["headline"], "巴基斯坦外长：希望美伊以建设性方式开展接触")
        self.assertEqual(result["events"][0]["url"], "https://api3.cls.cn/share/article/2341264")
        self.assertEqual(result["events"][0]["published_at"], "2026-04-11 15:22:58")

    def test_url_fetcher_can_fallback_from_timeline_to_embedded_json(self) -> None:
        html = """
        <html>
          <body>
            <script type="application/json" id="telegraph-json">
              {"props":{"initialState":{"telegraph":{"telegraphList":[{"title":"美国释放第二批848万桶战略石油储备","brief":"财联社4月11日电，美国能源部已释放第二批战略石油储备。","ctime":1775891234,"shareurl":"https://api3.cls.cn/share/article/2341257"}]}}}}
            </script>
          </body>
        </html>
        """
        adapter = {
            "name": "cls-telegraph",
            "event_type": "macro",
            "source": "cls",
            "parser": {
                "mode": "html_timeline",
                "fallback_mode": "html_embedded_json",
                "script_markers": ["unused-primary-marker"],
                "fallback_parser": {
                    "script_markers": ["telegraphList"],
                    "items_path": "props.initialState.telegraph.telegraphList",
                    "headline_path": "title",
                    "summary_path": "brief",
                    "published_path": "ctime",
                    "url_path": "shareurl",
                },
            },
        }
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(html, "https://www.cls.cn/telegraph", "text/html")):
            rows = self.app.url_fetcher.fetch_url_events(
                "https://www.cls.cn/telegraph",
                adapter,
                context={"trade_date": "20260411", "end_date": "20260411"},
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["headline"], "美国释放第二批848万桶战略石油储备")
        self.assertEqual(rows[0]["url"], "https://api3.cls.cn/share/article/2341257")

    def test_fetch_url_events_can_parse_jsonp_style_feed(self) -> None:
        payload = """
        callback({
          "data": {
            "fastNewsList": [
              {
                "title": "东方财富验证：美国释放第二批战略石油储备",
                "summary": "东方财富快讯示例。",
                "showTime": "2026-04-11 15:07:14",
                "code": "AN202604110001"
              }
            ]
          }
        })
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(payload, "https://np-weblist.eastmoney.com/comm/web/getFastNewsZhibo", "application/javascript")):
            result = self.app.fetch_url_events(
                url="https://np-weblist.eastmoney.com/comm/web/getFastNewsZhibo",
                event_type="macro",
                source="eastmoney",
                parser_mode="json_list",
                trade_date="20260411",
                items_path="data.fastNewsList",
                headline_path="title",
                summary_path="summary",
                published_path="showTime",
            )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["events"][0]["headline"], "验证：美国释放第二批战略石油储备")
        self.assertEqual(result["events"][0]["published_at"], "2026-04-11 15:07:14")

    def test_load_json_loose_can_parse_js_assignment_with_unquoted_keys(self) -> None:
        payload = """
        var thsRss = {
          pubDate:"2026/04/11 21:56:18",
          latestNewsSeq:"675920732",
          item:[
            {
              title:"伊美在伊斯兰堡开始直接会谈",
              content:"当地时间11日，据巴基斯坦方面消息，伊朗和美国已在伊斯兰堡开始直接会谈。",
              pubDate:"2026/04/11 21:44",
              extra:undefined,
            }
          ],
        };
        if (typeof(ths_rss_news_callback) != "undefined") {
          ths_rss_news_callback(thsRss);
        }
        """
        parsed = _load_json_loose(payload)
        self.assertEqual(parsed["pubDate"], "2026/04/11 21:56:18")
        self.assertEqual(parsed["item"][0]["title"], "伊美在伊斯兰堡开始直接会谈")
        self.assertIsNone(parsed["item"][0]["extra"])

    def test_fetch_url_events_can_parse_js_object_feed_and_build_item_url(self) -> None:
        payload = """
        var thsRss = {
          pubDate:"2026/04/11 21:56:18",
          item:[
            {
              title:"伊美在伊斯兰堡开始直接会谈",
              content:"当地时间11日，据巴基斯坦方面消息，伊朗和美国已在伊斯兰堡开始直接会谈。",
              pubDate:"2026/04/11 21:44",
              code:"c675920732"
            }
          ]
        };
        """
        with patch.object(self.app.url_fetcher, "fetch_text", return_value=(payload, "http://stock.10jqka.com.cn/thsgd/ywjh.js", "application/javascript")):
            result = self.app.fetch_url_events(
                url="http://stock.10jqka.com.cn/thsgd/ywjh.js",
                event_type="macro",
                source="10jqka",
                parser_mode="json_list",
                trade_date="20260411",
                items_path="item",
                headline_path="title",
                summary_path="content",
                published_path="pubDate",
                url_path="",
            )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["events"][0]["headline"], "伊美在伊斯兰堡开始直接会谈")
        self.assertEqual(result["events"][0]["published_at"], "2026-04-11 21:44")

    def test_url_fetcher_can_build_item_url_from_json_template(self) -> None:
        rows = self.app.url_fetcher._parse_json_payload(
            {"data": {"fastNewsList": [{"title": "测试标题", "summary": "测试摘要", "showTime": "2026-04-11 15:07:14", "code": "AN202604110001"}]}},
            "https://np-weblist.eastmoney.com/comm/web/getFastNewsZhibo",
            {
                "name": "eastmoney",
                "event_type": "macro",
                "source": "eastmoney",
                "parser": {
                    "items_path": "data.fastNewsList",
                    "headline_path": "title",
                    "summary_path": "summary",
                    "published_path": "showTime",
                    "item_url_template": "https://finance.eastmoney.com/a/{code}.html",
                },
            },
            {"trade_date": "20260411", "end_date": "20260411"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://finance.eastmoney.com/a/AN202604110001.html")

    def test_openclaw_session_turn_can_route_draft_and_enrich(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")

        first = self.app.handle_session_turn(
            "qq:user_a",
            "今天买了603083",
            trade_date="20260410",
        )
        self.assertEqual(first["route"], "draft_started")
        self.assertTrue(first["session_state"]["active_draft_id"])
        self.assertIn("下一问", first["assistant_message"])

        second = self.app.handle_session_turn(
            "qq:user_a",
            "43.2",
            trade_date="20260410",
        )
        self.assertEqual(second["route"], "draft_continued")
        self.assertIn("thesis", second["draft"]["missing_fields"])

        third = self.app.handle_session_turn(
            "qq:user_a",
            "逻辑是CPO修复回流，想做低吸。",
            trade_date="20260410",
        )
        self.assertEqual(third["route"], "draft_applied")
        self.assertEqual(third["session_state"]["active_entity_kind"], "trade")
        trade_id = third["session_state"]["active_entity_id"]
        self.assertTrue(trade_id)

        fourth = self.app.handle_session_turn(
            "qq:user_a",
            "补充：当时有点急，属于冲动追高。经验：下次先等回踩确认。",
            trade_date="20260410",
        )
        self.assertEqual(fourth["route"], "entity_enriched")
        trade = self.app.get_trade(trade_id)
        self.assertIsNotNone(trade)
        self.assertIn("冲动追高", json.loads(trade["mistake_tags_json"]))
        self.assertIn("有点急", trade["emotion_notes"])

        state = self.app.get_session_state("qq:user_a")
        self.assertEqual(state["session_state"]["active_entity_kind"], "trade")
        self.assertEqual(state["session_state"]["active_entity_id"], trade_id)

        reset = self.app.reset_session_thread("qq:user_a", reason="test_reset")
        self.assertEqual(reset["route"], "session_reset")
        self.assertEqual(reset["session_state"]["active_draft_id"], "")
        self.assertEqual(reset["session_state"]["active_entity_id"], "")

    def test_session_turn_can_reuse_same_day_environment_context(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")
        self.app.add_watchlist("600519", name="贵州茅台")

        first = self.app.handle_session_turn(
            "qq:user_env",
            "今天买了603083，43.2买的，逻辑是CPO修复回流低吸，市场还是震荡修复，消费板块也企稳了。",
            trade_date="20260410",
        )
        self.assertEqual(first["route"], "applied_from_session")
        self.assertIn("修复回流", first["result"]["draft"]["fields"]["environment_tags"])

        second = self.app.handle_session_turn(
            "qq:user_env",
            "今天买了600519，1350买的，逻辑是股息率低吸。",
            trade_date="20260410",
        )
        self.assertEqual(second["route"], "applied_from_session")
        second_fields = second["result"]["draft"]["fields"]
        self.assertIn("修复回流", second_fields["environment_tags"])
        self.assertTrue(any(item.get("scope") == "trade_date" for item in second["result"]["draft"].get("session_reuse", [])))
        self.assertFalse(
            any(item.get("field") == "environment_tags" for item in second["result"]["draft"]["reflection_prompts"])
        )

    def test_session_turn_can_reuse_same_symbol_thesis_for_repeat_trade(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")

        first = self.app.handle_session_turn(
            "qq:user_symbol",
            "今天买了603083，43.2买的，逻辑是CPO修复回流低吸。",
            trade_date="20260410",
        )
        self.assertEqual(first["route"], "applied_from_session")

        second = self.app.handle_session_turn(
            "qq:user_symbol",
            "今天又买了603083，44.1买的。",
            trade_date="20260410",
        )
        self.assertEqual(second["route"], "applied_from_session")
        second_fields = second["result"]["draft"]["fields"]
        self.assertIn("CPO", second_fields["thesis"])
        self.assertTrue(any(item.get("scope") == "symbol" for item in second["result"]["draft"].get("session_reuse", [])))

    def test_statement_import_can_align_trade_facts_and_prepare_follow_up(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")
        statement_path = self.runtime_root / "statement_rows.csv"
        statement_path.write_text(
            "ts_code,name,buy_date,buy_price,sell_date,sell_price,quantity\n"
            "603083,剑桥科技,20260410,43.2,20260415,46.8,1000\n",
            encoding="utf-8",
        )

        result = self.app.import_statement_file(
            str(statement_path),
            trade_date="20260415",
            session_key="qq:statement_user",
        )
        self.assertEqual(result["summary"]["imported_new"], 1)
        item = result["items"][0]
        self.assertEqual(item["status"], "imported_new")
        trade = self.app.get_trade(item["trade_id"])
        self.assertIsNotNone(trade)
        self.assertEqual(trade["buy_date"], "20260410")
        self.assertEqual(trade["sell_date"], "20260415")
        self.assertEqual(trade["buy_price"], 43.2)
        self.assertEqual(trade["sell_price"], 46.8)
        self.assertIn("thesis", item["follow_up"]["missing_fields"])
        self.assertTrue(item["follow_up"]["polling_bundle"]["next_question"])
        self.assertEqual(result["route"], "statement_import")
        self.assertEqual(result["pending_question"], item["follow_up"]["polling_bundle"]["next_question"])
        self.assertEqual(result["follow_up_queue"][0]["trade_id"], item["trade_id"])
        self.assertEqual(result["session_state"]["active_entity_kind"], "trade")
        self.assertEqual(result["session_state"]["active_entity_id"], item["trade_id"])
        self.assertEqual(result["session_state"]["pending_question"], item["follow_up"]["polling_bundle"]["next_question"])

        state = self.app.get_session_state("qq:statement_user")
        self.assertEqual(state["session_state"]["pending_question"], item["follow_up"]["polling_bundle"]["next_question"])
        self.assertIn("下一步建议补", state["assistant_message"])

        enriched = self.app.handle_session_turn(
            "qq:statement_user",
            "补充：当时看的是CPO回流和量能回暖，先按试错仓低吸。",
            trade_date="20260415",
        )
        self.assertEqual(enriched["route"], "entity_enriched")
        refreshed_trade = self.app.get_trade(item["trade_id"])
        self.assertIsNotNone(refreshed_trade)
        self.assertIn("CPO", refreshed_trade["thesis"])

    def test_gateway_can_import_statement_and_open_follow_up_session(self) -> None:
        self.app.add_watchlist("603083", name="剑桥科技")
        statement_path = self.runtime_root / "gateway_statement_rows.csv"
        statement_path.write_text(
            "证券代码,证券名称,买入日期,买入价格\n"
            "603083,剑桥科技,20260410,43.2\n",
            encoding="utf-8",
        )

        payload = dispatch(
            f"交易 导入 文件={statement_path} session=qq:gateway_statement trade_date=20260410",
            anchor_path=self.skill_root / "scripts" / "finance_journal_gateway.py",
            runtime_root=str(self.runtime_root),
            enable_market_data=False,
        )
        self.assertEqual(payload["route"], "statement_import")
        self.assertEqual(payload["summary"]["imported_new"], 1)
        self.assertTrue(payload["session_state"]["pending_question"])
        self.assertEqual(payload["session_state"]["active_entity_kind"], "trade")


if __name__ == "__main__":
    unittest.main()
