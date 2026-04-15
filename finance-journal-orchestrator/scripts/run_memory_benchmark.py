#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_journal_core.app import create_app
from finance_journal_core.benchmark import run_memory_retrieval_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Finance Journal memory retrieval benchmark")
    parser.add_argument("--root", help="Dedicated runtime root for benchmark artifacts")
    parser.add_argument("--disable-market-data", action="store_true")
    parser.add_argument("--trade-date", default="20260418")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--no-write-artifact", action="store_true", help="Do not write markdown/json benchmark artifacts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = create_app(Path(__file__).resolve(), runtime_root=args.root, enable_market_data=not args.disable_market_data)
    payload = run_memory_retrieval_benchmark(
        app,
        trade_date=args.trade_date,
        limit=args.limit,
        write_artifact=not args.no_write_artifact,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
