#!/usr/bin/env bash
set -u

status=0

section() {
  printf '\n## %s\n\n' "$1"
}

section "Listener Check"

printf -- "- Timestamp: %s\n" "$(date -Is)"

if ! command -v ss >/dev/null 2>&1; then
  printf -- "- finding: WATCH ss not found\n"
  exit 1
fi

listeners="$(ss -ltnp 2>&1)"
printf '%s\n' "$listeners"

section "Exposure Findings"

if printf '%s\n' "$listeners" | grep -Eq '(^|[[:space:]])0\.0\.0\.0:22([[:space:]]|$)|(^|[[:space:]])\[::\]:22([[:space:]]|$)'; then
  printf -- "- HIGH ssh listens on all IPv4 or IPv6 interfaces\n"
  status=2
else
  printf -- "- OK ssh all-interface listener not detected\n"
fi

if printf '%s\n' "$listeners" | grep -Eq '(^|[[:space:]])0\.0\.0\.0:|(^|[[:space:]])\[::\]:'; then
  printf -- "- WATCH at least one all-interface listener exists; review raw listener table above\n"
  status=$(( status < 1 ? 1 : status ))
fi

if printf '%s\n' "$listeners" | grep -Eq '127\.0\.0\.1:18800'; then
  printf -- "- MEDIUM Chrome CDP listener present on loopback 127.0.0.1:18800\n"
  status=$(( status < 1 ? 1 : status ))
fi

gateway_count="$(printf '%s\n' "$listeners" | grep -Ec '127\.0\.0\.1:(18789|19789)')"
if [[ "$gateway_count" -gt 1 ]]; then
  printf -- "- MEDIUM multiple OpenClaw gateway listeners detected on loopback\n"
  status=$(( status < 1 ? 1 : status ))
else
  printf -- "- OK duplicate OpenClaw gateway listener pattern not detected\n"
fi

section "Tailscale Serve"
if command -v tailscale >/dev/null 2>&1; then
  tailscale serve status 2>&1 || {
    printf -- "- WATCH tailscale serve status failed or is sandbox-limited\n"
    status=$(( status < 1 ? 1 : status ))
  }
else
  printf -- "- WATCH tailscale not found on PATH\n"
fi

exit "$status"
