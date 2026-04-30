#!/usr/bin/env sh
set -eu

SCRIPT_NAME="$(basename "$0")"
MODE="${1:-apply}"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

resolve_dist_dir() {
  if [ -n "${OPENCLAW_DIST_DIR:-}" ]; then
    [ -d "${OPENCLAW_DIST_DIR}" ] || fail "OPENCLAW_DIST_DIR does not exist: ${OPENCLAW_DIST_DIR}"
    printf '%s\n' "${OPENCLAW_DIST_DIR}"
    return 0
  fi

  npm_root="$(npm root -g 2>/dev/null || true)"
  if [ -n "${npm_root}" ] && [ -d "${npm_root}/openclaw/dist" ]; then
    printf '%s\n' "${npm_root}/openclaw/dist"
    return 0
  fi

  for candidate in \
    "/home/baine/.npm-global/lib/node_modules/openclaw/dist" \
    "/usr/local/lib/node_modules/openclaw/dist" \
    "/usr/lib/node_modules/openclaw/dist"
  do
    if [ -d "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  fail "Could not locate openclaw dist directory"
}

resolve_target_file() {
  dist_dir="$1"
  target="$(
    find "${dist_dir}" -maxdepth 1 -type f -name 'status.scan-*.js' \
      ! -name 'status.scan-overview-*' \
      ! -name 'status.scan.deps.runtime*' \
      ! -name 'status.scan.fast-json-*' \
      ! -name 'status.scan.runtime-*' \
      | sort \
      | head -n 1
  )"
  [ -n "${target}" ] || fail "Could not locate status.scan bundle under ${dist_dir}"
  printf '%s\n' "${target}"
}

is_target_patched() {
  target="$1"

  if ! rg -q 'includeChannelsData: opts\.all === true' "${target}"; then
    return 1
  fi

  if ! rg -q 'summary: \{ includeChannelSummary: opts\.all === true \}' "${target}"; then
    return 1
  fi

  if ! rg -q 'pluginCompatibility = opts\.all === true \? buildPluginCompatibilitySnapshotNotices' "${target}"; then
    return 1
  fi

  memory_guard_count="$(rg -c 'opts\.all \? await resolveStatusMemoryStatusSnapshot' "${target}")"
  if [ "${memory_guard_count}" -lt 2 ]; then
    return 1
  fi

  return 0
}

patch_target() {
  target="$1"

  if is_target_patched "${target}"; then
    log "already patched: ${target}"
    return 0
  fi

  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="${target}.pre-status-hotfix-${stamp}.bak"
  cp "${target}" "${backup}"

  TARGET_PATH="${target}" node <<'NODE'
const fs = require("fs");

const target = process.env.TARGET_PATH;
if (!target) throw new Error("TARGET_PATH not set");

let text = fs.readFileSync(target, "utf8");
const before = text;

const memoryPattern =
  /resolveMemory:\s*async\s*\(\{\s*cfg,\s*agentStatus,\s*memoryPlugin\s*\}\)\s*=>\s*await\s*resolveStatusMemoryStatusSnapshot\(\{\s*cfg,\s*agentStatus,\s*memoryPlugin\s*\}\)/g;
text = text.replace(
  memoryPattern,
  "resolveMemory: async ({ cfg, agentStatus, memoryPlugin }) => opts.all ? await resolveStatusMemoryStatusSnapshot({\n\t\t\tcfg,\n\t\t\tagentStatus,\n\t\t\tmemoryPlugin\n\t\t}) : null"
);

if (!/includeChannelsData:\s*opts\.all === true/.test(text)) {
  text = text.replace(
    /progress,\n(\s*)labels:/,
    "progress,\n$1includeChannelsData: opts.all === true,\n$1labels:"
  );
}

if (!/pluginCompatibility\s*=\s*opts\.all === true \? buildPluginCompatibilitySnapshotNotices/.test(text)) {
  text = text.replace(
    /const pluginCompatibility = buildPluginCompatibilitySnapshotNotices\(\{ config: overview\.cfg \}\);/,
    "const pluginCompatibility = opts.all === true ? buildPluginCompatibilitySnapshotNotices({ config: overview.cfg }) : [];"
  );
}

if (!/summary:\s*\{\s*includeChannelSummary:\s*opts\.all === true\s*\}/.test(text)) {
  text = text.replace(
    /overview,\n(\s*)resolveMemory:/,
    "overview,\n$1summary: { includeChannelSummary: opts.all === true },\n$1resolveMemory:"
  );
}

const checks = [
  [/includeChannelsData:\s*opts\.all === true/, "includeChannelsData guard"],
  [/summary:\s*\{\s*includeChannelSummary:\s*opts\.all === true\s*\}/, "summary guard"],
  [/pluginCompatibility\s*=\s*opts\.all === true \? buildPluginCompatibilitySnapshotNotices/, "pluginCompatibility guard"]
];
for (const [re, label] of checks) {
  if (!re.test(text)) {
    throw new Error(`missing expected patch segment: ${label}`);
  }
}

const memoryGuardCount = (text.match(/opts\.all \? await resolveStatusMemoryStatusSnapshot/g) || []).length;
if (memoryGuardCount < 2) {
  throw new Error(`expected at least 2 memory guards, found ${memoryGuardCount}`);
}

if (text === before) {
  throw new Error("no changes written; expected to patch unmodified file");
}

fs.writeFileSync(target, text);
NODE

  log "backup created: ${backup}"
  log "patched file: ${target}"
}

verify_target_and_runtime() {
  target="$1"

  if ! is_target_patched "${target}"; then
    fail "target is not patched: ${target}"
  fi

  log "patch markers present in: ${target}"
  log "running runtime verification (status, json, hooks, gateway)..."

  run_probe strict "status text" "/tmp/openclaw-status-hotfix-verify-status.txt" openclaw status --timeout 3000
  run_probe strict "status json" "/tmp/openclaw-status-hotfix-verify-status-json.txt" openclaw status --json --timeout 3000
  run_probe strict "hooks check" "/tmp/openclaw-status-hotfix-verify-hooks.txt" openclaw hooks check
  run_probe soft "gateway probe" "/tmp/openclaw-status-hotfix-verify-gateway-probe.txt" openclaw gateway probe
  run_probe soft "gateway health" "/tmp/openclaw-status-hotfix-verify-gateway-health.txt" openclaw gateway health

  log "verification outputs:"
  log "  /tmp/openclaw-status-hotfix-verify-status.txt"
  log "  /tmp/openclaw-status-hotfix-verify-status-json.txt"
  log "  /tmp/openclaw-status-hotfix-verify-hooks.txt"
  log "  /tmp/openclaw-status-hotfix-verify-gateway-probe.txt"
  log "  /tmp/openclaw-status-hotfix-verify-gateway-health.txt"
  log "verification complete"
}

run_probe() {
  probe_mode="$1"
  probe_name="$2"
  out_file="$3"
  shift 3

  log "probe start: ${probe_name}"
  if timeout 70s "$@" >"${out_file}" 2>&1; then
    log "probe ok: ${probe_name}"
    return 0
  else
    rc="$?"
  fi

  if [ "${probe_mode}" = "soft" ]; then
    log "probe warn: ${probe_name} (exit ${rc})"
  else
    log "probe failed: ${probe_name} (exit ${rc})"
  fi

  if [ -f "${out_file}" ]; then
    log "last lines from ${out_file}:"
    tail -n 40 "${out_file}" >&2 || true
  fi

  if [ "${probe_mode}" = "soft" ]; then
    return 0
  fi

  fail "runtime verification failed during '${probe_name}'"
}

revert_target_from_backup() {
  target="$1"
  latest_backup="$(
    ls -1t "${target}".pre-status-hotfix-*.bak 2>/dev/null | head -n 1 || true
  )"

  [ -n "${latest_backup}" ] || fail "no backup found for ${target}"

  cp "${latest_backup}" "${target}"
  log "reverted ${target} from ${latest_backup}"
}

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [apply|verify|show-target|revert]

Modes:
  apply       Apply idempotent status hotfix to the active openclaw dist bundle.
  verify      Verify patch markers and run runtime probes.
  show-target Print resolved openclaw dist dir and status.scan bundle path.
  revert      Restore latest pre-hotfix backup for the bundle.

Environment:
  OPENCLAW_DIST_DIR   Optional override for openclaw dist directory.
EOF
}

dist_dir="$(resolve_dist_dir)"
target_file="$(resolve_target_file "${dist_dir}")"

case "${MODE}" in
  apply)
    patch_target "${target_file}"
    ;;
  verify)
    verify_target_and_runtime "${target_file}"
    ;;
  show-target)
    log "dist dir: ${dist_dir}"
    log "target:   ${target_file}"
    ;;
  revert)
    revert_target_from_backup "${target_file}"
    ;;
  *)
    usage
    exit 2
    ;;
esac
