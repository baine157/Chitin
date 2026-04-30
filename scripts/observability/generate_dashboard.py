#!/usr/bin/env python3
"""Generate a local, read-only Chief of Staff observability snapshot."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "observability"
OUT = STATE_DIR / "dashboard.json"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def run(cmd: list[str], timeout: int = 12) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except Exception as exc:  # noqa: BLE001 - report-only snapshot
        return 1, str(exc)


def parse_table(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return rows
    headers = [part.strip() for part in lines[0].strip("|").split("|")]
    for line in lines[2:]:
        values = [part.strip() for part in line.strip("|").split("|")]
        if len(values) != len(headers):
            continue
        rows.append(dict(zip(headers, values)))
    return rows


def status_from_update(text: str) -> str:
    if "up to date" in text.lower():
        return "clear"
    if "available" in text.lower():
        return "watch"
    return "unknown"


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    update_code, update_text = run(["openclaw", "update", "status"])
    health_code, health_text = run(["openclaw", "health", "--json"])
    cron_code, cron_text = run(["openclaw", "cron", "list", "--json"])

    open_loops = parse_table(read_text(ROOT / "state" / "cos" / "open-loops.md"))
    waiting = parse_table(read_text(ROOT / "state" / "cos" / "waiting-on.md"))
    blocked_text = read_text(ROOT / "state" / "cos" / "blocked-packets.md")
    closeouts_text = read_text(ROOT / "state" / "cos" / "recent-closeouts.md")
    security_text = read_text(ROOT / "docs" / "security" / "z420-baseline-2026-04-24.md")

    blocked_clear = "No blocked packets recorded" in blocked_text
    security_high = len(re.findall(r"^### High", security_text, flags=re.MULTILINE))
    update_status = status_from_update(update_text)

    try:
        health_json = json.loads(health_text) if health_code == 0 else {}
    except json.JSONDecodeError:
        health_json = {}

    try:
        cron_json = json.loads(cron_text) if cron_code == 0 else {"jobs": []}
    except json.JSONDecodeError:
        cron_json = {"jobs": []}

    jobs = cron_json.get("jobs", [])
    security_jobs = [job for job in jobs if str(job.get("name", "")).startswith("z420-security:")]
    inbox_watch = next((job for job in jobs if job.get("name") == "CoS Inbox Watch"), None)

    waiting_cards = []
    for item in waiting:
        waiting_cards.append(
            {
                "id": item.get("id", "waiting"),
                "title": item.get("needed_for") or item.get("id", "Waiting item"),
                "owner": item.get("waiting_on", "unknown"),
                "status": item.get("status", "waiting"),
                "next_step": item.get("notes", ""),
                "source": item.get("source", "state/cos/waiting-on.md"),
            }
        )

    in_motion = []
    for item in open_loops:
        if item.get("status") in {"active", "partial"}:
            in_motion.append(
                {
                    "id": item.get("id", "loop"),
                    "title": item.get("id", "Open loop").replace("-", " ").title(),
                    "owner": item.get("owner", "CoS"),
                    "status": item.get("status", "active"),
                    "next_update": item.get("next_review", "next check"),
                    "proof": item.get("notes", ""),
                }
            )

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "surface": "Z420 CoS Observability Dashboard",
        "overall": {
            "state": "needs_attention",
            "headline": "Your CoS is tracking onboarding, guarded maintenance, and security posture with no external effects enabled.",
            "last_checked": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
            "next_best_action": "Complete the MD Anderson onboarding packet before May 11.",
            "next_action_detail": "I can prepare the checklist and source packet, but signing, dating, sending, and portal actions still need you.",
            "authority_state": "Read-only monitoring; drafting/checklists allowed; external actions require approval.",
        },
        "needs_baine": [
            {
                "id": "mda-onboarding-packet",
                "title": "MD Anderson onboarding forms/policies packet",
                "why_it_matters": "Required onboarding forms need review, completion, signature/date, and return.",
                "deadline": "2026-05-11",
                "authority": "User action required; CoS can prepare checklist but cannot sign/send.",
                "next_best_action": "Prioritize Clinical Specialist Check-in Documents.pdf and confirm Houston address if available.",
                "source": "CoS inbox watch alert",
                "severity": "high",
            },
            {
                "id": "mda-ay26-contract",
                "title": "MD Anderson AY 26-27 contract",
                "why_it_matters": "Appointment-related contract needs download, wet signature, and upload.",
                "deadline": "not stated",
                "authority": "User action required; no portal login/signature authority granted.",
                "next_best_action": "Complete before the May 11 packet if possible.",
                "source": "CoS inbox watch alert",
                "severity": "medium",
            },
            {
                "id": "i9-section-2",
                "title": "Form I-9 Section 2 follow-up",
                "why_it_matters": "Section 2 must be completed by an authorized representative by the third day of work for pay.",
                "deadline": "third day of work for pay",
                "authority": "User confirmation/contact required; CoS cannot send or schedule without approval.",
                "next_best_action": "Confirm with Daniel Quinones or Lorena Villanueva whether Section 2 is covered.",
                "source": "CoS inbox watch alert",
                "severity": "medium",
            },
        ],
        "deadlines": [
            {"label": "May 11", "title": "MD Anderson onboarding packet", "urgency": "upcoming"},
            {"label": "Unstated", "title": "AY 26-27 contract wet-sign/upload", "urgency": "watch"},
            {"label": "Start + 3 days", "title": "I-9 Section 2", "urgency": "watch"},
        ],
        "in_motion": in_motion,
        "waiting_blocked": waiting_cards,
        "done_with_proof": [
            {
                "title": "Z420 security lane",
                "status": "done",
                "proof": "Read-only scripts and OpenClaw cron jobs created; baseline and schedule documented.",
                "artifact": "docs/security/z420-baseline-2026-04-24.md",
            },
            {
                "title": "iCloud CalDAV calendar",
                "status": "done",
                "proof": "khal listed synced iCloud events from local .ics cache.",
                "artifact": "~/.local/share/vdirsyncer/calendars/",
            },
            {
                "title": "Recent CoS closeout",
                "status": "done",
                "proof": "Recent closeouts register contains weekend guarded packet runner verification.",
                "artifact": "state/cos/recent-closeouts.md",
            },
        ],
        "risk_watch": [
            {
                "title": "SSH listens on all interfaces",
                "level": "high",
                "next_step": "Review firewall/router/tailnet exposure before changing SSH.",
                "source": "docs/security/z420-baseline-2026-04-24.md",
            },
            {
                "title": "BW_SESSION appears in local logs/snapshots",
                "level": "medium",
                "next_step": "Approval-gated targeted redaction/quarantine.",
                "source": "docs/security/z420-baseline-2026-04-24.md",
            },
            {
                "title": "Voice transcription endpoint down",
                "level": "watch",
                "next_step": "Do not rely on voice for CoS/Lobster until Speaches passes repeated smoke tests.",
                "source": "current session",
            },
        ],
        "system_trust": {
            "posture": "local-first, proof-bearing, approval-bound for external effects",
            "openclaw_update": update_status,
            "openclaw_health": "clear" if health_json.get("ok") else "watch",
            "blocked_packets": "clear" if blocked_clear else "watch",
            "security_jobs": "clear" if len(security_jobs) >= 2 else "watch",
            "inbox_watch": inbox_watch.get("state", {}).get("lastRunStatus", "unknown") if inbox_watch else "unknown",
            "source_health": {
                "state/cos/open-loops.md": "ok" if open_loops else "missing or empty",
                "state/cos/waiting-on.md": "ok" if waiting else "missing or empty",
                "state/cos/blocked-packets.md": "ok" if blocked_text else "missing or empty",
                "state/cos/recent-closeouts.md": "ok" if closeouts_text else "missing or empty",
                "docs/security/z420-baseline-2026-04-24.md": "ok" if security_text else "missing or empty",
            },
            "queue_supervisor": {
                "last_snapshot": {
                    "queue_count": len(in_motion),
                    "blocked_count": 0 if blocked_clear else 1,
                    "done_count": 3,
                    "closeout_count": 1 if closeouts_text else 0,
                }
            },
            "security_baseline": {
                "source_file": "docs/security/z420-baseline-2026-04-24.md",
                "finding_count": len(security_text) and len(re.findall(r"^#### ", security_text, flags=re.MULTILINE)),
                "high_count": security_high,
                "medium_count": len(re.findall(r"^### Medium", security_text, flags=re.MULTILINE)),
            },
            "collector_boundaries": {
                "reads": "local files + read-only OpenClaw status commands",
                "writes": ["state/observability/dashboard.json"],
                "external_effect": False,
            },
        },
        "raw_status": {
            "openclaw_update_exit": update_code,
            "openclaw_health_exit": health_code,
            "openclaw_cron_exit": cron_code,
            "security_high_sections": security_high,
            "closeouts_chars": len(closeouts_text),
        },
    }

    OUT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
