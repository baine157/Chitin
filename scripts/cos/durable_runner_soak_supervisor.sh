#!/usr/bin/env bash
set -euo pipefail

DURATION_HOURS="${2:-24}"
POLL_MS="${3:-1000}"
LEASE_MS="${4:-120000}"
HEARTBEAT_MS="${5:-60000}"
COLLECT_EVERY_SEC="${6:-300}"
WORKER_ID="${7:-soak-worker-main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROOT_DIR="${1:-${REPO_ROOT}/state/cos/durable-runner}"
MANIFEST_PATH="${MANIFEST_PATH:-${REPO_ROOT}/lane-manifests/orchestrator_control_plane_health.yaml}"
RUNNER_CLI="${RUNNER_CLI:-${REPO_ROOT}/durable-runner/src/cli.ts}"
COLLECTOR="${COLLECTOR:-${REPO_ROOT}/scripts/observability/collect_dashboard.py}"
LOG_DIR="${ROOT_DIR}/logs"
RUN_DIR="${ROOT_DIR}/run"
PID_DIR="${ROOT_DIR}/pids"
LEDGER_DIR="${RUN_DIR}/ledger"
INCIDENT_LOG="${LEDGER_DIR}/soak-supervisor-incidents.jsonl"
HEARTBEAT_FILE="${PID_DIR}/supervisor-heartbeat.json"

mkdir -p "${LOG_DIR}" "${RUN_DIR}" "${PID_DIR}" "${LEDGER_DIR}"
MAX_LOOPS=$(( DURATION_HOURS * 3600 * 1000 / POLL_MS ))
END_EPOCH=$(( $(date +%s) + DURATION_HOURS * 3600 ))

json_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

write_incident() {
  local process_name="$1"
  local reason="$2"
  local at
  at="$(json_now)"
  printf '{"at":"%s","type":"restart","process":"%s","reason":"%s"}\n' "${at}" "${process_name}" "${reason}" >> "${INCIDENT_LOG}"
}

start_watch() {
  nohup node "${RUNNER_CLI}" watch \
    --manifest "${MANIFEST_PATH}" \
    --root "${RUN_DIR}" \
    --worker "${WORKER_ID}" \
    --lease-ms "${LEASE_MS}" \
    --poll-ms "${POLL_MS}" \
    --heartbeat-ms "${HEARTBEAT_MS}" \
    --max-loops "${MAX_LOOPS}" \
    >> "${LOG_DIR}/watch.log" 2>&1 &
  echo "$!" > "${PID_DIR}/watch.pid"
}

start_collector() {
  nohup bash -lc "
while true; do
  python3 \"${COLLECTOR}\" >> \"${LOG_DIR}/collector.log\" 2>&1 || true
  sleep \"${COLLECT_EVERY_SEC}\"
done
" >/dev/null 2>&1 &
  echo "$!" > "${PID_DIR}/collector.pid"
}

node "${RUNNER_CLI}" init --root "${RUN_DIR}" >/dev/null

start_watch
start_collector

while (( $(date +%s) < END_EPOCH )); do
  watch_pid="$(cat "${PID_DIR}/watch.pid" 2>/dev/null || true)"
  collector_pid="$(cat "${PID_DIR}/collector.pid" 2>/dev/null || true)"

  if [[ -z "${watch_pid}" ]] || ! kill -0 "${watch_pid}" 2>/dev/null; then
    write_incident "watch" "process_not_alive"
    start_watch
  fi

  if [[ -z "${collector_pid}" ]] || ! kill -0 "${collector_pid}" 2>/dev/null; then
    write_incident "collector" "process_not_alive"
    start_collector
  fi

  printf '{"at":"%s","status":"alive","watchPid":"%s","collectorPid":"%s"}\n' \
    "$(json_now)" \
    "$(cat "${PID_DIR}/watch.pid" 2>/dev/null || echo missing)" \
    "$(cat "${PID_DIR}/collector.pid" 2>/dev/null || echo missing)" \
    > "${HEARTBEAT_FILE}"

  sleep 30
done
