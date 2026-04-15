from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finance_journal_core.app import FinanceJournalApp
from finance_journal_core.benchmark import run_memory_retrieval_benchmark


class MemoryBenchmarkTest(unittest.TestCase):
    def test_graph_hybrid_beats_baselines_on_demo_corpus(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill_root = repo_root / "finance-journal-orchestrator"
        with tempfile.TemporaryDirectory() as temp_dir:
            app = FinanceJournalApp(
                repo_root=repo_root,
                skill_root=skill_root,
                runtime_root=str(Path(temp_dir) / "runtime"),
                enable_market_data=False,
            )
            app.init_runtime()
            report = run_memory_retrieval_benchmark(app, write_artifact=False)

        metrics = {item["method"]: item["aggregate_metrics"] for item in report["methods"]}
        self.assertGreater(metrics["graph_hybrid"]["recall@3"], metrics["fts_only"]["recall@3"])
        self.assertGreater(metrics["graph_hybrid"]["recall@3"], metrics["structured_only"]["recall@3"])
        self.assertGreaterEqual(metrics["graph_hybrid"]["recall@3"], metrics["hybrid_cell_only"]["recall@3"])
        self.assertGreaterEqual(metrics["graph_hybrid"]["ndcg"], metrics["hybrid_cell_only"]["ndcg"])


if __name__ == "__main__":
    unittest.main()
