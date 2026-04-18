from __future__ import annotations

import json
import unittest

from finance_journal_core.vault import render_daily_note, render_graph_note, render_trade_note


class VaultExportRenderTest(unittest.TestCase):
    def test_trade_note_includes_subjective_reasons_and_behavior(self) -> None:
        trade = {
            "trade_id": "trade_demo",
            "ts_code": "000001.SZ",
            "name": "PingAn",
            "status": "closed",
            "buy_date": "20260413",
            "sell_date": "20260414",
            "buy_price": 12.3,
            "sell_price": 12.9,
            "actual_return_pct": 4.88,
            "timing_alpha_pct": 1.2,
            "holding_days": 1,
            "thesis": "Breakout retest held.",
            "buy_reason": "Breakout held VWAP.",
            "sell_reason": "Lost intraday VWAP.",
            "buy_position": "Starter size",
            "sell_position": "Trimmed into weakness",
            "logic_type_tags_json": json.dumps(["trend"]),
            "pattern_tags_json": json.dumps(["breakout"]),
            "market_stage_tag": "risk-on",
            "environment_tags_json": json.dumps(["ai"]),
            "decision_context_json": json.dumps({"position_reason": "Starter size for confirmation."}),
            "emotion_notes": "Calm",
            "mistake_tags_json": json.dumps(["impatient"]),
            "lessons_learned": "Let strong names breathe.",
            "notes": "manual note",
        }

        markdown = render_trade_note(trade)

        self.assertIn("- Buy reason: Breakout held VWAP.", markdown)
        self.assertIn("- Sell reason: Lost intraday VWAP.", markdown)
        self.assertIn("- Emotion notes: Calm", markdown)
        self.assertIn("- Mistake tags: impatient", markdown)
        self.assertIn("- Lessons learned: Let strong names breathe.", markdown)

    def test_daily_note_summarizes_subjective_trade_fields(self) -> None:
        trades = [
            {
                "name": "PingAn",
                "buy_price": 12.3,
                "sell_price": 12.9,
                "actual_return_pct": 4.88,
                "buy_reason": "Breakout held VWAP.",
                "sell_reason": "Lost intraday VWAP.",
                "emotion_notes": "Calm",
                "mistake_tags_json": json.dumps(["impatient"]),
                "lessons_learned": "Let strong names breathe.",
                "decision_context_json": json.dumps({"position_reason": "Starter size for confirmation."}),
            }
        ]

        markdown = render_daily_note(
            "20260413",
            plans=[],
            trades=trades,
            reviews=[],
            memory_cells=[],
            skill_cards=[],
        )

        self.assertIn("  - Reasons: buy=Breakout held VWAP. | sell=Lost intraday VWAP. | position=Starter size for confirmation.", markdown)
        self.assertIn("  - Behavior: emotion=Calm | mistakes=impatient | lesson=Let strong names breathe.", markdown)

    def test_graph_note_includes_prompt_and_graph_sections(self) -> None:
        markdown = render_graph_note(
            {
                "stats": {"trade_count": 2, "memory_count": 3, "scene_count": 1, "hyperedge_count": 1, "skill_count": 1},
                "recent_scenes": [{"title": "CPO Pullback", "scene_type": "strategy", "description": "Recent repair scene.", "memory_ids_json": json.dumps(["m1", "m2"])}],
                "recent_hyperedges": [{"label": "trend:pullback", "edge_type": "tag_cluster", "tags_json": json.dumps(["trend", "pullback"])}],
                "recent_memory_cells": [{"title": "Trade | PingAn", "memory_kind": "trade", "trade_date": "20260413", "ts_code": "000001.SZ"}],
                "recent_skill_cards": [{"title": "Low-risk pullback", "sample_size": 2, "intent": "Wait for confirmation."}],
                "prompt_text": "Sync to Obsidian after journaling.",
            }
        )

        self.assertIn("# Local Knowledge Graph Snapshot", markdown)
        self.assertIn("## OpenClaw Prompt", markdown)
        self.assertIn("Sync to Obsidian after journaling.", markdown)


if __name__ == "__main__":
    unittest.main()
