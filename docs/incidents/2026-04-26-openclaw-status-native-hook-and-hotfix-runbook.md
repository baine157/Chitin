# 2026-04-26 OpenClaw Status + Native Hook Relay Runbook

## Summary

Two related operator pain points surfaced on April 26, 2026:

1. `openclaw status` looked hung or took too long in normal operation.
2. native hook relay intermittently failed in-session with:
   `Native hook relay unavailable` and `native hook relay not found`.

The high-noise status issue and relay instability are not identical root causes, but they often appeared together during the same recovery window.

This runbook captures a repeatable fix and verification path.

## What Was Changed

A live patch was applied to the OpenClaw status bundle in the installed runtime:

- target file pattern: `.../openclaw/dist/status.scan-*.js`
- current host target at incident time:
  `/home/baine/.npm-global/lib/node_modules/openclaw/dist/status.scan-Cjg5VwTu.js`

Patch behavior:

- for non-`--all` status calls:
  - skip expensive memory snapshot probing
  - skip channel data/summary expansion
  - skip plugin compatibility snapshot
- for `--all`:
  - keep full heavy diagnostics behavior

This preserves deep debug behavior while making routine status usable.

## Durable Workflow Added

Two scripts now exist in `orchestrator`:

- `scripts/observability/openclaw-status-hotfix.sh`
- `scripts/observability/openclaw-update-with-status-hotfix.sh`

`openclaw-status-hotfix.sh` supports:

- `apply` (default): idempotent patch + backup
- `verify`: patch marker checks + runtime probes
- `show-target`: print resolved dist and bundle paths
- `revert`: restore latest pre-hotfix backup

`openclaw-update-with-status-hotfix.sh` runs:

1. `openclaw update ...`
2. hotfix `apply`
3. hotfix `verify`

Use this wrapper for future updates so the fix survives version bumps.

## Standard Update Procedure

Run from `/home/baine/openclaw/orchestrator`:

```sh
scripts/observability/openclaw-update-with-status-hotfix.sh --yes
```

Or pin a tag:

```sh
scripts/observability/openclaw-update-with-status-hotfix.sh --tag <version> --yes
```

## Manual Repair Procedure

If status gets slow/hung again after an update:

```sh
scripts/observability/openclaw-status-hotfix.sh show-target
scripts/observability/openclaw-status-hotfix.sh apply
scripts/observability/openclaw-status-hotfix.sh verify
```

Verification artifacts are written to:

- `/tmp/openclaw-status-hotfix-verify-status.txt`
- `/tmp/openclaw-status-hotfix-verify-status-json.txt`
- `/tmp/openclaw-status-hotfix-verify-hooks.txt`
- `/tmp/openclaw-status-hotfix-verify-gateway-probe.txt`
- `/tmp/openclaw-status-hotfix-verify-gateway-health.txt`

Verifier semantics:

- strict gates: `status text`, `status json`, `hooks check`
- soft gates (warn-only): `gateway probe`, `gateway health`

Gateway checks are soft because this host can intermittently return loopback `EPERM`/abnormal-closure during transient restart windows even when the status hotfix itself is healthy.

## Native Hook Relay Triage

When operator reports `Native hook relay unavailable`:

1. Check control plane reachability:
```sh
openclaw gateway probe
openclaw gateway health
openclaw hooks check
```
2. Check recent relay errors in latest OpenClaw log:
```sh
LATEST_LOG="$(ls -1t /tmp/openclaw/openclaw-*.log | head -n 1)"
rg -n "native hook relay not found|Native hook relay unavailable|relay unavailable" "${LATEST_LOG}"
```
3. Run the local write-path canary:
```sh
python3 scripts/observability/native_hook_write_canary.py
python3 scripts/observability/collect_dashboard.py --check
```
4. If this exact Telegram session must be trusted for host-mutating work, run the live-session smoke from Telegram:
```sh
python3 scripts/observability/live_session_native_hook_smoke.py --execution-origin telegram-live-session
python3 scripts/observability/collect_dashboard.py --check
```
5. Treat gateway health as necessary but insufficient. A green gateway does not prove that a stale Telegram session can invoke native hooks.
6. If errors are historical only, probes are green, and the canary is fresh/ok, terminal-local execution can resume; live Telegram-session execution still needs the live-session smoke above if that path matters.
7. If errors are current and commands block, recover from a fresh session/runtime first, then re-run probes and both canaries.

## Native Hook Repair Playbook

Use this order for stale Telegram/native-hook relay failures:

1. Try `/new` or `/reset` in the affected Telegram session to escape stale session state.
2. Re-run the local native-hook/write-path canary:
```sh
python3 scripts/observability/native_hook_write_canary.py
```
3. Re-run the live-session smoke from the exact Telegram session:
```sh
python3 scripts/observability/live_session_native_hook_smoke.py --execution-origin telegram-live-session
```
4. If the live Telegram path is still broken, restart the OpenClaw gateway from a host terminal.
5. Re-run gateway health, the local native-hook/write-path canary, and the live-session smoke:
```sh
openclaw gateway health
python3 scripts/observability/native_hook_write_canary.py
python3 scripts/observability/live_session_native_hook_smoke.py --execution-origin telegram-live-session
```
6. Only then resume host-mutating Telegram tasks.

Do not claim native-hook health from gateway health alone. The terminal canary proves local file write/read/remove capability only; it cannot prove that a specific live Telegram session's native-hook relay is healthy. A terminal run of `live_session_native_hook_smoke.py` is also not a live-session pass unless the JSON records `execution_origin: telegram-live-session`.

## Rollback

If patch behavior regresses:

```sh
scripts/observability/openclaw-status-hotfix.sh revert
```

Then run:

```sh
openclaw status --timeout 3000
openclaw status --json --timeout 3000
```

## Expected Runtime Behavior (Current Host)

- `openclaw status --timeout 3000`: about 10-15s
- `openclaw status --json --timeout 3000`: about 10-12s
- `openclaw status --all --timeout 3000`: can still be heavy (about 50-60s)

If default status returns to long stalls while `--all` is unchanged, re-apply the hotfix first before deeper runtime speculation.
