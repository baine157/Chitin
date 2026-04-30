#!/usr/bin/env python3
"""
Guarded Packet Runner (v0)

Processes queued packet JSON files with strict contract validation and lane-specific
execution guards.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from validate_lane_manifest import ManifestValidationError, load_and_validate_manifest
except ModuleNotFoundError:
    from scripts.cos.validate_lane_manifest import ManifestValidationError, load_and_validate_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = REPO_ROOT / "state" / "cos" / "packets"
LANE_MANIFEST_DIR = REPO_ROOT / "lane-manifests"
QUEUE_DIR = PACKET_ROOT / "queue"
DONE_DIR = PACKET_ROOT / "done"
BLOCKED_DIR = PACKET_ROOT / "blocked"
CLOSEOUT_DIR = PACKET_ROOT / "closeouts"
LOCK_PATH = PACKET_ROOT / ".runner.lock"
ONBOARDING_OPS_ROOT = Path("/home/baine/openclaw/onboarding-ops")
COMPHEALTH_PACKET_DIR = (
    ONBOARDING_OPS_ROOT / "work" / "application-packets" / "comphealth-mycomphealth"
)

PACKET_ID_PATTERN = re.compile(r"^PKT-\d{8}-[a-z0-9][a-z0-9-]*-\d{2}$")
ALLOWED_DISPOSITIONS = {"build-now", "hold", "needs-input"}
ALLOWED_DUPLICATE_POLICIES = {"skip", "update", "ask", "replace"}


@dataclass(frozen=True)
class LaneConfig:
    name: str
    max_authority_level: int
    external_commit_allowed: bool
    default_command_ids: tuple[str, ...]
    commands: dict[str, tuple[str, ...]]
    allowed_packet_types: tuple[str, ...] = ()
    manifest_path: Path | None = None


OPENCLAW_UPDATE_HEALTH_LANE = LaneConfig(
    name="openclaw_update_health",
    max_authority_level=2,
    external_commit_allowed=False,
    default_command_ids=(
        "openclaw_update_status_json",
        "openclaw_update_dry_run_json",
        "openclaw_gateway_health",
        "openclaw_gateway_probe",
    ),
    commands={
        "openclaw_update_status_json": ("openclaw", "update", "status", "--json"),
        "openclaw_update_dry_run_json": ("openclaw", "update", "--dry-run", "--json"),
        "openclaw_gateway_health": ("openclaw", "gateway", "health"),
        "openclaw_gateway_probe": ("openclaw", "gateway", "probe"),
        "openclaw_status_deep": ("openclaw", "status", "--deep"),
    },
)

ONBOARDING_APPLICATION_PACKET_AUDIT_LANE = LaneConfig(
    name="onboarding_application_packet_audit",
    max_authority_level=2,
    external_commit_allowed=False,
    default_command_ids=("validate_comphealth_mycomphealth_packet",),
    commands={
        "validate_comphealth_mycomphealth_packet": (
            "python3",
            str(ONBOARDING_OPS_ROOT / "scripts" / "validate-application-packet.py"),
            "--packet-dir",
            str(COMPHEALTH_PACKET_DIR),
            "--json",
        ),
    },
)

HARDCODED_LANES = {
    OPENCLAW_UPDATE_HEALTH_LANE.name: OPENCLAW_UPDATE_HEALTH_LANE,
    ONBOARDING_APPLICATION_PACKET_AUDIT_LANE.name: ONBOARDING_APPLICATION_PACKET_AUDIT_LANE,
}

RETRY_POLICY: dict[str, tuple[int, float]] = {
    # Gateway checks can flap briefly after updates/restarts. Retry within a
    # tight bounded window before declaring the packet blocked.
    "openclaw_gateway_health": (3, 2.0),
    "openclaw_gateway_probe": (3, 2.0),
}

SOFT_FAIL_COMMANDS = {
    # Discovery/probe can fail transiently even when gateway health is green.
    "openclaw_gateway_probe",
}

BLOCKED_REASON_TAXONOMY = {
    "missing_input": "Required local input artifact is missing or empty.",
    "stale_artifact": "Local artifact appears stale or cannot prove current state.",
    "schema_mismatch": "Packet, manifest, or lane artifact does not match the required schema.",
    "validator_failed": "Lane validator failed without a more specific blocked reason.",
    "approval_gate": "Human approval or operator action is required before continuing.",
    "credential_mfa_gate": "Credential, MFA, captcha, cookie, or authenticated-session gate blocks progress.",
    "final_action_gate": "Final action is prohibited or requires explicit approval.",
}


def lane_from_manifest(path: Path) -> LaneConfig:
    manifest = load_and_validate_manifest(path)
    validator = manifest["commands"]["validator"]
    live_run = manifest["live_run"]

    return LaneConfig(
        name=manifest["lane_id"],
        max_authority_level=live_run["authority_max_level"],
        external_commit_allowed=live_run["external_commit_allowed"],
        default_command_ids=(validator["id"],),
        commands={validator["id"]: validator["argv"]},
        allowed_packet_types=manifest["allowed_packet_types"],
        manifest_path=path,
    )


MANIFEST_LOAD_ERRORS: list[str] = []


def build_lanes() -> dict[str, LaneConfig]:
    lanes = dict(HARDCODED_LANES)
    manifest_path = LANE_MANIFEST_DIR / "onboarding_application_packet_audit.yaml"
    if manifest_path.exists():
        try:
            lanes["onboarding_application_packet_audit"] = lane_from_manifest(manifest_path)
        except ManifestValidationError as exc:
            lanes.pop("onboarding_application_packet_audit", None)
            MANIFEST_LOAD_ERRORS.append(f"{manifest_path.relative_to(REPO_ROOT)}: {exc}")
    return lanes


LANES = build_lanes()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value)


def ensure_dirs() -> None:
    for directory in (QUEUE_DIR, DONE_DIR, BLOCKED_DIR, CLOSEOUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def acquire_lock() -> Any:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("packet root must be a JSON object")
    return payload


def validate_packet_schema(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "packet_id",
        "disposition",
        "objective",
        "lane",
        "priority",
        "authority",
        "idempotency",
        "done_condition",
        "evidence_required",
    ]
    for field in required:
        if field not in packet:
            errors.append(f"missing required field: {field}")

    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not PACKET_ID_PATTERN.match(packet_id):
        errors.append("packet_id must match PKT-YYYYMMDD-short-slug-NN")

    disposition = packet.get("disposition")
    if disposition not in ALLOWED_DISPOSITIONS:
        errors.append("disposition must be one of: build-now | hold | needs-input")

    objective = packet.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        errors.append("objective must be a non-empty string")

    lane = packet.get("lane")
    if lane not in LANES:
        errors.append(f"lane must be one of: {', '.join(sorted(LANES.keys()))}")

    priority = packet.get("priority")
    if priority not in {"P0", "P1", "P2"}:
        errors.append("priority must be one of: P0 | P1 | P2")

    authority = packet.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority must be an object")
    else:
        level = authority.get("level")
        if not isinstance(level, int) or level < 1 or level > 5:
            errors.append("authority.level must be an integer from 1 to 5")
        ext = authority.get("external_commit_allowed")
        if not isinstance(ext, bool):
            errors.append("authority.external_commit_allowed must be true or false")

    idempotency = packet.get("idempotency")
    if not isinstance(idempotency, dict):
        errors.append("idempotency must be an object")
    else:
        key = idempotency.get("key")
        if not isinstance(key, str) or not key.strip():
            errors.append("idempotency.key must be a non-empty string")
        duplicate_policy = idempotency.get("duplicate_policy")
        if duplicate_policy not in ALLOWED_DUPLICATE_POLICIES:
            errors.append(
                "idempotency.duplicate_policy must be one of: "
                + " | ".join(sorted(ALLOWED_DUPLICATE_POLICIES))
            )

    for list_field in ("done_condition", "evidence_required"):
        value = packet.get(list_field)
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            errors.append(f"{list_field} must be a non-empty list of non-empty strings")

    commands = packet.get("commands")
    if commands is not None:
        if not isinstance(commands, list) or not commands:
            errors.append("commands must be a non-empty list when provided")
        elif not all(isinstance(item, str) and item.strip() for item in commands):
            errors.append("commands entries must be non-empty strings")

    return errors


def validate_lane_guards(packet: dict[str, Any], lane: LaneConfig) -> list[str]:
    errors: list[str] = []
    if lane.manifest_path and packet["lane"] != lane.name:
        errors.append(f"packet lane {packet['lane']} does not match manifest lane_id {lane.name}")

    packet_type = packet.get("packet_type")
    if packet_type is not None:
        if not isinstance(packet_type, str) or not packet_type.strip():
            errors.append("packet_type must be a non-empty string when provided")
        elif lane.allowed_packet_types and packet_type not in lane.allowed_packet_types:
            errors.append(
                f"packet_type {packet_type} is not allowed for lane {lane.name}: "
                + ", ".join(lane.allowed_packet_types)
            )

    authority = packet["authority"]
    if authority["level"] > lane.max_authority_level:
        errors.append(
            f"authority.level {authority['level']} exceeds lane max {lane.max_authority_level}"
        )
    if authority["external_commit_allowed"] != lane.external_commit_allowed:
        errors.append(
            "authority.external_commit_allowed violates lane policy "
            f"({lane.external_commit_allowed})"
        )

    commands = packet.get("commands") or list(lane.default_command_ids)
    unknown = [item for item in commands if item not in lane.commands]
    if unknown:
        errors.append(f"unknown command ids for lane {lane.name}: {', '.join(unknown)}")

    return errors


def run_command(argv: tuple[str, ...], timeout_sec: int, max_output_chars: int) -> dict[str, Any]:
    start = time.monotonic()
    started_at = utc_now()
    try:
        proc = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        merged = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "started_at": started_at,
            "argv": list(argv),
            "exit_code": proc.returncode,
            "ok": proc.returncode == 0,
            "duration_ms": duration_ms,
            "output_excerpt": merged[:max_output_chars],
        }
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if exc.stdout:
            partial += exc.stdout
        if exc.stderr:
            partial += ("\n" if partial else "") + exc.stderr
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "started_at": started_at,
            "argv": list(argv),
            "exit_code": 124,
            "ok": False,
            "duration_ms": duration_ms,
            "output_excerpt": partial[:max_output_chars],
            "error": f"timeout after {timeout_sec}s",
        }
    except FileNotFoundError:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "started_at": started_at,
            "argv": list(argv),
            "exit_code": 127,
            "ok": False,
            "duration_ms": duration_ms,
            "output_excerpt": "",
            "error": f"command not found: {argv[0]}",
        }


def run_command_with_retry(
    command_id: str,
    argv: tuple[str, ...],
    timeout_sec: int,
    max_output_chars: int,
) -> dict[str, Any]:
    attempts, delay_sec = RETRY_POLICY.get(command_id, (1, 0.0))
    history: list[dict[str, Any]] = []
    for index in range(attempts):
        result = run_command(argv, timeout_sec=timeout_sec, max_output_chars=max_output_chars)
        history.append(result)
        if result["ok"]:
            break
        if index < attempts - 1 and delay_sec > 0:
            time.sleep(delay_sec)

    final = history[-1]
    final["attempts"] = len(history)
    if len(history) > 1:
        final["attempt_details"] = [
            {
                "attempt": idx + 1,
                "exit_code": item["exit_code"],
                "duration_ms": item["duration_ms"],
                "ok": item["ok"],
            }
            for idx, item in enumerate(history)
        ]
    return final


def parse_command_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    excerpt = result.get("output_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip().startswith("{"):
        return None
    try:
        payload = json.loads(excerpt)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def first_command_payload(command_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for result in command_results:
        payload = parse_command_payload(result)
        if payload is not None:
            return payload
    return None


def classify_issues(issues: list[Any]) -> str | None:
    issue_text = "\n".join(str(issue).lower() for issue in issues)
    if not issue_text:
        return None
    if "missing" in issue_text or "empty" in issue_text:
        return "missing_input"
    if "stale artifact" in issue_text or "freshness" in issue_text:
        return "stale_artifact"
    if "invalid json" in issue_text or "schema" in issue_text or "must contain" in issue_text or "must be" in issue_text:
        return "schema_mismatch"
    if any(term in issue_text for term in ("submit", "upload", "attest", "sign", "certify", "finalize", "final-action")):
        return "final_action_gate"
    if any(term in issue_text for term in ("credential", "password", "token", "cookie", "session", "mfa", "captcha")):
        return "credential_mfa_gate"
    return None


def closeout_readback(status: str, command_results: list[dict[str, Any]]) -> dict[str, Any]:
    payload = first_command_payload(command_results)
    failed = [item for item in command_results if item.get("ok") is not True]
    readback: dict[str, Any] = {
        "status": status,
        "blocked_reason": None,
        "blocked_reason_taxonomy": BLOCKED_REASON_TAXONOMY,
        "summary": "packet completed" if status == "DONE" else "packet did not complete",
        "evidence": {
            "command_count": len(command_results),
            "failed_command_ids": [item.get("id") for item in failed],
            "failed_command_exit_codes": [item.get("exit_code") for item in failed],
        },
    }
    if payload is not None:
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
        validator_status = payload.get("status")
        result = payload.get("result")
        readback["validator"] = {
            "status": validator_status,
            "result": result,
            "issues": issues[:5],
            "warnings": warnings[:5],
            "active_blocker_count": payload.get("active_blocker_count"),
            "checks": {
                "field_map_parses": checks.get("field_map_parses"),
                "active_blockers_present": checks.get("active_blockers_present"),
                "readback_present": checks.get("readback_present"),
                "verification_packet_present": checks.get("verification_packet_present"),
                "final_action_prohibitions_present": checks.get("final_action_prohibitions_present"),
                "required_artifacts_fresh": checks.get("required_artifacts_fresh"),
                "post_login_fields_inaccessible": checks.get("post_login_fields_inaccessible"),
                "sensitive_values_absent": checks.get("sensitive_values_absent"),
                "credentials_accessed": checks.get("credentials_accessed"),
            },
            "freshness": payload.get("freshness"),
            "external_effect": payload.get("external_effect"),
            "credentials_accessed": payload.get("credentials_accessed"),
            "final_actions_performed": payload.get("final_actions_performed"),
        }

        code = classify_issues(issues)
        if code is None and checks.get("final_action_prohibitions_present") is False:
            code = "final_action_gate"
        if code is None and checks.get("credentials_accessed") is not False:
            code = "credential_mfa_gate"
        if code is None and checks.get("post_login_fields_inaccessible") is True:
            code = "approval_gate"
        if code is None and validator_status == "BLOCKED":
            code = "validator_failed"

        if code:
            secondary_codes: list[str] = []
            if code == "approval_gate" and checks.get("post_login_fields_inaccessible") is True:
                secondary_codes.append("credential_mfa_gate")
            readback["blocked_reason"] = {
                "code": code,
                "label": BLOCKED_REASON_TAXONOMY[code],
                "detail": result or "lane validator reported blocked status",
                "secondary_codes": secondary_codes,
            }
            readback["summary"] = f"BLOCKED: {code} - {result or BLOCKED_REASON_TAXONOMY[code]}"
        return readback

    if status == "BLOCKED":
        code = "validator_failed"
        readback["blocked_reason"] = {
            "code": code,
            "label": BLOCKED_REASON_TAXONOMY[code],
            "detail": "one or more commands failed without structured validator JSON",
            "secondary_codes": [],
        }
        readback["summary"] = "BLOCKED: validator_failed - command failed without structured validator JSON"
    return readback


def write_closeout(packet: dict[str, Any], status: str, result: str, command_results: list[dict[str, Any]]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    closeout_path = CLOSEOUT_DIR / f"{sanitize_id(packet['packet_id'])}--{timestamp}.json"
    readback = closeout_readback(status, command_results)
    closeout = {
        "packet_id": packet["packet_id"],
        "status": status,
        "objective": packet["objective"],
        "result": result,
        "readback": readback,
        "blocked_reason": readback.get("blocked_reason"),
        "artifacts": {
            "changed": [str(closeout_path)],
            "inspected": [],
        },
        "authority_used": packet["authority"],
        "external_effect": {
            "occurred": False,
            "details": "none",
        },
        "verification": [
            f"validated lane guards for {packet['lane']}",
            "captured per-command exit codes and output excerpts",
        ],
        "state_updates": [
            "packet moved from queue to done/blocked register",
            "closeout recorded in state/cos/packets/closeouts",
        ],
        "residual_risk": [],
        "next_action": "none",
        "command_results": command_results,
        "generated_at": utc_now(),
    }
    if status == "PARTIAL":
        closeout["next_action"] = "monitor next scheduled packet run"
        closeout["residual_risk"] = [
            "one or more soft-check commands failed",
            "gateway discovery/probe may be degraded while core health remains available",
        ]
    elif status != "DONE":
        closeout["next_action"] = "review blocked command results and adjust packet"
        closeout["residual_risk"] = [
            readback.get("summary", "lane did not fully complete"),
            "manual decision or packet revision required",
        ]
    with closeout_path.open("w", encoding="utf-8") as handle:
        json.dump(closeout, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return closeout_path


def guess_packet_id(packet_path: Path, packet: dict[str, Any] | None = None) -> str:
    if isinstance(packet, dict):
        packet_id = packet.get("packet_id")
        if isinstance(packet_id, str) and packet_id.strip():
            return packet_id.strip()
    return f"INVALID-{sanitize_id(packet_path.stem)}"


def write_invalid_packet_closeout(
    *,
    packet_path: Path,
    packet_id: str,
    reason: str,
    errors: list[str],
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    closeout_path = CLOSEOUT_DIR / f"{sanitize_id(packet_id)}--{timestamp}.json"
    closeout = {
        "packet_id": packet_id,
        "status": "BLOCKED",
        "objective": "reject invalid packet before execution",
        "result": reason,
        "artifacts": {
            "changed": [str(closeout_path)],
            "inspected": [str(packet_path)],
        },
        "authority_used": {
            "level": 1,
            "source": "safe default",
            "external_commit_allowed": False,
        },
        "external_effect": {
            "occurred": False,
            "details": "none",
        },
        "verification": [
            "packet rejected before lane execution",
            *errors,
        ],
        "state_updates": [
            "packet moved from queue to blocked register",
            "closeout recorded in state/cos/packets/closeouts",
        ],
        "residual_risk": [
            "packet producer emitted invalid schema/readable payload",
        ],
        "next_action": "fix packet and re-queue with a new packet id",
        "command_results": [
            {
                "id": "packet_validation",
                "ok": False,
                "exit_code": 2,
                "errors": errors,
            }
        ],
        "generated_at": utc_now(),
    }
    with closeout_path.open("w", encoding="utf-8") as handle:
        json.dump(closeout, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return closeout_path


def move_packet(packet_path: Path, packet_id: str, status: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    target_dir = DONE_DIR if status in {"DONE", "PARTIAL"} else BLOCKED_DIR
    target = target_dir / f"{sanitize_id(packet_id)}--{stamp}.json"
    try:
        shutil.move(str(packet_path), str(target))
    except FileNotFoundError:
        # If another process moved it first (rare race), return the intended
        # target path and let lock discipline prevent recurring collisions.
        return target
    return target


def process_packet(packet_path: Path, *, dry_run: bool, timeout_sec: int, max_output_chars: int) -> int:
    try:
        packet = read_json(packet_path)
    except Exception as exc:
        reason = f"failed to read packet JSON: {exc}"
        print(f"[invalid] {packet_path.name}: {reason}")
        if dry_run:
            return 2
        packet_id = guess_packet_id(packet_path)
        closeout_path = write_invalid_packet_closeout(
            packet_path=packet_path,
            packet_id=packet_id,
            reason=reason,
            errors=[reason],
        )
        moved_to = move_packet(packet_path, packet_id, "BLOCKED")
        print(f"[invalid] closeout={closeout_path} moved_packet={moved_to}")
        return 2

    schema_errors = validate_packet_schema(packet)
    if schema_errors:
        for error in schema_errors:
            print(f"[invalid] {packet_path.name}: {error}")
        if not dry_run:
            packet_id = guess_packet_id(packet_path, packet)
            closeout_path = write_invalid_packet_closeout(
                packet_path=packet_path,
                packet_id=packet_id,
                reason="packet schema validation failed",
                errors=schema_errors,
            )
            moved_to = move_packet(packet_path, packet_id, "BLOCKED")
            print(f"[invalid] closeout={closeout_path} moved_packet={moved_to}")
        return 2

    lane = LANES[packet["lane"]]
    guard_errors = validate_lane_guards(packet, lane)
    if guard_errors:
        for error in guard_errors:
            print(f"[blocked] {packet['packet_id']}: {error}")
        if dry_run:
            return 2
        closeout_path = write_closeout(
            packet,
            status="BLOCKED",
            result="packet failed lane guard enforcement",
            command_results=[],
        )
        moved_to = move_packet(packet_path, packet["packet_id"], "BLOCKED")
        print(f"[blocked] closeout={closeout_path} moved_packet={moved_to}")
        return 3

    commands = packet.get("commands") or list(lane.default_command_ids)
    print(f"[packet] {packet['packet_id']} lane={packet['lane']} disposition={packet['disposition']}")
    if lane.manifest_path:
        print(f"[lane-source] manifest={lane.manifest_path.relative_to(REPO_ROOT)}")
    else:
        print("[lane-source] hardcoded")
    print(f"[commands] {', '.join(commands)}")

    if packet["disposition"] != "build-now":
        if dry_run:
            print("[dry-run] non build-now packet validated; execution skipped")
            return 0
        closeout_path = write_closeout(
            packet,
            status="NEEDS DECISION",
            result=f"execution skipped because disposition={packet['disposition']}",
            command_results=[],
        )
        moved_to = move_packet(packet_path, packet["packet_id"], "BLOCKED")
        print(f"[needs-decision] closeout={closeout_path} moved_packet={moved_to}")
        return 4

    if dry_run:
        print("[dry-run] validation passed; commands not executed")
        return 0

    command_results: list[dict[str, Any]] = []
    hard_failures = 0
    soft_failures = 0
    for command_id in commands:
        argv = lane.commands[command_id]
        result = run_command_with_retry(
            command_id,
            argv,
            timeout_sec=timeout_sec,
            max_output_chars=max_output_chars,
        )
        result["id"] = command_id
        command_results.append(result)
        status = "ok" if result["ok"] else "fail"
        attempts = result.get("attempts", 1)
        print(
            "[run] "
            f"{command_id} -> {status} exit={result['exit_code']} duration_ms={result['duration_ms']} attempts={attempts}"
        )
        if not result["ok"]:
            if command_id in SOFT_FAIL_COMMANDS:
                soft_failures += 1
            else:
                hard_failures += 1

    if hard_failures == 0 and soft_failures == 0:
        packet_status = "DONE"
    elif hard_failures == 0 and soft_failures > 0:
        packet_status = "PARTIAL"
    else:
        packet_status = "BLOCKED"

    result_text = (
        "lane completed with "
        f"{len(commands)} commands, hard_failures={hard_failures}, soft_failures={soft_failures}"
    )
    closeout_path = write_closeout(packet, status=packet_status, result=result_text, command_results=command_results)
    moved_to = move_packet(packet_path, packet["packet_id"], packet_status)
    print(f"[closeout] status={packet_status} closeout={closeout_path}")
    print(f"[archive] packet={moved_to}")
    return 0 if hard_failures == 0 else 5


def collect_packets(explicit_path: str | None) -> list[Path]:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        return [path]
    return sorted(path for path in QUEUE_DIR.glob("*.json") if path.is_file())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run guarded OpenClaw packets from queue.")
    parser.add_argument(
        "--packet",
        help="Optional explicit packet path. Defaults to queued packets in state/cos/packets/queue.",
    )
    parser.add_argument("--once", action="store_true", help="Process at most one queued packet.")
    parser.add_argument("--dry-run", action="store_true", help="Validate packet(s) without executing commands.")
    parser.add_argument("--timeout-sec", type=int, default=90, help="Per-command timeout seconds.")
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=4000,
        help="Max combined stdout/stderr chars stored per command.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_dirs()
    if MANIFEST_LOAD_ERRORS:
        for error in MANIFEST_LOAD_ERRORS:
            print(f"[manifest-invalid] {error}")
        return 2
    lock_handle = acquire_lock()
    if lock_handle is None:
        print("[busy] another guarded packet runner instance is already active")
        return 0

    packets = collect_packets(args.packet)
    if not packets:
        lock_handle.close()
        print("[idle] no packet files found")
        return 0

    if args.once:
        packets = packets[:1]

    final_code = 0
    try:
        for packet_path in packets:
            rc = process_packet(
                packet_path,
                dry_run=args.dry_run,
                timeout_sec=args.timeout_sec,
                max_output_chars=args.max_output_chars,
            )
            if rc != 0:
                final_code = rc
                if args.once:
                    break
    finally:
        lock_handle.close()
    return final_code


if __name__ == "__main__":
    raise SystemExit(main())
