#!/usr/bin/env bash
set -u

ROOTS=(
  "$HOME/.codex"
  "$HOME/.openclaw"
  "$PWD"
)

status=0

section() {
  printf '\n## %s\n\n' "$1"
}

section "Secret Pattern Scan"

printf -- "- Timestamp: %s\n" "$(date -Is)"
printf -- "- Mode: redacted file-path scan; matching secret values are not printed\n"

if ! command -v rg >/dev/null 2>&1; then
  printf -- "- finding: WATCH rg not found\n"
  exit 1
fi

scan_pattern='BW_SESSION|OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN|GH_TOKEN|NPM_TOKEN|OPENCLAW_GATEWAY_PASSWORD|BEGIN OPENSSH PRIVATE KEY|BEGIN RSA PRIVATE KEY|client_secret|refresh_token|access_token'

mapfile -t hits < <(
  rg -l "$scan_pattern" "${ROOTS[@]}" \
    -g '!node_modules' \
    -g '!dist' \
    -g '!build' \
    -g '!docs/security/**' \
    -g '!scripts/security/**' \
    2>/dev/null | sort -u
)

if [[ "${#hits[@]}" -eq 0 ]]; then
  printf -- "- finding: OK no configured secret patterns found in scanned roots\n"
  exit 0
fi

printf -- "- finding: MEDIUM secret-like patterns found in %s files\n" "${#hits[@]}"
printf -- "- note: paths only; no values printed\n\n"

printf -- "### Counts by Area\n\n"
for prefix in "$HOME/.codex" "$HOME/.openclaw" "$PWD"; do
  count="$(printf '%s\n' "${hits[@]}" | grep -c "^$prefix" || true)"
  printf -- "- %s: %s\n" "$prefix" "$count"
done

printf -- "\n### Sample Paths\n\n"
sample_limit="${SAMPLE_LIMIT:-80}"
sample_count=0
for path in "${hits[@]}"; do
  if [[ "$sample_count" -ge "$sample_limit" ]]; then
    break
  fi
  printf -- "- %s\n" "$path"
  sample_count=$((sample_count + 1))
done

if [[ "${#hits[@]}" -gt "$sample_limit" ]]; then
  printf -- "\n- note: %s additional paths omitted; rerun with SAMPLE_LIMIT=<n> for more\n" "$((${#hits[@]} - sample_limit))"
fi

status=1

if printf '%s\n' "${hits[@]}" | grep -q '/shell_snapshots/'; then
  printf '\n- finding: MEDIUM shell snapshots contain secret-like patterns; targeted redaction recommended\n'
fi

exit "$status"
