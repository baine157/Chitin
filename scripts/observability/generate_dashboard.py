#!/usr/bin/env python3
"""Compatibility wrapper for the canonical CoS dashboard collector.

The old generator emitted a legacy dashboard shape that omitted packet execution
truth. Keep this entry point so older launchers or muscle-memory commands still
produce the collector schema used by the UI and promotion checks.
"""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collect_dashboard import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
