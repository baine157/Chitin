#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORT_DIR="${1:-$ROOT_DIR/docs/security/reports}"
STAMP="$(date +%Y%m%dT%H%M%S%z)"
REPORT="$REPORT_DIR/z420-weekly-deep-check-$STAMP.md"

mkdir -p "$REPORT_DIR"

overall=0

run_section() {
  local title="$1"
  shift

  {
    printf '\n# %s\n\n' "$title"
    printf -- "_Command:_ \`%s\`\n\n" "$*"
  } >>"$REPORT"

  "$@" >>"$REPORT" 2>&1
  local code=$?

  {
    printf '\n_Command exit code:_ `%s`\n' "$code"
  } >>"$REPORT"

  if [[ "$code" -gt "$overall" ]]; then
    overall="$code"
  fi
}

{
  printf '# Z420 Weekly Deep Security Check\n\n'
  printf -- "- Timestamp: %s\n" "$(date -Is)"
  printf -- "- Host: %s\n" "$(hostname)"
  printf -- "- Repo: %s\n" "$ROOT_DIR"
  printf -- "- Mode: report-only; no remediation attempted\n"
} >"$REPORT"

run_section "Host Context" uname -a
run_section "OpenClaw Status" openclaw status
run_section "OpenClaw Deep Security Audit" openclaw security audit --deep
run_section "OpenClaw Update Status" openclaw update status
run_section "Known-Bad Packages" "$ROOT_DIR/scripts/security/z420-known-bad-packages.sh"
run_section "Listeners" "$ROOT_DIR/scripts/security/z420-listener-check.sh"
run_section "Secret Pattern Scan" "$ROOT_DIR/scripts/security/z420-secret-pattern-scan.sh"
run_section "User Crontab" crontab -l

if command -v systemctl >/dev/null 2>&1; then
  run_section "User Services" systemctl --user list-units --type=service --state=running
fi

{
  printf '\n# Result\n\n'
  printf -- '- Overall exit code: `%s`\n' "$overall"
  if [[ "$overall" -eq 0 ]]; then
    printf -- "- Status: OK\n"
  elif [[ "$overall" -eq 1 ]]; then
    printf -- "- Status: WATCH\n"
  else
    printf -- "- Status: HIGH\n"
  fi
  printf -- "- Report path: %s\n" "$REPORT"
} >>"$REPORT"

printf '%s\n' "$REPORT"
exit "$overall"
