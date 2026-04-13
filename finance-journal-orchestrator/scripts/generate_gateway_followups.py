#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_journal_core.app import create_app


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Gateway Batch Follow-up",
        "",
        "## Summary",
        f"- total scanned: {payload['summary'].get('total_scanned', 0)}",
        f"- incomplete trades: {payload['summary'].get('incomplete_trades', 0)}",
        f"- group batches: {payload['summary'].get('group_batches', 0)}",
        f"- single batches: {payload['summary'].get('single_batches', 0)}",
        "",
    ]
    for index, batch in enumerate(payload.get("batches") or [], start=1):
        lines.extend(
            [
                f"## Batch {index}: {batch.get('title') or batch.get('batch_id')}",
                "",
                f"- kind: `{batch.get('kind')}`",
                f"- scope: `{batch.get('scope')}`",
                f"- trade_ids: {', '.join(batch.get('trade_ids') or []) or '-'}",
                f"- fields: {', '.join(batch.get('fields') or []) or '-'}",
                "",
                "### Prompt",
                "",
                batch.get("prompt") or "",
                "",
                "### Answer Template",
                "",
                "```text",
                batch.get("answer_template") or "",
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate grouped gateway follow-up prompts from incomplete trade backlog")
    parser.add_argument("--root", help="Runtime root for data/artifacts")
    parser.add_argument("--disable-market-data", action="store_true", help="Do not call Tushare")
    parser.add_argument("--status")
    parser.add_argument("--trade-date")
    parser.add_argument("--ts-code")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-complete", action="store_true")
    parser.add_argument("--max-groups", type=int, default=12)
    parser.add_argument("--max-group-trades", type=int, default=6)
    parser.add_argument("--max-singles", type=int, default=12)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", help="Optional output file path")
    args = parser.parse_args(argv)

    app = create_app(Path(__file__).resolve(), runtime_root=args.root, enable_market_data=not args.disable_market_data)
    payload = app.build_gateway_follow_up_batches(
        status=args.status,
        limit=args.limit,
        trade_date=args.trade_date,
        ts_code=args.ts_code,
        include_complete=args.include_complete,
        max_group_batches=args.max_groups,
        max_group_trades=args.max_group_trades,
        max_single_batches=args.max_singles,
    )

    if args.format == "markdown":
        rendered = _render_markdown(payload)
    else:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
