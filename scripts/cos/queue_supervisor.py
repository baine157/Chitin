#!/usr/bin/env python3
"""
Queue Supervisor + SLA Alerts (v0)

Monitors CoS packet queue health and emits a compact binary status:
- QUEUE_SUPERVISOR_CLEAR
- QUEUE_SUPERVISOR_ALERT
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKETS_ROOT = REPO_ROOT / "state" / "cos" / "packets"
DEFAULT_STATE_FILE = PACKETS_ROOT / "supervisor_state.json"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat()


def from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def safe_list_json(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


@dataclass
class Alert:
    item: str
    status: str
    need: str
    boundary: str = "none"


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor packet queue SLA and emit compact alerts.")
    parser.add_argument("--queue-dir", default=str(PACKETS_ROOT / "queue"))
    parser.add_argument("--done-dir", default=str(PACKETS_ROOT / "done"))
    parser.add_argument("--blocked-dir", default=str(PACKETS_ROOT / "blocked"))
    parser.add_argument("--closeouts-dir", default=str(PACKETS_ROOT / "closeouts"))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--max-queue-depth", type=int, default=20)
    parser.add_argument("--queue-stale-minutes", type=int, default=360)
    parser.add_argument("--processing-idle-minutes", type=int, default=240)
    parser.add_argument("--blocked-new-threshold", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text contract.")
    return parser.parse_args()


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def newest_mtime(paths: list[Path]) -> datetime | None:
    if not paths:
        return None
    return max(file_mtime(path) for path in paths)


def oldest_mtime(paths: list[Path]) -> datetime | None:
    if not paths:
        return None
    return min(file_mtime(path) for path in paths)


def count_new_since(paths: list[Path], checkpoint: datetime | None) -> int:
    if checkpoint is None:
        return 0
    return sum(1 for path in paths if file_mtime(path) > checkpoint)


def summarize(snapshot: dict[str, Any], alerts: list[Alert], as_json: bool) -> tuple[str, int]:
    if as_json:
        payload = {
            "status": "QUEUE_SUPERVISOR_ALERT" if alerts else "QUEUE_SUPERVISOR_CLEAR",
            "alerts": [alert.__dict__ for alert in alerts],
            "snapshot": snapshot,
        }
        return json.dumps(payload, indent=2, sort_keys=True), (2 if alerts else 0)

    if not alerts:
        return "QUEUE_SUPERVISOR_CLEAR", 0

    lines: list[str] = ["QUEUE_SUPERVISOR_ALERT"]
    for alert in alerts:
        lines.append(f"Item: {alert.item}")
        lines.append(f"Status: {alert.status}")
        lines.append(f"Need: {alert.need}")
        lines.append(f"Boundary: {alert.boundary}")
    return "\n".join(lines), 2


def main() -> int:
    args = build_args()
    now = utc_now()

    queue_dir = Path(args.queue_dir).resolve()
    done_dir = Path(args.done_dir).resolve()
    blocked_dir = Path(args.blocked_dir).resolve()
    closeouts_dir = Path(args.closeouts_dir).resolve()
    state_file = Path(args.state_file).resolve()

    queue_files = safe_list_json(queue_dir)
    done_files = safe_list_json(done_dir)
    blocked_files = safe_list_json(blocked_dir)
    closeout_files = safe_list_json(closeouts_dir)

    current = {
        "queue_count": len(queue_files),
        "done_count": len(done_files),
        "blocked_count": len(blocked_files),
        "closeout_count": len(closeout_files),
        "queue_oldest_at": to_iso(oldest_mtime(queue_files)),
        "done_newest_at": to_iso(newest_mtime(done_files)),
        "blocked_newest_at": to_iso(newest_mtime(blocked_files)),
    }

    state = read_state(state_file)
    last_run_at = from_iso(state.get("last_run_at"))

    # First run sets baseline to avoid alerting on historical setup artifacts.
    if not state or last_run_at is None:
        baseline = {
            "initialized_at": to_iso(now),
            "last_run_at": to_iso(now),
            "last_snapshot": current,
        }
        write_state(state_file, baseline)
        output, code = summarize(current, [], args.json)
        print(output)
        return code

    alerts: list[Alert] = []

    if len(queue_files) > args.max_queue_depth:
        alerts.append(
            Alert(
                item="queue_depth",
                status=f"depth {len(queue_files)} exceeds max {args.max_queue_depth}",
                need="reduce queue or increase runner cadence",
            )
        )

    queue_oldest = oldest_mtime(queue_files)
    if queue_oldest is not None:
        oldest_age_minutes = int((now - queue_oldest).total_seconds() / 60)
        if oldest_age_minutes > args.queue_stale_minutes:
            alerts.append(
                Alert(
                    item="queue_oldest_packet_age",
                    status=f"oldest queued packet age {oldest_age_minutes}m exceeds {args.queue_stale_minutes}m",
                    need="check runner activity and clear stalled packets",
                )
            )

    new_blocked = count_new_since(blocked_files, last_run_at)
    if new_blocked >= args.blocked_new_threshold:
        alerts.append(
            Alert(
                item="blocked_packet_spike",
                status=f"{new_blocked} new blocked packets since last check",
                need="inspect latest closeouts and adjust lane/authority before continuing",
            )
        )

    if len(queue_files) > 0:
        last_processing = newest_mtime(done_files + blocked_files)
        if last_processing is None:
            alerts.append(
                Alert(
                    item="processing_absent",
                    status="queue has packets but no done/blocked processing artifacts exist",
                    need="verify heartbeat runner invocation",
                )
            )
        else:
            idle_minutes = int((now - last_processing).total_seconds() / 60)
            if idle_minutes > args.processing_idle_minutes:
                alerts.append(
                    Alert(
                        item="processing_idle",
                        status=f"no packet processing for {idle_minutes}m with non-empty queue",
                        need="restore runner execution path",
                    )
                )

    next_state = {
        "initialized_at": state.get("initialized_at", to_iso(now)),
        "last_run_at": to_iso(now),
        "last_snapshot": current,
        "last_alert_count": len(alerts),
        "last_alert_items": [alert.item for alert in alerts],
    }
    write_state(state_file, next_state)

    output, code = summarize(current, alerts, args.json)
    print(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
