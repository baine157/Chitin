#!/usr/bin/env python3
"""Host-side OpenClaw relay repair and verification lane.

This is intentionally runnable from a normal Z420 terminal, outside the stale
Telegram/native-hook path. It repairs common stale task/session state, restarts
the managed gateway service, then writes a proof-bearing JSON artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_DIR = REPO_ROOT / "state" / "observability"
DEFAULT_OUTPUT = OBSERVABILITY_DIR / "openclaw-relay-repair.json"
OPENCLAW_CONFIG_PATH = Path("/home/baine/.openclaw/openclaw.json")
OPENCLAW_SERVICE_ENV_PATH = Path("/home/baine/.openclaw/gateway.systemd.env")
LOG_GLOB = Path("/tmp/openclaw")
RELAY_ERROR_RE = re.compile(
    r"native hook relay not found|Native hook relay unavailable|relay unavailable",
    re.IGNORECASE,
)
AGENT_SMOKE_MESSAGE = "Smoke test only. Reply exactly: OK"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    for key, value in load_env_file(OPENCLAW_SERVICE_ENV_PATH).items():
        env.setdefault(key, value)
    return env


def gateway_password(env: dict[str, str]) -> str | None:
    try:
        config = json.loads(OPENCLAW_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    auth = config.get("gateway", {}).get("auth", {})
    password_ref = auth.get("password")
    if isinstance(password_ref, str):
        return password_ref
    if isinstance(password_ref, dict) and password_ref.get("source") == "env":
        key = str(password_ref.get("id") or "")
        return env.get(key) if key else None
    return None


def run_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: int = 60,
    display_command: list[str] | None = None,
) -> dict[str, Any]:
    shown = display_command or command
    started_at = utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "status": "missing",
            "ok": False,
            "command": shown,
            "started_at": started_at,
            "ended_at": utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "ok": False,
            "command": shown,
            "started_at": started_at,
            "ended_at": utc_now(),
            "timeout_seconds": timeout,
            "stdout_excerpt": (exc.stdout or "")[:2000],
            "stderr_excerpt": (exc.stderr or "")[:2000],
        }
    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "ok": completed.returncode == 0,
        "command": shown,
        "started_at": started_at,
        "ended_at": utc_now(),
        "exit_code": completed.returncode,
        "stdout_excerpt": (completed.stdout or "")[:2000],
        "stderr_excerpt": (completed.stderr or "")[:2000],
        "native_hook_relay_error_seen": bool(RELAY_ERROR_RE.search(output)),
    }


def log_offsets() -> dict[str, int]:
    offsets: dict[str, int] = {}
    for path in sorted(LOG_GLOB.glob("openclaw-*.log")):
        try:
            offsets[str(path)] = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return offsets


def scan_new_relay_errors(offsets: dict[str, int]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for raw_path, start_line in offsets.items():
        path = Path(raw_path)
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle, start=1):
                    if index <= start_line:
                        continue
                    if RELAY_ERROR_RE.search(line):
                        hits.append({"path": str(path), "line": index, "excerpt": line.rstrip()[:1000]})
        except OSError:
            continue
    return hits


def parse_gateway_probe(payload: dict[str, Any]) -> dict[str, Any]:
    stdout = str(payload.get("stdout_excerpt") or "")
    if not stdout.strip().startswith("{"):
        return {"parsed": None}
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {"parsed": None, "parse_error": "invalid json"}
    return {
        "parsed": {
            "ok": parsed.get("ok"),
            "degraded": parsed.get("degraded"),
            "capability": parsed.get("capability"),
            "warnings": parsed.get("warnings", []),
        }
    }


def run_gateway_probe_with_retries(
    *,
    env: dict[str, str],
    auth_args: list[str],
    display_auth_args: list[str],
    attempts: int,
    delay_seconds: float,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index in range(attempts):
        result = run_command(
            ["openclaw", "gateway", "probe", "--json", *auth_args],
            env=env,
            timeout=45,
            display_command=["openclaw", "gateway", "probe", "--json", *display_auth_args],
        )
        result.update(parse_gateway_probe(result))
        result["attempt"] = index + 1
        results.append(result)
        parsed = result.get("parsed") or {}
        if parsed.get("ok") is True:
            return {
                **result,
                "attempts": results,
                "retry_summary": f"passed on attempt {index + 1} of {attempts}",
            }
        if index + 1 < attempts:
            time.sleep(delay_seconds)
    final = results[-1] if results else {"status": "failed", "ok": False}
    return {
        **final,
        "attempts": results,
        "retry_summary": f"failed after {len(results)} attempts",
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    env = command_env()
    password = gateway_password(env)
    auth_available = bool(password)
    auth_args = ["--password", password] if password else []
    display_auth_args = ["--password", "<redacted>"] if password else []
    commands: dict[str, Any] = {}
    before_offsets = log_offsets()

    commands["version"] = run_command(["openclaw", "--version"], env=env, timeout=20)
    commands["tasks_maintenance"] = run_command(
        ["openclaw", "tasks", "maintenance", "--apply", "--json"],
        env=env,
        timeout=120,
    )
    commands["sessions_cleanup"] = run_command(
        ["openclaw", "sessions", "cleanup", "--all-agents", "--enforce", "--fix-missing", "--json"],
        env=env,
        timeout=180,
    )
    commands["systemd_restart"] = run_command(
        ["systemctl", "--user", "restart", "openclaw-gateway.service"],
        env=env,
        timeout=60,
    )
    time.sleep(args.settle_seconds)
    commands["gateway_status"] = run_command(
        ["openclaw", "gateway", "status", "--deep", "--json", *auth_args],
        env=env,
        timeout=45,
        display_command=["openclaw", "gateway", "status", "--deep", "--json", *display_auth_args],
    )
    commands["gateway_probe"] = run_gateway_probe_with_retries(
        env=env,
        auth_args=auth_args,
        display_auth_args=display_auth_args,
        attempts=args.probe_attempts,
        delay_seconds=args.probe_retry_seconds,
    )
    commands["hooks_check"] = run_command(["openclaw", "hooks", "check"], env=env, timeout=60)

    if args.include_agent_smoke:
        commands["agent_smoke"] = run_command(
            [
                "openclaw",
                "agent",
                "--agent",
                "main",
                "--message",
                AGENT_SMOKE_MESSAGE,
                "--thinking",
                "low",
                "--json",
                "--timeout",
                str(args.agent_timeout),
            ],
            env=env,
            timeout=args.agent_timeout + 30,
        )
    else:
        commands["agent_smoke"] = {
            "status": "unverified",
            "ok": None,
            "skipped": True,
            "command": ["openclaw", "agent", "--agent", "main", "--message", "<smoke>", "--json"],
        }

    relay_hits = scan_new_relay_errors(before_offsets)
    decisive = {
        "gateway_auth_material_available": auth_available,
        "gateway_probe_ok": commands["gateway_probe"].get("parsed", {}).get("ok") is True,
        "hooks_ready": commands["hooks_check"].get("ok") is True
        and "Ready: 4" in str(commands["hooks_check"].get("stdout_excerpt") or "")
        and "Not ready: 0" in str(commands["hooks_check"].get("stdout_excerpt") or ""),
        "agent_smoke_ok": commands["agent_smoke"].get("ok") is True,
        "new_relay_errors": len(relay_hits),
    }

    if relay_hits:
        status = "degraded"
    elif not decisive["gateway_auth_material_available"]:
        status = "blocked"
    elif not decisive["gateway_probe_ok"] or not decisive["hooks_ready"]:
        status = "degraded"
    elif args.include_agent_smoke and not decisive["agent_smoke_ok"]:
        status = "degraded"
    elif not args.include_agent_smoke:
        status = "unverified"
    else:
        status = "ok"

    return {
        "schema_version": 1,
        "repair_name": "openclaw_relay_repair",
        "timestamp": utc_now(),
        "status": status,
        "decisive": decisive,
        "commands": commands,
        "relay_error_hits_since_start": relay_hits,
        "operator_readback": {
            "control_plane_health_is_not_execution_health": True,
            "gateway_probe_requires_gateway_auth_material": True,
            "telegram_live_session_still_requires_live_session_smoke": True,
            "external_action_rule": (
                "No sent/submitted/finalized claim without action-specific verification readback."
            ),
        },
        "external_effect": {
            "occurred": False,
            "details": "Local OpenClaw maintenance, gateway service restart, and internal smoke only.",
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    assert_under_observability(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair and verify OpenClaw relay health from the host.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-agent-smoke", action="store_true")
    parser.add_argument("--agent-timeout", type=int, default=180)
    parser.add_argument("--settle-seconds", type=float, default=5.0)
    parser.add_argument("--probe-attempts", type=int, default=4)
    parser.add_argument("--probe-retry-seconds", type=float, default=3.0)
    parser.add_argument("--no-write-result", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    payload = build_payload(args)
    if not args.no_write_result:
        write_json(Path(args.output).expanduser(), payload)
    print(json.dumps({"status": payload["status"], "output": rel(Path(args.output))}, sort_keys=True))
    return 0 if payload["status"] in {"ok", "unverified"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
