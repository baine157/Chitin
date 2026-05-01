#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${OPENCLAW_ORCHESTRATOR_ROOT:-/home/baine/openclaw/orchestrator}"
AGENT_TIMEOUT="${OPENCLAW_EXECUTION_HEALTH_AGENT_TIMEOUT:-180}"

cd "${REPO_ROOT}"

python3 scripts/observability/native_hook_write_canary.py
python3 scripts/observability/execution_plane_smoke.py --include-agent-smoke --agent-timeout "${AGENT_TIMEOUT}"
python3 scripts/cos/queue_supervisor.py --json
python3 scripts/observability/collect_dashboard.py

python3 - <<'PY'
import json
from pathlib import Path

root = Path("/home/baine/openclaw/orchestrator")
dashboard = json.loads((root / "state/observability/dashboard.json").read_text(encoding="utf-8"))
execution = dashboard.get("system_trust", {}).get("execution_substrate", {})
split = execution.get("control_plane_vs_execution_plane", {})
packet = dashboard.get("packet_execution", {}).get("summary", {})

print("EXECUTION_PLANE_HEALTH")
print(f"status={execution.get('status')}")
print(f"gateway={split.get('gateway_alive')} diagnostic={split.get('gateway_diagnostic_detail')}")
print(f"hooks={split.get('hooks_registry_ready')}")
print(f"shell={split.get('shell_execution_usable')}")
print(f"agent={split.get('openclaw_agent_execution_usable')}")
print(f"native_relay={split.get('native_relay_usable')}")
print(f"packet_blocked_count={packet.get('blocked_count')}")
print(f"active_blocked_packet_count={packet.get('active_blocked_packet_count')}")
PY
