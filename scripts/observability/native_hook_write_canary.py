#!/usr/bin/env python3
"""Local write-path canary for OpenClaw/BearClaw execution substrate checks."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_DIR = REPO_ROOT / "state" / "observability"
DEFAULT_OUTPUT = OBSERVABILITY_DIR / "native-hook-write-canary.json"
DEFAULT_TEST_PATH = OBSERVABILITY_DIR / "canaries" / "native-hook-write-path.txt"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build_payload(
    *,
    status: str,
    test_path: Path,
    operation_results: dict[str, Any],
    detected_error: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "canary_name": "native_hook_write_path",
        "timestamp": utc_now(),
        "path_tested": str(test_path),
        "path_tested_relative": rel(test_path),
        "operation_results": operation_results,
        "detected_error": detected_error,
        "remediation_hint": (
            "Gateway health is necessary but insufficient. If this canary is blocked, "
            "repair local filesystem/sandbox write access before host-mutating tasks. "
            "If this canary is ok but Telegram reports Native hook relay unavailable, "
            "treat the live Telegram session relay as still unverified or degraded."
        ),
        "gateway_health": {
            "role": "necessary_but_insufficient",
            "tested_by_this_canary": False,
        },
        "native_hook_write_path": {
            "tested_by_this_canary": True,
            "status": status,
        },
        "telegram_session_native_hook": {
            "tested_by_this_canary": False,
            "status": "unverified",
            "reason": "A terminal-local file canary cannot prove a live Telegram session native-hook relay.",
        },
        "external_effect": {
            "occurred": False,
            "details": "local file write/read/remove only",
        },
    }


def run_canary(test_path: Path) -> dict[str, Any]:
    marker = f"native-hook-write-canary {utc_now()}\n"
    operation_results: dict[str, Any] = {
        "ensure_parent": False,
        "write": False,
        "read": False,
        "content_matches": False,
        "remove": False,
        "removed": False,
    }

    try:
        test_path.parent.mkdir(parents=True, exist_ok=True)
        operation_results["ensure_parent"] = True
        test_path.write_text(marker, encoding="utf-8")
        operation_results["write"] = True
        readback = test_path.read_text(encoding="utf-8")
        operation_results["read"] = True
        operation_results["content_matches"] = readback == marker
        test_path.unlink()
        operation_results["remove"] = True
        operation_results["removed"] = not test_path.exists()
        status = "ok" if all(operation_results.values()) else "degraded"
        return build_payload(
            status=status,
            test_path=test_path,
            operation_results=operation_results,
            detected_error=None if status == "ok" else "local write-path operation mismatch",
        )
    except PermissionError as exc:
        return build_payload(
            status="blocked",
            test_path=test_path,
            operation_results=operation_results,
            detected_error=f"{type(exc).__name__}: {exc}",
        )
    except OSError as exc:
        return build_payload(
            status="error",
            test_path=test_path,
            operation_results=operation_results,
            detected_error=f"{type(exc).__name__}: {exc}",
        )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    resolved = path.resolve()
    allowed_root = OBSERVABILITY_DIR.resolve()
    if resolved != allowed_root and allowed_root not in resolved.parents:
        raise SystemExit(f"refusing to write outside {rel(allowed_root)}: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = resolved.with_suffix(resolved.suffix + f".tmp.{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(resolved)


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local native-hook/write-path canary.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--test-path", default=str(DEFAULT_TEST_PATH))
    parser.add_argument("--no-write-result", action="store_true", help="Print JSON only; do not write result file.")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    payload = run_canary(Path(args.test_path).expanduser().resolve())
    if not args.no_write_result:
        write_json(Path(args.output).expanduser(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
