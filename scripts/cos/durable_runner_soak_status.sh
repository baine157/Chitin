#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROOT_DIR="${1:-${REPO_ROOT}/state/cos/durable-runner}"
RUN_DIR="${ROOT_DIR}/run"
PID_DIR="${ROOT_DIR}/pids"
RUNNER_CLI="${RUNNER_CLI:-${REPO_ROOT}/durable-runner/src/cli.ts}"
WATCH_HEALTH="${RUN_DIR}/state/watch-health.json"

watch_pid="missing"
collector_pid="missing"
supervisor_pid="missing"
if [[ -f "${PID_DIR}/watch.pid" ]]; then watch_pid="$(cat "${PID_DIR}/watch.pid")"; fi
if [[ -f "${PID_DIR}/collector.pid" ]]; then collector_pid="$(cat "${PID_DIR}/collector.pid")"; fi
if [[ -f "${PID_DIR}/supervisor.pid" ]]; then supervisor_pid="$(cat "${PID_DIR}/supervisor.pid")"; fi
live_pid="$(systemctl --user show durable-runner-soak.service -p MainPID --value 2>/dev/null || true)"
if [[ -n "${live_pid}" ]] && [[ "${live_pid}" != "0" ]]; then
  supervisor_pid="${live_pid}"
fi

watch_alive="false"
collector_alive="false"
supervisor_alive="false"
if [[ "${watch_pid}" != "missing" ]] && kill -0 "${watch_pid}" 2>/dev/null; then watch_alive="true"; fi
if [[ "${collector_pid}" != "missing" ]] && kill -0 "${collector_pid}" 2>/dev/null; then collector_alive="true"; fi
if [[ "${supervisor_pid}" != "missing" ]] && kill -0 "${supervisor_pid}" 2>/dev/null; then supervisor_alive="true"; fi

echo "SOAK_STATUS"
echo "supervisor_pid=${supervisor_pid}"
echo "supervisor_alive=${supervisor_alive}"
echo "watch_pid=${watch_pid}"
echo "watch_alive=${watch_alive}"
echo "collector_pid=${collector_pid}"
echo "collector_alive=${collector_alive}"

if [[ -f "${PID_DIR}/supervisor-heartbeat.json" ]]; then
  echo "supervisor_heartbeat_path=${PID_DIR}/supervisor-heartbeat.json"
  sed -n '1,120p' "${PID_DIR}/supervisor-heartbeat.json"
fi

if [[ -f "${WATCH_HEALTH}" ]]; then
  echo "watch_health_path=${WATCH_HEALTH}"
  sed -n '1,200p' "${WATCH_HEALTH}"
else
  echo "watch_health_path=missing"
fi

echo "sample_task_state_counts:"
for state in queued running waiting_approval done failed canceled; do
  dir="${RUN_DIR}/tasks/${state}"
  count=0
  if [[ -d "${dir}" ]]; then
    count=$(find "${dir}" -maxdepth 1 -type f -name '*.json' | wc -l)
  fi
  echo "  ${state}=${count}"
done

echo "recent_events:"
EVENTS_DIR="${RUN_DIR}/events"
if [[ -d "${EVENTS_DIR}" ]]; then
  find "${EVENTS_DIR}" -maxdepth 1 -type f -name '*.jsonl' | head -n 3 | while read -r event_file; do
    echo "--- ${event_file}"
    tail -n 5 "${event_file}" || true
  done
else
  echo "  none"
fi

echo "cli_probe:"
node "${RUNNER_CLI}" cleanup-quarantine --root "${RUN_DIR}" --dry-run
