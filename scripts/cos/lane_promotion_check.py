#!/usr/bin/env python3
"""Machine-check lane promotion readiness for bounded portal-adjacent work."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from validate_lane_manifest import ManifestValidationError, load_and_validate_manifest
except ModuleNotFoundError:
    from scripts.cos.validate_lane_manifest import ManifestValidationError, load_and_validate_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
ONBOARDING_ROOT = Path("/home/baine/openclaw/onboarding-ops")
MANIFEST_PATH = REPO_ROOT / "lane-manifests" / "onboarding_application_packet_audit.yaml"
DASHBOARD_PATH = REPO_ROOT / "state" / "observability" / "dashboard.json"
CLOSEOUT_DIR = REPO_ROOT / "state" / "cos" / "packets" / "closeouts"
FIXTURE_ROOT = ONBOARDING_ROOT / "tests" / "fixtures" / "application-packets"
VALIDATOR_PATH = ONBOARDING_ROOT / "scripts" / "validate-application-packet.py"
NATIVE_HOOK_SMOKE_PATH = REPO_ROOT / "state" / "observability" / "live-session-native-hook-smoke.json"
LOCAL_WRITE_CANARY_PATH = REPO_ROOT / "state" / "observability" / "native-hook-write-canary.json"
TARGET_TRUST_LEVEL = "bounded_portal_adjacent_work"
SUPPORTED_LANES = {"onboarding_application_packet_audit"}
REQUIRED_FIXTURES = {
    "partial-ready": "PARTIAL",
    "blocked-approval-gate": "BLOCKED",
    "blocked-missing-input": "BLOCKED",
    "blocked-schema-mismatch": "BLOCKED",
    "blocked-stale-artifact": "BLOCKED",
}
FRESH_ENOUGH_HOURS = 24


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc.msg}"
    except OSError as exc:
        return None, f"read failed: {exc}"
    if not isinstance(payload, dict):
        return None, "json root is not an object"
    return payload, None


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness_state(path: Path) -> dict[str, Any]:
    payload, warning = read_json(path)
    if payload is None:
        return {
            "status": "unverified",
            "freshness": "missing",
            "source_file": rel(path),
            "warning": warning or "missing",
        }
    timestamp = parse_timestamp(payload.get("timestamp"))
    if timestamp is None:
        return {
            "status": "unverified",
            "freshness": "invalid_timestamp",
            "source_file": rel(path),
            "observed_status": payload.get("status"),
        }
    age_hours = round((datetime.now(timezone.utc) - timestamp).total_seconds() / 3600, 3)
    freshness = "fresh" if age_hours <= FRESH_ENOUGH_HOURS else "stale"
    status = payload.get("status") if freshness == "fresh" else "unverified"
    return {
        "status": status,
        "freshness": freshness,
        "age_hours": age_hours,
        "fresh_enough_hours": FRESH_ENOUGH_HOURS,
        "source_file": rel(path),
        "observed_status": payload.get("status"),
        "execution_origin": payload.get("execution_origin"),
        "telegram_session_native_hook": payload.get("telegram_session_native_hook"),
        "gateway_health": payload.get("gateway_health"),
    }


def latest_lane_closeout(lane_id: str) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for path in sorted(CLOSEOUT_DIR.glob("*.json")):
        payload, warning = read_json(path)
        if payload is None:
            continue
        if lane_id not in json.dumps(payload, sort_keys=True):
            continue
        generated = str(payload.get("generated_at") or "")
        candidates.append((generated, path, payload))
    if not candidates:
        return None, None, "no closeout found for lane"
    _, path, payload = sorted(candidates, key=lambda item: (item[0], str(item[1])), reverse=True)[0]
    return payload, path, None


def load_validator_module() -> Any:
    spec = importlib.util.spec_from_file_location("validate_application_packet", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load validator module from {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_guarded_runner_module() -> Any:
    runner_path = REPO_ROOT / "scripts" / "cos" / "guarded_packet_runner.py"
    script_dir = str(runner_path.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("guarded_packet_runner_for_promotion", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load guarded runner module from {runner_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(name: str, ok: bool, evidence: list[str], detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "evidence": evidence}


def run_checks(lane_id: str) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    evidence: list[str] = []
    residual_risks: list[str] = []

    if lane_id not in SUPPORTED_LANES:
        return {
            "lane_id": lane_id,
            "promotion_status": "not_promotable",
            "target_trust_level": TARGET_TRUST_LEVEL,
            "checks": {
                "supported_lane": check("supported_lane", False, [], "unsupported lane")
            },
            "evidence": [],
            "residual_risks": ["only onboarding_application_packet_audit is supported in v0"],
        }

    try:
        manifest = load_and_validate_manifest(MANIFEST_PATH)
        manifest_ok = manifest["lane_id"] == lane_id
        manifest_detail = "manifest valid" if manifest_ok else "manifest lane_id mismatch"
    except ManifestValidationError as exc:
        manifest = None
        manifest_ok = False
        manifest_detail = str(exc)
    checks["manifest_validates"] = check(
        "manifest_validates", manifest_ok, [rel(MANIFEST_PATH)], manifest_detail
    )
    evidence.append(rel(MANIFEST_PATH))

    try:
        runner = load_guarded_runner_module()
        lane = runner.LANES.get(lane_id)
        manifest_resolved = lane is not None and lane.manifest_path == MANIFEST_PATH
        detail = f"lane source={rel(lane.manifest_path) if lane and lane.manifest_path else 'hardcoded_or_missing'}"
    except Exception as exc:  # noqa: BLE001 - report import/runtime failure as a failed check.
        manifest_resolved = False
        detail = f"runner import/resolution failed: {exc}"
    checks["runner_resolves_manifest"] = check(
        "runner_resolves_manifest", manifest_resolved, ["scripts/cos/guarded_packet_runner.py"], detail
    )

    try:
        validator = load_validator_module()
        validator_result = validator.validate_packet(ONBOARDING_ROOT / "work" / "application-packets" / "comphealth-mycomphealth")
        validator_json_ok = isinstance(validator_result, dict) and "status" in validator_result and "checks" in validator_result
        detail = f"status={validator_result.get('status') if isinstance(validator_result, dict) else None}"
    except Exception as exc:  # noqa: BLE001
        validator_result = {}
        validator_json_ok = False
        detail = f"validator failed: {exc}"
    checks["validator_structured_json"] = check(
        "validator_structured_json", validator_json_ok, [rel(VALIDATOR_PATH)], detail
    )
    evidence.append(rel(VALIDATOR_PATH))

    fixture_results: dict[str, Any] = {}
    fixture_ok = True
    stale_proven = False
    try:
        validator = load_validator_module()
        for fixture_name, expected_status in REQUIRED_FIXTURES.items():
            fixture = FIXTURE_ROOT / fixture_name
            if not fixture.is_dir():
                fixture_ok = False
                fixture_results[fixture_name] = {"ok": False, "detail": "missing fixture"}
                continue
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / fixture_name
                shutil.copytree(fixture, root)
                if fixture_name == "blocked-stale-artifact":
                    stale_path = root / "readback.md"
                    stale_path.touch(exist_ok=True)
                    stale_path.chmod(0o644)
                    import os

                    os.utime(stale_path, (0, 0))
                    result = validator.validate_packet(root, freshness_max_age_days=1)
                else:
                    result = validator.validate_packet(root)
            issues = result.get("issues", []) if isinstance(result, dict) else []
            if fixture_name == "blocked-stale-artifact":
                stale_proven = any(str(issue).startswith("stale artifact:") for issue in issues)
            ok = isinstance(result, dict) and result.get("status") == expected_status
            fixture_ok = fixture_ok and ok
            fixture_results[fixture_name] = {
                "ok": ok,
                "expected_status": expected_status,
                "observed_status": result.get("status") if isinstance(result, dict) else None,
                "issues": issues[:3] if isinstance(issues, list) else [],
            }
    except Exception as exc:  # noqa: BLE001
        fixture_ok = False
        fixture_results["error"] = str(exc)
    checks["fixture_corpus"] = check(
        "fixture_corpus",
        fixture_ok and stale_proven,
        [str(FIXTURE_ROOT)],
        json.dumps(fixture_results, sort_keys=True),
    )
    evidence.append(str(FIXTURE_ROOT))

    closeout, closeout_path, closeout_warning = latest_lane_closeout(lane_id)
    closeout_evidence = [rel(closeout_path)] if closeout_path else []
    checks["closeout_top_level_blocked_reason"] = check(
        "closeout_top_level_blocked_reason",
        bool(closeout and isinstance(closeout.get("blocked_reason"), dict) and closeout["blocked_reason"].get("code")),
        closeout_evidence,
        closeout_warning or "top-level blocked_reason present",
    )
    checks["closeout_readback_freshness"] = check(
        "closeout_readback_freshness",
        bool(
            closeout
            and isinstance(closeout.get("readback"), dict)
            and isinstance(closeout["readback"].get("validator"), dict)
            and isinstance(closeout["readback"]["validator"].get("freshness"), dict)
        ),
        closeout_evidence,
        closeout_warning or "readback.validator.freshness present",
    )
    if closeout_path:
        evidence.append(rel(closeout_path))

    validator_from_closeout = {}
    if closeout:
        readback = closeout.get("readback")
        if isinstance(readback, dict):
            validator_from_closeout = readback.get("validator") if isinstance(readback.get("validator"), dict) else {}
    external_effect_ok = bool(closeout and closeout.get("external_effect", {}).get("occurred") is False)
    credentials_ok = validator_from_closeout.get("credentials_accessed") is False
    final_actions_ok = validator_from_closeout.get("final_actions_performed") is False
    checks["external_effect_false"] = check("external_effect_false", external_effect_ok, closeout_evidence)
    checks["credentials_not_accessed"] = check("credentials_not_accessed", credentials_ok, closeout_evidence)
    checks["final_actions_not_performed"] = check("final_actions_not_performed", final_actions_ok, closeout_evidence)

    dashboard, dashboard_warning = read_json(DASHBOARD_PATH)
    dashboard_ok = False
    dashboard_detail = dashboard_warning or ""
    if dashboard:
        latest = (dashboard.get("packet_execution", {}).get("recent") or [{}])[0]
        dashboard_ok = latest.get("lane") == lane_id and latest.get("external_effect", {}).get("occurred") is False
        dashboard_detail = f"latest_packet_id={latest.get('packet_id')} status={latest.get('status')} blocker={latest.get('blocker')}"
    checks["dashboard_latest_lane_truth"] = check(
        "dashboard_latest_lane_truth", dashboard_ok, [rel(DASHBOARD_PATH)], dashboard_detail
    )
    evidence.append(rel(DASHBOARD_PATH))

    write_canary = freshness_state(LOCAL_WRITE_CANARY_PATH)
    smoke = freshness_state(NATIVE_HOOK_SMOKE_PATH)
    canary_ok = write_canary["freshness"] in {"fresh", "stale", "missing", "invalid_timestamp"} and smoke[
        "freshness"
    ] in {"fresh", "stale", "missing", "invalid_timestamp"}
    checks["canary_smoke_state_explicit"] = check(
        "canary_smoke_state_explicit",
        canary_ok,
        [rel(LOCAL_WRITE_CANARY_PATH), rel(NATIVE_HOOK_SMOKE_PATH)],
        f"write_canary={write_canary['status']} freshness={write_canary['freshness']}; live_smoke={smoke['status']} freshness={smoke['freshness']}",
    )
    evidence.extend([rel(LOCAL_WRITE_CANARY_PATH), rel(NATIVE_HOOK_SMOKE_PATH)])

    execution_substrate = dashboard.get("system_trust", {}).get("execution_substrate", {}) if dashboard else {}
    gateway_role = execution_substrate.get("gateway_health", {}).get("role")
    telegram_status = execution_substrate.get("telegram_session_native_hook", {}).get("status") or smoke.get(
        "telegram_session_native_hook", {}
    ).get("status")
    hook_not_inferred = gateway_role == "necessary_but_insufficient" and telegram_status in {"ok", "unverified"}
    checks["telegram_hook_not_inferred_from_gateway"] = check(
        "telegram_hook_not_inferred_from_gateway",
        hook_not_inferred,
        [rel(DASHBOARD_PATH), rel(NATIVE_HOOK_SMOKE_PATH)],
        f"gateway_role={gateway_role}; telegram_session_native_hook={telegram_status}",
    )

    failed = [name for name, item in checks.items() if not item["ok"]]
    if failed:
        residual_risks.append("failed promotion checks: " + ", ".join(failed))
    if smoke["status"] == "unverified":
        residual_risks.append("Telegram live-session native hook is explicitly unverified, not inferred from gateway health.")
    elif smoke["freshness"] != "fresh":
        residual_risks.append("Telegram live-session native hook smoke is not fresh.")

    return {
        "lane_id": lane_id,
        "promotion_status": "promotable" if not failed else "not_promotable",
        "target_trust_level": TARGET_TRUST_LEVEL,
        "checks": checks,
        "evidence": sorted(set(evidence)),
        "residual_risks": residual_risks,
    }


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check lane promotion readiness.")
    parser.add_argument("--lane", required=True, help="Lane id to check.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    result = run_checks(args.lane)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"lane={result['lane_id']} promotion_status={result['promotion_status']}")
        for name, item in result["checks"].items():
            marker = "ok" if item["ok"] else "fail"
            print(f"- {marker}: {name} {item.get('detail', '')}")
    return 0 if result["promotion_status"] == "promotable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
