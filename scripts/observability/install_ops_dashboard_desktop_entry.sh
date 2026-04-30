#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"
LAUNCHER="${REPO_ROOT}/scripts/observability/launch_ops_dashboard_app.sh"
WRITE_DESKTOP_SHORTCUT=1

usage() {
  cat <<EOF
Usage: $(basename "$0") [--no-desktop-shortcut]

Installs:
  - ~/.local/share/applications/cos-ops-dashboard.desktop
  - ~/Desktop/CoS Ops Dashboard.desktop (unless disabled)
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --no-desktop-shortcut)
        WRITE_DESKTOP_SHORTCUT=0
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

ensure_launcher_executable() {
  [ -f "${LAUNCHER}" ] || fail "launcher not found: ${LAUNCHER}"
  chmod +x "${LAUNCHER}"
}

write_desktop_entry() {
  data_home="${XDG_DATA_HOME:-${HOME}/.local/share}"
  app_dir="${data_home}/applications"
  entry_path="${app_dir}/cos-ops-dashboard.desktop"

  mkdir -p "${app_dir}"

  cat >"${entry_path}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=CoS Ops Dashboard
Comment=Local Chief of Staff observability dashboard
Exec=${LAUNCHER}
Path=${REPO_ROOT}
Terminal=false
StartupNotify=true
Categories=Office;Utility;
Icon=utilities-system-monitor
EOF

  chmod 644 "${entry_path}"
  printf '%s\n' "${entry_path}"
}

write_desktop_shortcut() {
  entry_path="$1"
  desktop_dir="${HOME}/Desktop"
  shortcut_path="${desktop_dir}/CoS Ops Dashboard.desktop"

  mkdir -p "${desktop_dir}"
  cp "${entry_path}" "${shortcut_path}"
  chmod +x "${shortcut_path}"
  printf '%s\n' "${shortcut_path}"
}

main() {
  parse_args "$@"
  ensure_launcher_executable
  entry_path="$(write_desktop_entry)"

  printf 'installed app entry: %s\n' "${entry_path}"
  if [ "${WRITE_DESKTOP_SHORTCUT}" -eq 1 ]; then
    shortcut_path="$(write_desktop_shortcut "${entry_path}")"
    printf 'installed desktop shortcut: %s\n' "${shortcut_path}"
  fi

  printf 'double-click "CoS Ops Dashboard" to open it\n'
}

main "$@"
