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


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance Journal OpenClaw session agent")
    parser.add_argument("--root", help="Runtime root for data/artifacts")
    parser.add_argument("--disable-market-data", action="store_true")
    parser.add_argument("--session-key", required=True)
    parser.add_argument("--text")
    parser.add_argument("--mode", choices=["auto", "trade", "plan"], default="auto")
    parser.add_argument("--trade-date")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--state", action="store_true", help="Show current session state")
    parser.add_argument("--reset", action="store_true", help="Reset current session state")
    parser.add_argument("--reason", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = create_app(Path(__file__).resolve(), runtime_root=args.root, enable_market_data=not args.disable_market_data)
    if args.reset:
        _print(app.reset_session_thread(args.session_key, reason=args.reason))
        return 0
    if args.state or not args.text:
        _print(app.get_session_state(args.session_key))
        return 0
    _print(
        app.handle_session_turn(
            args.session_key,
            args.text,
            mode=args.mode,
            trade_date=args.trade_date,
            lookback_days=args.lookback_days,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
