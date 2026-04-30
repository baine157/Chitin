#!/usr/bin/env python3
"""Collect local Chief-of-Staff observability state into dashboard JSON."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_COS = REPO_ROOT / "state" / "cos"
PACKETS = STATE_COS / "packets"
DEFAULT_OUTPUT = REPO_ROOT / "state" / "observability" / "dashboard.json"
NATIVE_HOOK_CANARY_PATH = REPO_ROOT / "state" / "observability" / "native-hook-write-canary.json"
LIVE_SESSION_SMOKE_PATH = REPO_ROOT / "state" / "observability" / "live-session-native-hook-smoke.json"
CANARY_STALE_HOURS = 24
RELAY_ERROR_PATTERN = re.compile(
    r"native hook relay not found|Native hook relay unavailable|relay unavailable",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceRead:
    path: Path
    text: str | None
    warning: str | None = None


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> SourceRead:
    try:
        return SourceRead(path=path, text=path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return SourceRead(path=path, text=None, warning="missing")
    except UnicodeDecodeError:
        return SourceRead(path=path, text=None, warning="not valid utf-8")
    except OSError as exc:
        return SourceRead(path=path, text=None, warning=f"read failed: {exc}")


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc.msg}"
    except UnicodeDecodeError:
        return None, "not valid utf-8"
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


def source_status(reads: list[SourceRead], json_warnings: dict[Path, str | None]) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for read in reads:
        sources[rel(read.path)] = "ok" if read.warning is None else read.warning
    for path, warning in json_warnings.items():
        sources[rel(path)] = "ok" if warning is None else warning
    return sources


def last_checked(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"^Last checked:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def markdown_tables(text: str | None) -> list[list[dict[str, str]]]:
    if not text:
        return []
    tables: list[list[dict[str, str]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not (line.startswith("|") and line.endswith("|")):
            index += 1
            continue
        if index + 1 >= len(lines) or not re.fullmatch(r"\|[\s:\-|\t]+\|", lines[index + 1].strip()):
            index += 1
            continue

        headers = [cell.strip() for cell in line.strip("|").split("|")]
        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines):
            row_line = lines[index].strip()
            if not (row_line.startswith("|") and row_line.endswith("|")):
                break
            cells = [cell.strip() for cell in row_line.strip("|").split("|")]
            rows.append({headers[pos]: cells[pos] if pos < len(cells) else "" for pos in range(len(headers))})
            index += 1
        tables.append(rows)
    return tables


def first_table(text: str | None) -> list[dict[str, str]]:
    tables = markdown_tables(text)
    return tables[0] if tables else []


def parse_priority_blocks(text: str | None, source: Path) -> list[dict[str, Any]]:
    if not text:
        return []
    items: list[dict[str, Any]] = []
    current_priority = None
    current: dict[str, str] | None = None

    def finish() -> None:
        if current and current.get("id"):
            items.append(
                {
                    "id": current.get("id"),
                    "priority": current_priority,
                    "status": current.get("status"),
                    "owner": current.get("owner"),
                    "source": current.get("source"),
                    "last_checked": current.get("last_checked"),
                    "notes": current.get("notes"),
                    "source_file": rel(source),
                }
            )

    for raw in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", raw)
        if heading:
            finish()
            current = None
            current_priority = heading.group(1)
            continue

        item = re.match(r"^-\s+id:\s*(.+?)\s*$", raw)
        if item:
            finish()
            current = {"id": item.group(1)}
            continue

        field = re.match(r"^\s+([a-z_]+):\s*(.*?)\s*$", raw)
        if field and current is not None:
            current[field.group(1)] = field.group(2)

    finish()
    return items


def no_pending(text: str | None) -> bool:
    return bool(text and re.search(r"^No .* recorded", text, flags=re.IGNORECASE | re.MULTILINE))


def safe_json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def packet_summary(path: Path) -> dict[str, Any]:
    payload, warning = read_json(path)
    if payload is None:
        return {"id": path.stem, "source_file": rel(path), "warning": warning}
    archive_status = None
    if path.parent.name == "blocked":
        archive_status = "BLOCKED"
    elif path.parent.name == "done":
        archive_status = "DONE"
    return {
        "id": payload.get("packet_id", path.stem),
        "status": payload.get("status") or archive_status or payload.get("disposition"),
        "priority": payload.get("priority"),
        "lane": payload.get("lane"),
        "owner": payload.get("owner"),
        "objective": payload.get("objective"),
        "source": payload.get("source"),
        "authority": payload.get("authority") or payload.get("authority_used"),
        "proof": proof_summary(payload),
        "source_file": rel(path),
    }


def proof_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    command_results = payload.get("command_results")
    if isinstance(command_results, list):
        total = len(command_results)
        ok_count = sum(1 for item in command_results if isinstance(item, dict) and item.get("ok") is True)
        return {
            "command_count": total,
            "ok_count": ok_count,
            "failed_count": total - ok_count,
            "verification": payload.get("verification", []),
        }
    evidence_required = payload.get("evidence_required")
    if isinstance(evidence_required, list):
        return {"evidence_required": evidence_required}
    return None


def command_ids(payload: dict[str, Any]) -> list[str]:
    commands = payload.get("command_results")
    if not isinstance(commands, list):
        return []
    return [str(item.get("id")) for item in commands if isinstance(item, dict) and item.get("id")]


def command_exit_codes(payload: dict[str, Any]) -> list[int | None]:
    commands = payload.get("command_results")
    if not isinstance(commands, list):
        return []
    return [item.get("exit_code") for item in commands if isinstance(item, dict)]


def lane_from_closeout(payload: dict[str, Any]) -> str | None:
    lane = payload.get("lane")
    if isinstance(lane, str) and lane.strip():
        return lane
    verification = payload.get("verification")
    if isinstance(verification, list):
        for item in verification:
            match = re.search(r"validated lane guards for ([a-zA-Z0-9_-]+)", str(item))
            if match:
                return match.group(1)
    ids = set(command_ids(payload))
    if "validate_comphealth_mycomphealth_packet" in ids:
        return "onboarding_application_packet_audit"
    if any(item.startswith("openclaw_") for item in ids):
        return "openclaw_update_health"
    return None


def parsed_command_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    commands = payload.get("command_results")
    if not isinstance(commands, list):
        return parsed
    for item in commands:
        if not isinstance(item, dict):
            continue
        excerpt = item.get("output_excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip().startswith("{"):
            continue
        try:
            value = json.loads(excerpt)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def concise_blocker(payload: dict[str, Any]) -> str:
    blocked_reason = payload.get("blocked_reason")
    if isinstance(blocked_reason, dict):
        code = blocked_reason.get("code")
        detail = blocked_reason.get("detail")
        if code and detail:
            return f"{code}: {detail}"
        if code:
            return str(code)
    parsed = parsed_command_payloads(payload)
    for item in parsed:
        result = item.get("result")
        if isinstance(result, str) and result.strip():
            status = item.get("status")
            return f"{status}: {result}" if status else result
        issues = item.get("issues")
        if isinstance(issues, list) and issues:
            return "; ".join(str(issue) for issue in issues[:2])
    residual = payload.get("residual_risk")
    if isinstance(residual, list) and residual:
        return "; ".join(str(item) for item in residual[:2])
    result = payload.get("result")
    return str(result) if result else ""


def closeout_summary(path: Path) -> dict[str, Any]:
    payload, warning = read_json(path)
    if payload is None:
        return {"id": path.stem, "source_file": rel(path), "warning": warning}
    external_effect = payload.get("external_effect")
    if not isinstance(external_effect, dict):
        external_effect = {}
    return {
        "id": payload.get("packet_id", path.stem),
        "packet_id": payload.get("packet_id", path.stem),
        "status": payload.get("status"),
        "lane": lane_from_closeout(payload),
        "objective": payload.get("objective"),
        "result": payload.get("result"),
        "command_ids": command_ids(payload),
        "command_exit_codes": command_exit_codes(payload),
        "external_effect": {
            "occurred": external_effect.get("occurred"),
            "details": external_effect.get("details"),
        },
        "generated_at": payload.get("generated_at"),
        "updated_at": payload.get("generated_at"),
        "residual_risk": payload.get("residual_risk", []),
        "blocker": concise_blocker(payload),
        "proof": proof_summary(payload),
        "source_file": rel(path),
    }


def latest_closeouts(limit: int = 5) -> list[dict[str, Any]]:
    closeout_paths = safe_json_files(PACKETS / "closeouts")
    items = [closeout_summary(path) for path in closeout_paths]
    return sorted(
        items,
        key=lambda item: (item.get("generated_at") or "", item.get("id") or "", item.get("source_file") or ""),
        reverse=True,
    )[:limit]


def packet_execution_summary(closeouts: list[dict[str, Any]], blocked_register_clear: bool) -> dict[str, Any]:
    blocked = [item for item in closeouts if item.get("status") == "BLOCKED"]
    partial = [item for item in closeouts if item.get("status") == "PARTIAL"]
    done = [item for item in closeouts if item.get("status") == "DONE"]
    warnings: list[dict[str, Any]] = []
    if blocked and blocked_register_clear:
        warnings.append(
            {
                "id": "blocked-closeout-register-divergence",
                "severity": "Watch",
                "title": "Blocked closeout/register divergence",
                "risk": [
                    "Guarded runner closeout JSON records blocked packet execution while blocked-packets.md says none recorded.",
                    "Treat closeout JSON as execution truth until the register is regenerated or reconciled.",
                ],
                "source_file": "state/cos/packets/closeouts/",
            }
        )
    return {
        "summary": {
            "closeout_count": len(closeouts),
            "blocked_count": len(blocked),
            "partial_count": len(partial),
            "done_count": len(done),
        },
        "recent": closeouts,
        "warnings": warnings,
    }


def native_hook_write_canary_state(path: Path = NATIVE_HOOK_CANARY_PATH) -> dict[str, Any]:
    payload, warning = read_json(path)
    if payload is None:
        return {
            "status": "unverified",
            "freshness": "missing",
            "source_file": rel(path),
            "warning": warning or "missing",
            "remediation_hint": "Run scripts/observability/native_hook_write_canary.py before claiming local write-path execution health.",
        }

    timestamp = parse_timestamp(payload.get("timestamp"))
    age_hours = None
    freshness = "unknown"
    observed_status = payload.get("status")
    status = str(observed_status or "unverified")
    if timestamp is None:
        status = "unverified"
        freshness = "invalid_timestamp"
    else:
        age_hours = round((datetime.now(timezone.utc) - timestamp).total_seconds() / 3600, 3)
        if age_hours > CANARY_STALE_HOURS:
            status = "unverified"
            freshness = "stale"
        else:
            freshness = "fresh"

    return {
        "status": status,
        "observed_status": observed_status,
        "freshness": freshness,
        "age_hours": age_hours,
        "stale_after_hours": CANARY_STALE_HOURS,
        "source_file": rel(path),
        "payload": payload,
    }


def live_session_native_hook_smoke_state(path: Path = LIVE_SESSION_SMOKE_PATH) -> dict[str, Any]:
    payload, warning = read_json(path)
    if payload is None:
        return {
            "status": "unverified",
            "freshness": "missing",
            "source_file": rel(path),
            "warning": warning or "missing",
            "remediation_hint": (
                "Run scripts/observability/live_session_native_hook_smoke.py "
                "--execution-origin telegram-live-session from the exact Telegram session being tested."
            ),
        }

    timestamp = parse_timestamp(payload.get("timestamp"))
    age_hours = None
    freshness = "unknown"
    observed_status = payload.get("status")
    execution_origin = payload.get("execution_origin")
    status = str(observed_status or "unverified")
    if timestamp is None:
        status = "unverified"
        freshness = "invalid_timestamp"
    else:
        age_hours = round((datetime.now(timezone.utc) - timestamp).total_seconds() / 3600, 3)
        if age_hours > CANARY_STALE_HOURS:
            status = "unverified"
            freshness = "stale"
        else:
            freshness = "fresh"

    if execution_origin != "telegram-live-session":
        status = "unverified"

    return {
        "status": status,
        "observed_status": observed_status,
        "execution_origin": execution_origin,
        "freshness": freshness,
        "age_hours": age_hours,
        "stale_after_hours": CANARY_STALE_HOURS,
        "source_file": rel(path),
        "payload": payload,
        "remediation_hint": (
            "A terminal-local result is not a pass. Re-run from the exact Telegram session with "
            "--execution-origin telegram-live-session before claiming live native-hook health."
        ),
    }


def native_hook_truth(
    closeouts: list[dict[str, Any]],
    write_canary: dict[str, Any],
    live_session_smoke: dict[str, Any],
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for item in closeouts:
        source = item.get("source_file")
        payload, warning = read_json(REPO_ROOT / str(source)) if source else (None, "missing source")
        if payload is None:
            if warning:
                continue
            continue
        for command in payload.get("command_results", []):
            if not isinstance(command, dict):
                continue
            excerpt = str(command.get("output_excerpt", ""))
            if RELAY_ERROR_PATTERN.search(excerpt):
                hits.append(
                    {
                        "packet_id": payload.get("packet_id"),
                        "command_id": command.get("id"),
                        "source_file": source,
                    }
                )
    write_status = write_canary.get("status")
    live_smoke_status = live_session_smoke.get("status")
    if hits:
        status = "degraded"
    elif write_status in {"blocked", "error", "degraded"}:
        status = "degraded"
    elif live_smoke_status in {"blocked", "error", "degraded"}:
        status = "degraded"
    elif live_smoke_status == "ok":
        status = "ok"
    else:
        status = "unverified"

    return {
        "status": status,
        "truth_rule": "Gateway health is necessary but insufficient for native-hook relay health.",
        "canary_required": "Native-hook relay health requires a real tool/write/canary path, not gateway status alone.",
        "degraded_if": "Mark execution substrate degraded when Native hook relay unavailable, native hook relay not found, or relay unavailable appears in fresh evidence.",
        "gateway_health": {
            "role": "necessary_but_insufficient",
            "tested_by_collector": False,
        },
        "native_hook_write_path": write_canary,
        "live_session_native_hook_smoke": live_session_smoke,
        "telegram_session_native_hook": live_session_smoke.get(
            "payload",
            {
                "status": live_smoke_status,
                "tested_by_terminal_canary": False,
                "reason": "The terminal-local write canary cannot prove the live Telegram session native-hook relay.",
            },
        ).get("telegram_session_native_hook", {"status": live_smoke_status}),
        "relay_error_hits": hits,
    }


def recent_closeout_sections(text: str | None, source: Path) -> list[dict[str, Any]]:
    if not text:
        return []
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_key: str | None = None
    for raw in text.splitlines():
        header = re.match(r"^##\s+(.+?)\s*$", raw)
        if header:
            if current:
                sections.append(current)
            current = {"title": header.group(1), "source_file": rel(source)}
            current_key = None
            continue
        subheader = re.match(r"^(Status|Artifacts|Verification|Residual risk|Actions):\s*(.*?)\s*$", raw)
        if subheader and current is not None:
            key = subheader.group(1).lower().replace(" ", "_")
            value = subheader.group(2)
            current_key = key
            current[key] = value if value else []
            continue
        bullet = re.match(r"^-\s+(.+?)\s*$", raw)
        if bullet and current is not None and current_key:
            current.setdefault(current_key, [])
            if isinstance(current[current_key], list):
                current[current_key].append(bullet.group(1))
    if current:
        sections.append(current)
    return sections


def security_findings(text: str | None, source: Path) -> list[dict[str, Any]]:
    if not text:
        return []
    findings: list[dict[str, Any]] = []
    severity: str | None = None
    capture: dict[str, Any] | None = None
    capture_key: str | None = None
    for raw in text.splitlines():
        if re.match(r"^##\s+", raw):
            if capture:
                findings.append(capture)
            severity = None
            capture = None
            capture_key = None
            continue

        sev_match = re.match(r"^###\s+(High|Medium|Low / Watch|Blocked Checks)\s*$", raw)
        if sev_match:
            if capture:
                findings.append(capture)
            severity = sev_match.group(1)
            capture = None
            capture_key = None
            continue
        finding_match = re.match(r"^####\s+(.+?)\s*$", raw)
        if finding_match and severity:
            if capture:
                findings.append(capture)
            capture = {
                "id": slug(finding_match.group(1)),
                "title": finding_match.group(1),
                "severity": severity,
                "source_file": rel(source),
            }
            capture_key = None
            continue
        key_match = re.match(r"^(Evidence|Risk|Remediation requires approval):\s*$", raw)
        if key_match and capture is not None:
            capture_key = key_match.group(1).lower().replace(" ", "_")
            capture[capture_key] = []
            continue
        bullet = re.match(r"^-\s+(.+?)\s*$", raw)
        if bullet and capture is not None and capture_key:
            capture[capture_key].append(bullet.group(1))
            continue
        if capture is not None and capture_key and raw.strip():
            capture[capture_key].append(raw.strip())
    if capture:
        findings.append(capture)
    return findings


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_dashboard() -> dict[str, Any]:
    current_priorities = read_text(STATE_COS / "current-priorities.md")
    open_loops = read_text(STATE_COS / "open-loops.md")
    waiting_on = read_text(STATE_COS / "waiting-on.md")
    blocked_packets = read_text(STATE_COS / "blocked-packets.md")
    recent_closeouts = read_text(STATE_COS / "recent-closeouts.md")
    calendar_actions = read_text(STATE_COS / "calendar-actions-pending.md")
    drafts_pending = read_text(STATE_COS / "drafts-pending-review.md")
    security_baseline = read_text(REPO_ROOT / "docs" / "security" / "z420-baseline-2026-04-24.md")
    reads = [
        current_priorities,
        open_loops,
        waiting_on,
        blocked_packets,
        recent_closeouts,
        calendar_actions,
        drafts_pending,
        security_baseline,
    ]

    supervisor_path = PACKETS / "supervisor_state.json"
    supervisor_state, supervisor_warning = read_json(supervisor_path)
    native_hook_canary_state = native_hook_write_canary_state()
    live_session_smoke_state = live_session_native_hook_smoke_state()
    json_warnings = {
        supervisor_path: supervisor_warning,
        NATIVE_HOOK_CANARY_PATH: None
        if native_hook_canary_state.get("freshness") != "missing"
        else native_hook_canary_state.get("warning", "missing"),
        LIVE_SESSION_SMOKE_PATH: None
        if live_session_smoke_state.get("freshness") != "missing"
        else live_session_smoke_state.get("warning", "missing"),
    }

    priorities = parse_priority_blocks(current_priorities.text, current_priorities.path)
    loops = first_table(open_loops.text)
    waiting_rows = first_table(waiting_on.text)
    queue_packets = [packet_summary(path) for path in safe_json_files(PACKETS / "queue")]
    blocked_packet_files = [packet_summary(path) for path in safe_json_files(PACKETS / "blocked")]
    latest_guarded_closeouts = latest_closeouts(limit=25)
    blocked_register_clear = no_pending(blocked_packets.text)
    packet_execution = packet_execution_summary(latest_guarded_closeouts, blocked_register_clear)
    execution_substrate = native_hook_truth(latest_guarded_closeouts, native_hook_canary_state, live_session_smoke_state)
    security = security_findings(security_baseline.text, security_baseline.path)

    needs_baine = [
        {
            "id": row.get("id"),
            "need": row.get("needed_for") or row.get("notes"),
            "waiting_on": row.get("waiting_on"),
            "status": row.get("status"),
            "last_checked": row.get("last_checked"),
            "source": row.get("source"),
            "notes": row.get("notes"),
            "source_file": rel(waiting_on.path),
        }
        for row in waiting_rows
        if row.get("waiting_on", "").lower() in {"principal", "baine"}
    ]

    deadlines = [
        {
            "id": row.get("id"),
            "status": row.get("status"),
            "owner": row.get("owner"),
            "next_review": row.get("next_review"),
            "notes": row.get("notes"),
            "source_file": rel(open_loops.path),
        }
        for row in loops
        if row.get("next_review") and row.get("next_review", "").lower() != "none"
        and row.get("status", "").lower() != "done"
    ]

    in_motion = [
        item
        for item in priorities
        if item.get("status") in {"active", "open", "ready-for-phase-1", "partial"}
    ]
    in_motion.extend(
        {
            "id": row.get("id"),
            "status": row.get("status"),
            "owner": row.get("owner"),
            "next_review": row.get("next_review"),
            "notes": row.get("notes"),
            "source_file": rel(open_loops.path),
        }
        for row in loops
        if row.get("status") in {"active", "partial"}
    )
    in_motion.extend(queue_packets)

    waiting_blocked = [
        {
            "id": row.get("id"),
            "waiting_on": row.get("waiting_on"),
            "status": row.get("status"),
            "needed_for": row.get("needed_for"),
            "notes": row.get("notes"),
            "source_file": rel(waiting_on.path),
        }
        for row in waiting_rows
    ]
    if blocked_register_clear:
        waiting_blocked.append(
            {
                "id": "blocked-packets-register",
                "status": "clear",
                "notes": "No blocked packets recorded in register.",
                "last_checked": last_checked(blocked_packets.text),
                "source_file": rel(blocked_packets.path),
            }
        )
    waiting_blocked.extend(blocked_packet_files)
    waiting_blocked.extend(
        {
            "id": item.get("packet_id") or item.get("id"),
            "status": item.get("status"),
            "lane": item.get("lane"),
            "objective": item.get("objective"),
            "notes": item.get("blocker") or item.get("result"),
            "proof": item.get("proof"),
            "source_file": item.get("source_file"),
            "external_effect": item.get("external_effect"),
            "command_ids": item.get("command_ids"),
            "command_exit_codes": item.get("command_exit_codes"),
            "next_step": "review closeout blocker before rerun",
        }
        for item in latest_guarded_closeouts
        if item.get("status") in {"BLOCKED", "PARTIAL"}
    )

    done_with_proof = recent_closeout_sections(recent_closeouts.text, recent_closeouts.path)
    done_with_proof.extend(item for item in latest_guarded_closeouts if item.get("status") == "DONE")

    risk_watch = [
        {
            "id": finding.get("id"),
            "severity": finding.get("severity"),
            "title": finding.get("title"),
            "risk": finding.get("risk", []),
            "evidence": finding.get("evidence", []),
            "source_file": finding.get("source_file"),
        }
        for finding in security
    ]
    if supervisor_state:
        snapshot = supervisor_state.get("last_snapshot", {})
        if isinstance(snapshot, dict):
            risk_watch.append(
                {
                    "id": "queue-supervisor-snapshot",
                    "severity": "Watch",
                    "title": "Packet queue health",
                    "risk": [
                        f"queue_count={snapshot.get('queue_count', 0)}",
                        f"blocked_count={snapshot.get('blocked_count', 0)}",
                        f"last_alert_count={supervisor_state.get('last_alert_count', 0)}",
                    ],
                    "evidence": [rel(supervisor_path)],
                    "source_file": rel(supervisor_path),
                }
            )
    risk_watch.extend(packet_execution["warnings"])
    risk_watch.append(
        {
            "id": "native-hook-relay-truth",
            "severity": "Watch" if execution_substrate["status"] == "unverified" else "High",
            "title": "Native-hook relay truth",
            "risk": [
                execution_substrate["truth_rule"],
                execution_substrate["canary_required"],
                f"status={execution_substrate['status']}",
                f"write_path_canary={native_hook_canary_state.get('status')} freshness={native_hook_canary_state.get('freshness')}",
                (
                    "live_session_native_hook_smoke="
                    f"{live_session_smoke_state.get('status')} "
                    f"origin={live_session_smoke_state.get('execution_origin')} "
                    f"freshness={live_session_smoke_state.get('freshness')}"
                ),
            ],
            "evidence": [
                native_hook_canary_state.get("source_file"),
                live_session_smoke_state.get("source_file"),
                *[item.get("source_file") for item in latest_guarded_closeouts[:4] if item.get("source_file")],
            ],
            "source_file": "state/cos/packets/closeouts/",
        }
    )

    external_pending = []
    if no_pending(calendar_actions.text):
        external_pending.append("calendar_actions_clear")
    if no_pending(drafts_pending.text):
        external_pending.append("drafts_pending_clear")

    system_trust = {
        "posture": "local-first, proof-bearing, approval-bound for external effects",
        "source_health": source_status(reads, json_warnings),
        "queue_supervisor": supervisor_state or {},
        "security_baseline": {
            "source_file": rel(security_baseline.path),
            "last_checked": "2026-04-24" if security_baseline.text else None,
            "finding_count": len(security),
            "high_count": sum(1 for item in security if item.get("severity") == "High"),
            "medium_count": sum(1 for item in security if item.get("severity") == "Medium"),
        },
        "external_action_registers": external_pending,
        "packet_execution": packet_execution,
        "execution_substrate": execution_substrate,
        "collector_boundaries": {
            "reads": "local files only",
            "writes": [rel(DEFAULT_OUTPUT)],
            "external_effect": False,
        },
    }

    return {
        "schema_version": 1,
        "generated_from": "local-files",
        "needs_baine": needs_baine,
        "deadlines": deadlines,
        "in_motion": in_motion,
        "waiting_blocked": waiting_blocked,
        "done_with_proof": done_with_proof,
        "risk_watch": risk_watch,
        "packet_execution": packet_execution,
        "system_trust": system_trust,
    }


def write_dashboard(path: Path, payload: dict[str, Any]) -> None:
    resolved = path.resolve()
    allowed_root = (REPO_ROOT / "state" / "observability").resolve()
    if resolved != allowed_root and allowed_root not in resolved.parents:
        raise SystemExit(f"refusing to write outside {rel(allowed_root)}: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local CoS observability dashboard JSON.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path under state/observability/.")
    parser.add_argument("--check", action="store_true", help="Build and validate payload without writing.")
    return parser.parse_args()


def main() -> int:
    args = build_args()
    payload = build_dashboard()
    if not args.check:
        write_dashboard(Path(args.output), payload)
    print(json.dumps({"status": "ok", "output": rel(Path(args.output)), "schema_version": payload["schema_version"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
