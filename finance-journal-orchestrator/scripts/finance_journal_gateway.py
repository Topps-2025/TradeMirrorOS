#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_journal_core.gateway import main


if __name__ == "__main__":
    raise SystemExit(main(anchor_path=Path(__file__).resolve()))
