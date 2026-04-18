from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finance_journal_core.app import FinanceJournalApp


class RuntimeMaintenanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temp_dir.name) / "runtime"
        self.repo_root = Path(self.temp_dir.name) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.skill_root = Path(__file__).resolve().parents[1] / "finance-journal-orchestrator"
        self.app = FinanceJournalApp(
            repo_root=self.repo_root,
            skill_root=self.skill_root,
            runtime_root=str(self.runtime_root),
            enable_market_data=False,
        )
        self.app.init_runtime()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sync_vault_full_clean_exports_graph_note(self) -> None:
        self.app.log_trade(
            ts_code="000001.SZ",
            name="PingAn",
            buy_date="20260413",
            buy_price=12.3,
            thesis="Breakout retest held.",
            buy_reason="Breakout held VWAP.",
            environment_tags=["bank"],
        )

        payload = self.app.sync_vault(full=True, clean=True)

        graph_path = self.runtime_root / "obsidian-vault" / "08-graph" / "local_knowledge_graph_snapshot.md"
        self.assertTrue(graph_path.exists())
        self.assertIn(str(graph_path), payload["paths"])

    def test_mirror_runtime_exports_to_repo_root_copies_runtime_views(self) -> None:
        self.app.log_trade(
            ts_code="000001.SZ",
            name="PingAn",
            buy_date="20260413",
            buy_price=12.3,
            thesis="Mirror test.",
            buy_reason="Mirror setup.",
            environment_tags=["bank"],
        )
        self.app.sync_vault(full=True, clean=True)

        payload = self.app.mirror_runtime_exports_to_repo_root()

        self.assertTrue((self.repo_root / "artifacts").exists())
        self.assertTrue((self.repo_root / "obsidian-vault" / "08-graph" / "local_knowledge_graph_snapshot.md").exists())
        self.assertEqual(payload["artifacts"]["destination"], str(self.repo_root / "artifacts"))
        self.assertEqual(payload["obsidian_vault"]["destination"], str(self.repo_root / "obsidian-vault"))

    def test_sync_repo_snapshot_rebuilds_and_mirrors_runtime_exports(self) -> None:
        repo_runtime_app = FinanceJournalApp(
            repo_root=self.repo_root,
            skill_root=self.skill_root,
            runtime_root=str(self.repo_root / "_runtime"),
            enable_market_data=False,
        )
        repo_runtime_app.init_runtime()
        repo_runtime_app.log_trade(
            ts_code="000001.SZ",
            name="PingAn",
            buy_date="20260418",
            buy_price=12.3,
            thesis="Sync the full repo snapshot.",
            buy_reason="Full export check.",
            environment_tags=["bank"],
        )

        payload = repo_runtime_app.sync_repo_snapshot()

        self.assertTrue((self.repo_root / "artifacts").exists())
        self.assertTrue((self.repo_root / "obsidian-vault" / "08-graph" / "local_knowledge_graph_snapshot.md").exists())
        self.assertEqual(payload["self_check"]["status"], "ok")
        self.assertTrue(payload["self_check"]["mirror_state"]["in_sync"])

    def test_runtime_self_check_warns_when_runtime_root_differs_from_repo_runtime(self) -> None:
        self.app.log_trade(
            ts_code="000001.SZ",
            name="PingAn",
            buy_date="20260418",
            buy_price=12.3,
            thesis="Check runtime mismatch warning.",
            buy_reason="Diagnose cloud mismatch.",
            environment_tags=["bank"],
        )
        self.app.sync_vault(full=True, clean=True)
        self.app.mirror_runtime_exports_to_repo_root()

        payload = self.app.runtime_self_check()

        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["matches_repo_runtime"])
        self.assertTrue(any("different ledger" in item for item in payload["warnings"]))
        self.assertTrue(payload["mirror_state"]["in_sync"])

    def test_purge_records_in_date_range_removes_march_rows_and_rebuilds_runtime_views(self) -> None:
        self.app.log_trade(
            ts_code="000001.SZ",
            name="PingAn",
            buy_date="20260318",
            buy_price=12.3,
            thesis="Old March trade.",
            buy_reason="March setup.",
            environment_tags=["legacy"],
        )
        april_trade = self.app.log_trade(
            ts_code="000002.SZ",
            name="Vanke",
            buy_date="20260416",
            buy_price=9.8,
            thesis="Keep April trade.",
            buy_reason="April setup.",
            environment_tags=["survivor"],
        )

        payload = self.app.purge_records_in_date_range("20260201", "20260331")

        trades = self.app.list_trades(limit=20)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["trade_id"], april_trade["trade_id"])
        self.assertEqual(payload["deleted"]["trades"], 1)
        self.assertEqual(self.app.db.fetchone("SELECT COUNT(*) AS count FROM memory_cells", ())["count"], 1)

        memory_files = [item.name for item in (self.runtime_root / "memory").glob("*")]
        self.assertTrue(all(not name.startswith("202603") for name in memory_files))

        graph_path = self.runtime_root / "obsidian-vault" / "08-graph" / "local_knowledge_graph_snapshot.md"
        self.assertTrue(graph_path.exists())


if __name__ == "__main__":
    unittest.main()
