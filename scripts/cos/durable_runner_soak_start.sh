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
COLLECTOR="${COLLECTOR:-}"
SUPERVISOR="${SUPERVISOR:-${SCRIPT_DIR}/durable_runner_soak_supervisor.sh}"
LOG_DIR="${ROOT_DIR}/logs"
RUN_DIR="${ROOT_DIR}/run"
PID_DIR="${ROOT_DIR}/pids"

mkdir -p "${LOG_DIR}" "${RUN_DIR}" "${PID_DIR}"

MAX_LOOPS=$(( DURATION_HOURS * 3600 * 1000 / POLL_MS ))

echo "Starting durable-runner soak"
echo "  root: ${RUN_DIR}"
echo "  duration_hours: ${DURATION_HOURS}"
echo "  poll_ms: ${POLL_MS}"
echo "  lease_ms: ${LEASE_MS}"
echo "  heartbeat_ms: ${HEARTBEAT_MS}"
if [[ -n "${COLLECTOR}" && -f "${COLLECTOR}" ]]; then
  echo "  collector: ${COLLECTOR}"
  echo "  collect_every_sec: ${COLLECT_EVERY_SEC}"
elif [[ -n "${COLLECTOR}" ]]; then
  echo "  collector: disabled (${COLLECTOR} not found)"
else
  echo "  collector: disabled"
fi

nohup bash "${SUPERVISOR}" \
  "${ROOT_DIR}" \
  "${DURATION_HOURS}" \
  "${POLL_MS}" \
  "${LEASE_MS}" \
  "${HEARTBEAT_MS}" \
  "${COLLECT_EVERY_SEC}" \
  "${WORKER_ID}" \
  > "${LOG_DIR}/supervisor.log" 2>&1 &
SUPERVISOR_PID=$!
echo "${SUPERVISOR_PID}" > "${PID_DIR}/supervisor.pid"

# Liveness gate: fail fast if required background work exits immediately.
sleep 3
watch_alive="false"
collector_alive="disabled"
if [[ -f "${PID_DIR}/watch.pid" ]] && kill -0 "$(cat "${PID_DIR}/watch.pid")" 2>/dev/null; then watch_alive="true"; fi
if [[ -n "${COLLECTOR}" && -f "${COLLECTOR}" ]]; then
  collector_alive="false"
  if [[ -f "${PID_DIR}/collector.pid" ]] && kill -0 "$(cat "${PID_DIR}/collector.pid")" 2>/dev/null; then collector_alive="true"; fi
fi
if ! kill -0 "${SUPERVISOR_PID}" 2>/dev/null || [[ "${watch_alive}" != "true" || "${collector_alive}" == "false" ]]; then
  echo "SOAK_START_FAILED"
  echo "supervisor_alive=false"
  echo "watch_alive=${watch_alive}"
  echo "collector_alive=${collector_alive}"
  echo "--- supervisor.log tail ---"
  tail -n 80 "${LOG_DIR}/supervisor.log" 2>/dev/null || true
  echo "--- watch.log tail ---"
  tail -n 80 "${LOG_DIR}/watch.log" 2>/dev/null || true
  echo "--- collector.log tail ---"
  tail -n 80 "${LOG_DIR}/collector.log" 2>/dev/null || true
  exit 2
fi

cat <<EOF
SOAK_STARTED
supervisor_pid=${SUPERVISOR_PID}
watch_pid=$(cat "${PID_DIR}/watch.pid")
collector_pid=$(cat "${PID_DIR}/collector.pid" 2>/dev/null || echo disabled)
run_root=${RUN_DIR}
EOF
