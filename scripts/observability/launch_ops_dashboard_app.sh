#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"
PORT="${OPS_DASHBOARD_PORT:-4177}"
REFRESH=1
OPEN_WINDOW=1
MODE="launch"

PID_FILE="/tmp/cos-ops-dashboard-http-${PORT}.pid"
LOG_FILE="/tmp/cos-ops-dashboard-http-${PORT}.log"
REFRESH_LOG="/tmp/cos-ops-dashboard-refresh-${PORT}.log"

usage() {
  cat <<EOF
Usage: $(basename "$0") [status|stop] [--no-refresh] [--no-open] [--port <port>]

Defaults:
  - refreshes state/observability/dashboard.json
  - ensures local HTTP server on 127.0.0.1:${PORT}
  - opens app window at /ui/ops-dashboard/
EOF
}

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      status)
        MODE="status"
        ;;
      stop)
        MODE="stop"
        ;;
      --no-refresh)
        REFRESH=0
        ;;
      --no-open)
        OPEN_WINDOW=0
        ;;
      --port)
        shift
        [ "${1:-}" ] || fail "--port requires a value"
        PORT="$1"
        PID_FILE="/tmp/cos-ops-dashboard-http-${PORT}.pid"
        LOG_FILE="/tmp/cos-ops-dashboard-http-${PORT}.log"
        REFRESH_LOG="/tmp/cos-ops-dashboard-refresh-${PORT}.log"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
    shift
  done
}

server_running() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -Eq "127\\.0\\.0\\.1:${PORT}[[:space:]]" && return 0
    ss -ltn 2>/dev/null | grep -Eq "\\*:${PORT}[[:space:]]" && return 0
  fi
  return 1
}

refresh_dashboard() {
  [ "${REFRESH}" -eq 1 ] || return 0

  if [ -f "${REPO_ROOT}/scripts/observability/collect_dashboard.py" ]; then
    if (cd "${REPO_ROOT}" && python3 scripts/observability/collect_dashboard.py >"${REFRESH_LOG}" 2>&1); then
      log "dashboard refreshed with collect_dashboard.py"
      return 0
    fi
  fi

  if [ -f "${REPO_ROOT}/scripts/observability/generate_dashboard.py" ]; then
    if (cd "${REPO_ROOT}" && python3 scripts/observability/generate_dashboard.py >"${REFRESH_LOG}" 2>&1); then
      log "dashboard refreshed with generate_dashboard.py"
      return 0
    fi
  fi

  if [ -f "${REFRESH_LOG}" ]; then
    log "refresh log tail:"
    tail -n 30 "${REFRESH_LOG}" >&2 || true
  fi
  fail "dashboard refresh failed"
}

start_server_if_needed() {
  if server_running; then
    log "dashboard server already running on 127.0.0.1:${PORT}"
    return 0
  fi

  log "starting dashboard server on 127.0.0.1:${PORT}"
  (
    cd "${REPO_ROOT}" || exit 1
    nohup python3 -m http.server "${PORT}" --bind 127.0.0.1 >"${LOG_FILE}" 2>&1 &
    printf '%s\n' "$!" >"${PID_FILE}"
  )

  count=0
  while [ "${count}" -lt 15 ]; do
    if server_running; then
      log "dashboard server ready"
      return 0
    fi
    count=$((count + 1))
    sleep 1
  done

  if [ -f "${LOG_FILE}" ]; then
    log "server log tail:"
    tail -n 30 "${LOG_FILE}" >&2 || true
  fi
  fail "dashboard server did not become ready"
}

print_status() {
  URL="http://127.0.0.1:${PORT}/ui/ops-dashboard/"
  JSON_PATH="${REPO_ROOT}/state/observability/dashboard.json"

  log "repo_root=${REPO_ROOT}"
  log "url=${URL}"
  if [ -f "${JSON_PATH}" ]; then
    log "dashboard_json=present (${JSON_PATH})"
  else
    log "dashboard_json=missing (${JSON_PATH})"
  fi

  if server_running; then
    log "server=running (127.0.0.1:${PORT})"
  else
    log "server=stopped (127.0.0.1:${PORT})"
  fi

  if [ -f "${PID_FILE}" ]; then
    log "pid_file=${PID_FILE} ($(cat "${PID_FILE}"))"
  fi
}

stop_server() {
  if [ ! -f "${PID_FILE}" ]; then
    log "no PID file at ${PID_FILE}; nothing to stop"
    return 0
  fi

  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [ -z "${pid}" ]; then
    rm -f "${PID_FILE}"
    log "removed empty PID file"
    return 0
  fi

  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "${pid}" >/dev/null 2>&1; then
      fail "process ${pid} still running; stop manually"
    fi
    log "stopped dashboard server pid=${pid}"
  else
    log "pid ${pid} not running"
  fi

  rm -f "${PID_FILE}"
}

open_app_window() {
  [ "${OPEN_WINDOW}" -eq 1 ] || return 0
  URL="http://127.0.0.1:${PORT}/ui/ops-dashboard/"

  if command -v google-chrome-stable >/dev/null 2>&1; then
    nohup google-chrome-stable --app="${URL}" >/dev/null 2>&1 &
    log "opened dashboard app window in google-chrome-stable"
    return 0
  fi

  if command -v chromium-browser >/dev/null 2>&1; then
    nohup chromium-browser --app="${URL}" >/dev/null 2>&1 &
    log "opened dashboard app window in chromium-browser"
    return 0
  fi

  if command -v chromium >/dev/null 2>&1; then
    nohup chromium --app="${URL}" >/dev/null 2>&1 &
    log "opened dashboard app window in chromium"
    return 0
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    nohup xdg-open "${URL}" >/dev/null 2>&1 &
    log "opened dashboard URL with xdg-open"
    return 0
  fi

  log "open manually: ${URL}"
}

main() {
  parse_args "$@"

  case "${MODE}" in
    status)
      print_status
      return 0
      ;;
    stop)
      stop_server
      return 0
      ;;
    launch)
      refresh_dashboard
      start_server_if_needed
      open_app_window
      return 0
      ;;
    *)
      fail "unsupported mode: ${MODE}"
      ;;
  esac
}

main "$@"
