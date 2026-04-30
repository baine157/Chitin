#!/usr/bin/env python3
"""Safe live-session native-hook smoke artifact writer.

This script is intentionally local-only. A terminal run can verify that this
host can mutate local state, but only a Telegram-origin run can prove that the
current live Telegram session has a working native-hook relay.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_DIR = REPO_ROOT / "state" / "observability"
CANARY_DIR = OBSERVABILITY_DIR / "canaries"
TEST_FILE = CANARY_DIR / "live-session-native-hook-smoke.txt"
RESULT_FILE = OBSERVABILITY_DIR / "live-session-native-hook-smoke.json"
ALLOWED_ORIGINS = {"terminal-local", "telegram-live-session"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def assert_under_observability(path: Path) -> None:
    resolved = path.resolve()
    allowed = OBSERVABILITY_DIR.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise SystemExit(f"refusing to write outside {rel(allowed)}: {resolved}")


def build_result(
    *,
    execution_origin: str,
    status: str,
    operation_results: dict[str, Any],
    detected_error: str | None,
) -> dict[str, Any]:
    telegram_status = "ok" if execution_origin == "telegram-live-session" and status == "ok" else "unverified"
    reason = None
    if execution_origin != "telegram-live-session":
        reason = "Terminal-local execution does not prove the current live Telegram session native-hook relay."
    elif status != "ok":
        reason = "Live Telegram session smoke did not complete cleanly."

    return {
        "status": status,
        "smoke_name": "live_session_native_hook",
        "timestamp": utc_now(),
        "execution_origin": execution_origin,
        "path_tested": rel(TEST_FILE),
        "operation_results": operation_results,
        "detected_error": detected_error,
        "remediation_hint": (
            "If Telegram reports Native hook relay unavailable, treat the live session as blocked: "
            "try /new or /reset, rerun this smoke from Telegram, then restart the OpenClaw gateway only if needed."
        ),
        "gateway_health": {
            "role": "necessary_but_insufficient",
            "tested_by_this_smoke": False,
        },
        "native_hook_write_path": {
            "tested_by_this_smoke": True,
            "scope": "tiny local state file write/read/remove",
        },
        "telegram_session_native_hook": {
            "status": telegram_status,
            "tested_by_this_smoke": execution_origin == "telegram-live-session",
            "reason": reason,
        },
        "terminal_local_run_does_not_prove_telegram": execution_origin != "telegram-live-session",
        "external_effect": {
            "occurred": False,
            "details": "Local observability state file only; no network, credentials, browser, portal, or external system.",
        },
    }


def run_smoke(execution_origin: str) -> dict[str, Any]:
    operation_results: dict[str, Any] = {
        "write_attempted": False,
        "read_attempted": False,
        "remove_attempted": False,
        "write_ok": False,
        "read_ok": False,
        "remove_ok": False,
        "content_matches": False,
    }
    detected_error = None
    status = "ok"
    content = f"live-session-native-hook-smoke {execution_origin} {utc_now()}\n"

    try:
        assert_under_observability(TEST_FILE)
        assert_under_observability(RESULT_FILE)
        CANARY_DIR.mkdir(parents=True, exist_ok=True)

        operation_results["write_attempted"] = True
        TEST_FILE.write_text(content, encoding="utf-8")
        operation_results["write_ok"] = True

        operation_results["read_attempted"] = True
        observed = TEST_FILE.read_text(encoding="utf-8")
        operation_results["read_ok"] = True
        operation_results["content_matches"] = observed == content

        operation_results["remove_attempted"] = True
        TEST_FILE.unlink()
        operation_results["remove_ok"] = True

        if not operation_results["content_matches"]:
            status = "degraded"
            detected_error = "read content did not match written content"
    except OSError as exc:
        status = "error"
        detected_error = str(exc)
    except Exception as exc:  # noqa: BLE001 - smoke output should capture unexpected local failures.
        status = "error"
        detected_error = str(exc)

    return build_result(
        execution_origin=execution_origin,
        status=status,
        operation_results=operation_results,
        detected_error=detected_error,
    )


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live-session native-hook smoke contract.")
    parser.add_argument(
        "--execution-origin",
        choices=sorted(ALLOWED_ORIGINS),
        default="terminal-local",
        help="Use telegram-live-session only when invoked by the exact Telegram session being tested.",
    )
    parser.add_argument(
        "--output",
        default=str(RESULT_FILE),
        help="Result path under state/observability/.",
    )
    return parser.parse_args()


def main() -> int:
    args = build_args()
    output = Path(args.output)
    assert_under_observability(output)
    result = run_smoke(args.execution_origin)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": rel(output), "execution_origin": args.execution_origin}, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
