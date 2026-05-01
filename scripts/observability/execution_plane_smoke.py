#!/usr/bin/env python3
"""Execution-plane smoke for OpenClaw/BearClaw runtime truth.

This script intentionally separates control-plane liveness from machine
execution reachability. Gateway and hook-registry checks are useful signals,
but a local shell smoke and an optional agent smoke are the evidence that work
can actually execute.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_DIR = REPO_ROOT / "state" / "observability"
DEFAULT_OUTPUT = OBSERVABILITY_DIR / "execution-plane-smoke.json"
SHELL_MARKER = "execution-plane-shell-ok"
AGENT_SMOKE_MESSAGE = "Smoke test only. Reply exactly: OK"
OPENCLAW_CONFIG_PATH = Path("/home/baine/.openclaw/openclaw.json")
OPENCLAW_SERVICE_ENV_PATH = Path("/home/baine/.openclaw/gateway.systemd.env")


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


def gateway_password() -> str | None:
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
        if not key:
            return None
        return os.environ.get(key) or load_env_file(OPENCLAW_SERVICE_ENV_PATH).get(key)
    return None


def gateway_auth_args() -> tuple[list[str], list[str]]:
    password = gateway_password()
    if not password:
        return [], []
    return ["--password", password], ["--password", "<redacted>"]


def run_command(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 30,
    display_command: list[str] | None = None,
) -> dict[str, Any]:
    shown = display_command or command
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
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
            "error": f"{type(exc).__name__}: {exc}",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "ok": False,
            "command": shown,
            "timeout_seconds": timeout,
            "stdout_excerpt": (exc.stdout or "")[:1000],
            "stderr_excerpt": (exc.stderr or "")[:1000],
        }

    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "ok": completed.returncode == 0,
        "command": shown,
        "exit_code": completed.returncode,
        "stdout_excerpt": (completed.stdout or "")[:1000],
        "stderr_excerpt": (completed.stderr or "")[:1000],
        "native_hook_relay_error_seen": "Native hook relay unavailable" in output
        or "native hook relay not found" in output,
    }


def gateway_probe() -> dict[str, Any]:
    auth_args, display_auth_args = gateway_auth_args()
    command = ["openclaw", "gateway", "probe", "--json", *auth_args]
    display_command = ["openclaw", "gateway", "probe", "--json", *display_auth_args]
    result = run_command(command, timeout=20, display_command=display_command)
    payload = None
    if result.get("stdout_excerpt", "").strip().startswith("{"):
        try:
            payload = json.loads(result["stdout_excerpt"])
        except json.JSONDecodeError:
            payload = None
    return {
        **result,
        "payload": payload,
        "auth_material_available": bool(auth_args),
        "role": "necessary_but_insufficient",
        "truth_note": "Gateway reachability does not prove native hook relay or shell execution health.",
    }


def hooks_check() -> dict[str, Any]:
    result = run_command(["openclaw", "hooks", "check"], timeout=30)
    return {
        **result,
        "role": "necessary_but_insufficient",
        "truth_note": "Hook registry readiness does not prove the current live session can invoke hooks.",
    }


def shell_execution() -> dict[str, Any]:
    result = run_command(["bash", "-lc", f"printf {SHELL_MARKER}"], timeout=10)
    marker_seen = result.get("stdout_excerpt") == SHELL_MARKER
    return {
        **result,
        "status": "ok" if result.get("ok") and marker_seen else "failed",
        "ok": bool(result.get("ok") and marker_seen),
        "marker_seen": marker_seen,
    }


def codex_cli() -> dict[str, Any]:
    binary = shutil.which("codex")
    if not binary:
        return {
            "status": "missing",
            "ok": False,
            "binary": None,
            "truth_note": "Codex CLI is not on PATH for this worker environment.",
        }
    result = run_command(["codex", "--help"], timeout=20)
    return {
        **result,
        "binary": binary,
        "truth_note": "This proves Codex CLI availability, not attachment to a specific Telegram/OpenClaw session.",
    }


def agent_smoke(include: bool, timeout: int) -> dict[str, Any]:
    if not include:
        return {
            "status": "unverified",
            "ok": None,
            "skipped": True,
            "truth_note": "Pass --include-agent-smoke to prove OpenClaw agent execution from this environment.",
        }
    result = run_command(
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
            str(timeout),
        ],
        timeout=timeout + 15,
    )
    return {
        **result,
        "truth_note": "This is the decisive smoke for OpenClaw agent execution from this environment.",
    }


def external_action_verification(
    *,
    local_shell: dict[str, Any],
    agent: dict[str, Any],
) -> dict[str, Any]:
    if local_shell.get("status") != "ok":
        status = "blocked"
        reason = "local shell execution is not proven"
    elif agent.get("status") == "ok":
        status = "usable_with_explicit_readback"
        reason = "agent smoke passed; external actions still require per-action evidence"
    elif agent.get("status") == "unverified":
        status = "unverified"
        reason = "agent smoke was not run"
    else:
        status = "blocked"
        reason = "agent smoke failed"
    return {
        "status": status,
        "reason": reason,
        "rule": "Never claim sent/submitted/finalized unless the action-specific verification path is available and has read back evidence.",
    }


def overall_status(signals: dict[str, Any]) -> str:
    shell = signals["shell_execution"]["status"]
    agent = signals["openclaw_agent_execution"]["status"]
    gateway = signals["gateway"]["status"]
    hooks = signals["hooks_registry"]["status"]
    external = signals["external_action_verification"]["status"]
    relay_errors = any(
        item.get("native_hook_relay_error_seen") is True
        for item in [signals["gateway"], signals["hooks_registry"], signals["openclaw_agent_execution"]]
    )
    if relay_errors or shell in {"failed", "timeout", "missing"} or agent in {"failed", "timeout", "missing"}:
        return "degraded"
    if agent == "unverified" or external == "unverified":
        return "unverified"
    if gateway == "ok" and hooks == "ok" and shell == "ok" and agent == "ok":
        return "ok"
    return "degraded"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    gateway = gateway_probe()
    hooks = hooks_check()
    shell = shell_execution()
    codex = codex_cli()
    agent = agent_smoke(args.include_agent_smoke, args.agent_timeout)
    external = external_action_verification(local_shell=shell, agent=agent)
    signals = {
        "telegram_cos_session": {
            "status": "unverified",
            "truth_note": "This terminal-local smoke cannot prove Telegram conversation liveness.",
        },
        "gateway": gateway,
        "hooks_registry": hooks,
        "shell_execution": shell,
        "codex_cli": codex,
        "codex_session_attach": {
            "status": "unverified",
            "truth_note": "CLI availability is separate from attaching to an existing Codex terminal session.",
        },
        "openclaw_agent_execution": agent,
        "external_action_verification": external,
    }
    return {
        "schema_version": 1,
        "smoke_name": "execution_plane",
        "timestamp": utc_now(),
        "status": overall_status(signals),
        "signals": signals,
        "native_hooks_policy": "native hooks are a fast path, not the source of execution truth",
        "remediation_hint": (
            "If gateway/hooks are green but shell or agent execution fails, treat the execution plane as degraded. "
            "Use a fresh host terminal or durable runner lane; do not claim machine work from chat liveness."
        ),
        "external_effect": {
            "occurred": False,
            "details": "Local diagnostics only; optional agent smoke sends an internal OpenClaw smoke message, not an external action.",
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    assert_under_observability(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run execution-plane smoke and write dashboard-ready JSON.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-agent-smoke", action="store_true")
    parser.add_argument("--agent-timeout", type=int, default=180)
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
