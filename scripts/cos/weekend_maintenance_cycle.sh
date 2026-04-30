#!/usr/bin/env sh
set -eu

REPO_ROOT="/home/baine/openclaw/orchestrator"
cd "$REPO_ROOT"

CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-/home/baine/.openclaw/openclaw.json}"
EXPECTED_OPENCLAW_VERSION="${EXPECTED_OPENCLAW_VERSION:-2026.4.26}"
EXPECTED_NODE_VERSION="${EXPECTED_NODE_VERSION:-v22.22.2}"
EXPECTED_GATEWAY_BIND="${EXPECTED_GATEWAY_BIND:-loopback}"
EXPECTED_GATEWAY_AUTH_MODE="${EXPECTED_GATEWAY_AUTH_MODE:-password}"
EXPECTED_GATEWAY_ALLOW_TAILSCALE="${EXPECTED_GATEWAY_ALLOW_TAILSCALE:-false}"
CANARY_AGENT_ID="${CANARY_AGENT_ID:-main}"
CANARY_TIMEOUT_SECONDS="${CANARY_TIMEOUT_SECONDS:-90}"
CANARY_MESSAGE="${CANARY_MESSAGE:-Canary check only. Reply exactly: OK}"
RELAY_PATTERN='native hook relay not found|Native hook relay unavailable|relay unavailable'

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

run_version_gate() {
  openclaw_version="$(
    openclaw --version 2>&1 | python3 -c '
import re
import sys
text = sys.stdin.read()
match = re.search(r"OpenClaw\s+([0-9][0-9.]*)", text)
print(match.group(1) if match else "")
'
  )"
  [ -n "${openclaw_version}" ] || fail "could not parse openclaw version output"
  [ "${openclaw_version}" = "${EXPECTED_OPENCLAW_VERSION}" ] || fail \
    "openclaw version mismatch: expected ${EXPECTED_OPENCLAW_VERSION}, got ${openclaw_version}"

  node_version="$(node --version 2>/dev/null || true)"
  [ -n "${node_version}" ] || fail "node is unavailable"
  [ "${node_version}" = "${EXPECTED_NODE_VERSION}" ] || fail \
    "node version mismatch: expected ${EXPECTED_NODE_VERSION}, got ${node_version}"

  log "[gate] runtime versions pinned (openclaw=${openclaw_version}, node=${node_version})"
}

run_topology_gate() {
  [ -f "${CONFIG_PATH}" ] || fail "openclaw config missing: ${CONFIG_PATH}"
  topology="$(
    python3 - "${CONFIG_PATH}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

gateway = data.get("gateway", {})
auth = gateway.get("auth", {})
bind_mode = gateway.get("bind")
auth_mode = auth.get("mode")
allow_tailscale = auth.get("allowTailscale")
print(f"{bind_mode}\t{auth_mode}\t{str(bool(allow_tailscale)).lower()}")
PY
  )"
  bind_mode="$(printf '%s' "${topology}" | awk -F '\t' '{print $1}')"
  auth_mode="$(printf '%s' "${topology}" | awk -F '\t' '{print $2}')"
  allow_tailscale="$(printf '%s' "${topology}" | awk -F '\t' '{print $3}')"

  [ "${bind_mode}" = "${EXPECTED_GATEWAY_BIND}" ] || fail \
    "gateway bind mismatch: expected ${EXPECTED_GATEWAY_BIND}, got ${bind_mode}"
  [ "${auth_mode}" = "${EXPECTED_GATEWAY_AUTH_MODE}" ] || fail \
    "gateway auth mode mismatch: expected ${EXPECTED_GATEWAY_AUTH_MODE}, got ${auth_mode}"
  [ "${allow_tailscale}" = "${EXPECTED_GATEWAY_ALLOW_TAILSCALE}" ] || fail \
    "gateway allowTailscale mismatch: expected ${EXPECTED_GATEWAY_ALLOW_TAILSCALE}, got ${allow_tailscale}"

  log "[gate] conservative topology verified (bind=${bind_mode}, auth=${auth_mode}, allowTailscale=${allow_tailscale})"
}

run_gateway_probe_gate() {
  probe_json=""
  if ! probe_json="$(openclaw gateway probe --json 2>&1)"; then
    fail "gateway probe command failed: ${probe_json}"
  fi
  probe_fields="$(
    printf '%s' "${probe_json}" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
ok = payload.get("ok")
capability = payload.get("capability")
normalized = str(capability or "").strip().lower().replace("_", "-")
print(f"{str(bool(ok)).lower()}\t{normalized}")
'
  )"
  probe_ok="$(printf '%s' "${probe_fields}" | awk -F '\t' '{print $1}')"
  probe_capability="$(printf '%s' "${probe_fields}" | awk -F '\t' '{print $2}')"

  [ "${probe_ok}" = "true" ] || fail "gateway probe not reachable/admin-ready (ok=${probe_ok})"
  [ "${probe_capability}" = "admin-capable" ] || fail \
    "gateway probe capability mismatch: expected admin-capable, got ${probe_capability}"

  log "[gate] gateway probe reachable/admin-capable"
}

run_hooks_gate() {
  hooks_output=""
  if ! hooks_output="$(openclaw hooks check 2>&1)"; then
    fail "hooks check command failed: ${hooks_output}"
  fi
  ready="$(printf '%s\n' "${hooks_output}" | awk -F ': ' '/^Ready:/ {print $2; exit}')"
  not_ready="$(printf '%s\n' "${hooks_output}" | awk -F ': ' '/^Not ready:/ {print $2; exit}')"
  [ "${ready:-}" = "4" ] || fail "hooks check Ready count mismatch: expected 4, got ${ready:-missing}"
  [ "${not_ready:-}" = "0" ] || fail "hooks check Not ready count mismatch: expected 0, got ${not_ready:-missing}"
  log "[gate] hooks check Ready=4 Not ready=0"
}

run_preflight_gates() {
  run_gateway_probe_gate
  run_hooks_gate
}

run_state_hygiene() {
  log "[hygiene] openclaw tasks maintenance --apply"
  openclaw tasks maintenance --apply
  log "[hygiene] openclaw sessions cleanup --all-agents --enforce --fix-missing"
  openclaw sessions cleanup --all-agents --enforce --fix-missing
}

capture_log_snapshot() {
  snapshot_path="$1"
  : >"${snapshot_path}"
  for path in /tmp/openclaw/openclaw-*.log; do
    [ -f "${path}" ] || continue
    lines="$(wc -l < "${path}" | tr -d ' ')"
    printf '%s\t%s\n' "${path}" "${lines}" >>"${snapshot_path}"
  done
}

scan_new_relay_errors() {
  snapshot_path="$1"
  output_path="$2"
  python3 - "${snapshot_path}" "${output_path}" "${RELAY_PATTERN}" <<'PY'
import glob
import re
import sys
from pathlib import Path

snapshot_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
pattern = re.compile(sys.argv[3], re.IGNORECASE)
baseline: dict[str, int] = {}

if snapshot_path.exists():
    for raw in snapshot_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        path, count = raw.split("\t", 1)
        try:
            baseline[path] = int(count)
        except ValueError:
            baseline[path] = 0

hits: list[str] = []
for path in sorted(glob.glob("/tmp/openclaw/openclaw-*.log")):
    start_line = baseline.get(path, 0)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle, start=1):
                if index <= start_line:
                    continue
                if pattern.search(line):
                    hits.append(f"{path}:{index}:{line.rstrip()}")
    except FileNotFoundError:
        continue

output_path.write_text("\n".join(hits), encoding="utf-8")
sys.exit(3 if hits else 0)
PY
}

run_relay_canary_and_scan() {
  snapshot_path="$(mktemp /tmp/openclaw-relay-snapshot.XXXXXX)"
  relay_hits_path="$(mktemp /tmp/openclaw-relay-hits.XXXXXX)"
  canary_out_path="$(mktemp /tmp/openclaw-canary.XXXXXX)"

  capture_log_snapshot "${snapshot_path}"

  if ! openclaw agent \
    --agent "${CANARY_AGENT_ID}" \
    --message "${CANARY_MESSAGE}" \
    --thinking low \
    --timeout "${CANARY_TIMEOUT_SECONDS}" \
    --json >"${canary_out_path}" 2>&1; then
    log "[canary] command failed; tail follows:"
    tail -n 40 "${canary_out_path}" >&2 || true
    rm -f "${snapshot_path}" "${relay_hits_path}" "${canary_out_path}"
    return 1
  fi

  if ! scan_new_relay_errors "${snapshot_path}" "${relay_hits_path}"; then
    log "[canary] relay error detected in newly appended log lines:"
    cat "${relay_hits_path}" >&2 || true
    rm -f "${snapshot_path}" "${relay_hits_path}" "${canary_out_path}"
    return 2
  fi

  log "[canary] agent path healthy and no new relay errors"
  rm -f "${snapshot_path}" "${relay_hits_path}" "${canary_out_path}"
  return 0
}

attempt_recovery() {
  log "[recovery] restarting gateway after canary/relay failure"
  openclaw gateway restart

  # Required: run a real canary and relay scan after each restart.
  run_preflight_gates

  if run_relay_canary_and_scan; then
    log "[recovery] post-restart canary succeeded"
    return 0
  fi

  rc="$?"
  if [ "${rc}" -eq 2 ]; then
    fail "relay errors persisted after restart; failing closed"
  fi
  fail "canary failed after restart; failing closed"
}

run_preflight_gates
run_topology_gate
run_version_gate
run_state_hygiene

if ! run_relay_canary_and_scan; then
  attempt_recovery
fi

runner_rc=0
python3 scripts/cos/guarded_packet_runner.py --once || runner_rc=$?

supervisor_rc=0
python3 scripts/cos/queue_supervisor.py || supervisor_rc=$?

if [ "${runner_rc}" -ne 0 ]; then
  exit "${runner_rc}"
fi

if [ "${supervisor_rc}" -ne 0 ]; then
  exit "${supervisor_rc}"
fi

exit 0
