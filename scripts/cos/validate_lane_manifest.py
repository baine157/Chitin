#!/usr/bin/env python3
"""Validate guarded-runner lane manifests.

The validator is intentionally deterministic and local-file-only. It validates
manifest metadata and safety invariants before the guarded runner trusts a lane.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ONBOARDING_WORKSPACE = "/home/baine/openclaw/onboarding-ops"
ALLOWED_STATUSES = {"DONE", "PARTIAL", "BLOCKED", "NEEDS DECISION"}
REQUIRED_FORBIDDEN_ACTIONS = {"submit", "upload", "attest", "sign", "certify", "finalize"}
UNSAFE_ARG_PATTERNS = (
    re.compile(r"(^|/)(bw|bitwarden)$", re.IGNORECASE),
    re.compile(r"(^|/)(xurl|gog)$", re.IGNORECASE),
    re.compile(r"browser.*login", re.IGNORECASE),
    re.compile(r"\b(login|credential|credentials|password|passwd|token|cookie|session|mfa|captcha)\b", re.IGNORECASE),
    re.compile(r"\b(submit|upload|send|attest|sign|certify|finalize)\b", re.IGNORECASE),
)


class ManifestValidationError(ValueError):
    """Raised when a lane manifest violates schema or safety invariants."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestValidationError(f"{field} must be an object")
    return value


def require_string(value: Any, field: str, *, absolute_path: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{field} must be a non-empty string")
    if absolute_path and not value.startswith("/"):
        raise ManifestValidationError(f"{field} must be an absolute path string")
    return value


def require_string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestValidationError(f"{field} must be a non-empty list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ManifestValidationError(f"{field}[{index}] must be a non-empty string")
        result.append(item)
    return tuple(result)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ManifestValidationError("PyYAML is required to load lane manifests") from exc
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestValidationError(f"manifest file not found: {rel(path)}") from exc
    except OSError as exc:
        raise ManifestValidationError(f"failed to read manifest {rel(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestValidationError("manifest root must be an object")
    return payload


def validator_argv_is_safe(argv: tuple[str, ...]) -> bool:
    for arg in argv:
        for pattern in UNSAFE_ARG_PATTERNS:
            if pattern.search(arg):
                return False
    return True


def validate_manifest_payload(payload: dict[str, Any], *, source: Path | None = None) -> dict[str, Any]:
    lane_id = require_string(payload.get("lane_id"), "lane_id")
    workspace = require_string(payload.get("workspace"), "workspace", absolute_path=True)
    allowed_packet_types = require_string_list(payload.get("allowed_packet_types"), "allowed_packet_types")

    commands = require_mapping(payload.get("commands"), "commands")
    validator = require_mapping(commands.get("validator"), "commands.validator")
    validator_id = require_string(validator.get("id"), "commands.validator.id")
    validator_argv = require_string_list(validator.get("argv"), "commands.validator.argv")

    live_run = require_mapping(payload.get("live_run"), "live_run")
    if not isinstance(live_run.get("allowed"), bool):
        raise ManifestValidationError("live_run.allowed must be a boolean")
    if live_run.get("allowed") is not True:
        raise ManifestValidationError("live_run.allowed must be true for guarded runner execution")
    authority_max_level = live_run.get("authority_max_level")
    if not isinstance(authority_max_level, int):
        raise ManifestValidationError("live_run.authority_max_level must be an integer")
    if authority_max_level > 2:
        raise ManifestValidationError("live_run.authority_max_level must be <= 2 for manifest-backed lanes")
    if authority_max_level < 1:
        raise ManifestValidationError("live_run.authority_max_level must be >= 1")
    external_commit_allowed = live_run.get("external_commit_allowed")
    if external_commit_allowed is not False:
        raise ManifestValidationError("live_run.external_commit_allowed must be false")

    outputs = require_mapping(payload.get("outputs"), "outputs")
    require_string(outputs.get("closeout_dir"), "outputs.closeout_dir")

    forbidden_actions = set(require_string_list(payload.get("forbidden_actions"), "forbidden_actions"))
    human_gates = require_string_list(payload.get("human_gates"), "human_gates")
    canary = require_mapping(payload.get("canary"), "canary")
    canary_id = require_string(canary.get("id"), "canary.id")
    canary_command = require_string_list(canary.get("command"), "canary.command")
    expected_statuses = require_string_list(canary.get("expected_statuses"), "canary.expected_statuses")
    invalid_statuses = [status for status in expected_statuses if status not in ALLOWED_STATUSES]
    if invalid_statuses:
        raise ManifestValidationError(
            "canary.expected_statuses contains unsupported status: " + ", ".join(invalid_statuses)
        )

    missing_actions = sorted(REQUIRED_FORBIDDEN_ACTIONS - forbidden_actions)
    if missing_actions:
        raise ManifestValidationError(
            "forbidden_actions missing required final-action prohibition: " + ", ".join(missing_actions)
        )
    if not validator_argv_is_safe(validator_argv):
        raise ManifestValidationError("commands.validator.argv contains unsafe command or action")
    if not validator_argv_is_safe(canary_command):
        raise ManifestValidationError("canary.command contains unsafe command or action")

    if lane_id == "onboarding_application_packet_audit" and workspace != ONBOARDING_WORKSPACE:
        raise ManifestValidationError(f"workspace must be {ONBOARDING_WORKSPACE}")

    return {
        "lane_id": lane_id,
        "workspace": workspace,
        "allowed_packet_types": allowed_packet_types,
        "commands": {
            "validator": {
                "id": validator_id,
                "argv": validator_argv,
            }
        },
        "live_run": {
            "allowed": live_run["allowed"],
            "authority_max_level": authority_max_level,
            "external_commit_allowed": external_commit_allowed,
        },
        "outputs": {
            "closeout_dir": outputs["closeout_dir"],
        },
        "forbidden_actions": tuple(forbidden_actions),
        "human_gates": human_gates,
        "canary": {
            "id": canary_id,
            "command": canary_command,
            "expected_statuses": expected_statuses,
        },
        "source": rel(source) if source else None,
    }


def load_and_validate_manifest(path: Path) -> dict[str, Any]:
    return validate_manifest_payload(load_yaml(path), source=path)


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a guarded-runner lane manifest.")
    parser.add_argument("manifest", help="Path to lane manifest YAML.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable validation result.")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    path = Path(args.manifest)
    try:
        manifest = load_and_validate_manifest(path)
    except ManifestValidationError as exc:
        payload = {"status": "invalid", "manifest": rel(path), "error": str(exc)}
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"[invalid] {payload['manifest']}: {payload['error']}")
        return 2

    payload = {
        "status": "ok",
        "manifest": rel(path),
        "lane_id": manifest["lane_id"],
        "validator_id": manifest["commands"]["validator"]["id"],
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"[ok] {payload['manifest']} lane={payload['lane_id']} validator={payload['validator_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
