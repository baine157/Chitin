#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
HOTFIX_SCRIPT="${SCRIPT_DIR}/openclaw-status-hotfix.sh"

if [ ! -x "${HOTFIX_SCRIPT}" ]; then
  printf 'ERROR: hotfix script is missing or not executable: %s\n' "${HOTFIX_SCRIPT}" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- --yes
fi

printf 'Running openclaw update with args: %s\n' "$*"
openclaw update "$@"

printf 'Re-applying status hotfix...\n'
"${HOTFIX_SCRIPT}" apply

printf 'Verifying status hotfix...\n'
"${HOTFIX_SCRIPT}" verify

printf 'Done. openclaw update + status hotfix verification completed.\n'
