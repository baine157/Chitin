#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROOT_DIR="${1:-${REPO_ROOT}/state/cos/durable-runner}"
RUN_DIR="${ROOT_DIR}/run"
LOG_DIR="${ROOT_DIR}/logs"
PID_DIR="${ROOT_DIR}/pids"
REPORT_PATH="${ROOT_DIR}/soak-report.txt"
WATCH_HEALTH="${RUN_DIR}/state/watch-health.json"

stop_pid_file() {
  local file="$1"
  local name="$2"
  if [[ -f "${file}" ]]; then
    local pid
    pid="$(cat "${file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
      sleep 1
      if kill -0 "${pid}" 2>/dev/null; then
        kill -9 "${pid}" 2>/dev/null || true
      fi
    fi
    echo "${name}_pid=${pid}" >> "${REPORT_PATH}"
  else
    echo "${name}_pid=missing" >> "${REPORT_PATH}"
  fi
}

rm -f "${REPORT_PATH}"
echo "DURABLE_RUNNER_SOAK_REPORT" >> "${REPORT_PATH}"
echo "generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${REPORT_PATH}"
echo "run_root=${RUN_DIR}" >> "${REPORT_PATH}"

stop_pid_file "${PID_DIR}/watch.pid" "watch"
stop_pid_file "${PID_DIR}/collector.pid" "collector"
stop_pid_file "${PID_DIR}/supervisor.pid" "supervisor"

if [[ -f "${WATCH_HEALTH}" ]]; then
  echo "" >> "${REPORT_PATH}"
  echo "watch_health:" >> "${REPORT_PATH}"
  sed -n '1,220p' "${WATCH_HEALTH}" >> "${REPORT_PATH}"
else
  echo "watch_health=missing" >> "${REPORT_PATH}"
fi

echo "" >> "${REPORT_PATH}"
echo "task_state_counts:" >> "${REPORT_PATH}"
for state in queued running waiting_approval done failed canceled; do
  dir="${RUN_DIR}/tasks/${state}"
  count=0
  if [[ -d "${dir}" ]]; then
    count=$(find "${dir}" -maxdepth 1 -type f -name '*.json' | wc -l)
  fi
  echo "  ${state}=${count}" >> "${REPORT_PATH}"
done

echo "" >> "${REPORT_PATH}"
echo "quarantine_summary:" >> "${REPORT_PATH}"
node "${REPO_ROOT}/durable-runner/src/cli.ts" cleanup-quarantine --root "${RUN_DIR}" --dry-run >> "${REPORT_PATH}" 2>/dev/null || true

echo "" >> "${REPORT_PATH}"
echo "log_tails:" >> "${REPORT_PATH}"
for logf in "${LOG_DIR}/watch.log" "${LOG_DIR}/collector.log"; do
  echo "--- ${logf}" >> "${REPORT_PATH}"
  if [[ -f "${logf}" ]]; then
    tail -n 40 "${logf}" >> "${REPORT_PATH}" || true
  else
    echo "missing" >> "${REPORT_PATH}"
  fi
done

echo "--- ${LOG_DIR}/supervisor.log" >> "${REPORT_PATH}"
if [[ -f "${LOG_DIR}/supervisor.log" ]]; then
  tail -n 40 "${LOG_DIR}/supervisor.log" >> "${REPORT_PATH}" || true
else
  echo "missing" >> "${REPORT_PATH}"
fi

echo "" >> "${REPORT_PATH}"
echo "supervisor_incidents:" >> "${REPORT_PATH}"
if [[ -f "${RUN_DIR}/ledger/soak-supervisor-incidents.jsonl" ]]; then
  tail -n 100 "${RUN_DIR}/ledger/soak-supervisor-incidents.jsonl" >> "${REPORT_PATH}" || true
else
  echo "none" >> "${REPORT_PATH}"
fi

cat <<EOF
SOAK_STOPPED
report_path=${REPORT_PATH}
EOF
