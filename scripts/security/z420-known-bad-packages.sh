#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

status=0

section() {
  printf '\n## %s\n\n' "$1"
}

section "Known-Bad Package Scan"

printf -- "- Repo: %s\n" "$ROOT_DIR"
printf -- "- Timestamp: %s\n" "$(date -Is)"

section "Bitwarden CLI"

if command -v bw >/dev/null 2>&1; then
  bw_path="$(command -v bw)"
  printf -- "- bw path: %s\n" "$bw_path"
  if bw_version="$(bw --version 2>/dev/null)"; then
    printf -- "- bw version: %s\n" "$bw_version"
    if [[ "$bw_version" == "2026.4.0" ]]; then
      printf -- "- finding: HIGH known-bad @bitwarden/cli 2026.4.0 detected\n"
      status=2
    else
      printf -- "- finding: OK known-bad @bitwarden/cli 2026.4.0 not detected by bw --version\n"
    fi
  else
    printf -- "- finding: WATCH bw exists but direct version check failed\n"
    package_json="$(npm root -g 2>/dev/null)/@bitwarden/cli/package.json"
    if [[ -f "$package_json" ]]; then
      package_version="$(node -e 'console.log(require(process.argv[1]).version)' "$package_json" 2>/dev/null || true)"
      if [[ -n "$package_version" ]]; then
        printf -- "- package.json version: %s\n" "$package_version"
        if [[ "$package_version" == "2026.4.0" ]]; then
          printf -- "- finding: HIGH known-bad @bitwarden/cli 2026.4.0 detected by package.json\n"
          status=2
        else
          printf -- "- finding: OK known-bad @bitwarden/cli 2026.4.0 not detected by package.json\n"
        fi
      else
        status=$(( status < 1 ? 1 : status ))
      fi
    else
      status=$(( status < 1 ? 1 : status ))
    fi
  fi
else
  printf -- "- finding: WATCH bw not found on PATH\n"
fi

if command -v npm >/dev/null 2>&1; then
  section "Global npm Inventory"
  npm ls -g --depth=0 2>&1 | sed -E 's/[[:space:]]+$//'
  if npm ls -g @bitwarden/cli --depth=0 2>/dev/null | grep -q '@bitwarden/cli@2026\.4\.0'; then
    printf '\n- finding: HIGH global npm has known-bad @bitwarden/cli@2026.4.0\n'
    status=2
  fi
else
  section "Global npm Inventory"
  printf -- "- finding: WATCH npm not found on PATH\n"
fi

section "OpenClaw Update Status"
if command -v openclaw >/dev/null 2>&1; then
  openclaw update status 2>&1 || {
    printf -- "\n- finding: WATCH openclaw update status failed\n"
    status=$(( status < 1 ? 1 : status ))
  }
else
  printf -- "- finding: WATCH openclaw not found on PATH\n"
fi

section "APT Upgrades"
if command -v apt >/dev/null 2>&1; then
  apt list --upgradable 2>/dev/null || {
    printf -- "- finding: WATCH apt upgradable check failed\n"
    status=$(( status < 1 ? 1 : status ))
  }
else
  printf -- "- finding: WATCH apt not found\n"
fi

exit "$status"
