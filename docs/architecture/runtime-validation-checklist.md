# Runtime Validation Checklist

## Purpose

Prevent false stability claims where OpenClaw services are reachable but BearClaw behavior has drifted.

Use this checklist after:

- prompt or system contract changes
- OpenClaw runtime upgrades
- session-store cleanup
- gateway restart
- security posture changes
- connector or skill changes that affect orchestration
- native-hook relay failures or repair work

## Required Gates

### 1. Config Gate

Command:

```text
openclaw config validate
```

Pass condition:

- active config parses successfully
- expected config path is used

Fail condition:

- invalid JSON or schema
- unexpected config path

### 2. Gateway Gate

Commands:

```text
openclaw gateway health
openclaw status --deep
```

Pass condition:

- gateway reachable
- Telegram OK when Telegram behavior is in scope
- no critical runtime health failure

Fail condition:

- gateway unavailable
- Telegram unavailable when Telegram behavior is in scope
- deep status reports active task/run instability

### 3. Security Gate

Command:

```text
openclaw security audit --deep
```

Pass condition:

- 0 critical findings
- remaining warnings are understood and acceptable for current trust model

Fail condition:

- any critical finding
- new warning that widens external exposure or tool blast radius

### 4. Session Gate

Command:

```text
openclaw sessions --all-agents --json
```

Pass condition:

- primary operator-facing sessions are under context budget
- contaminated smoke-test sessions are reset before retesting
- session cleanup dry-run has no unexpected destructive plan

Fail condition:

- primary direct session is over budget
- smoke test reuses a stale session after prompt change
- missing transcript entries accumulate without cleanup

### 5. Behavior Gate

Run one live, non-delivered planning-only agent turn.

Expected input shape:

```text
Planning only. Do not launch coding work. Reply in BearClaw private-DM orchestration format only. Objective: evaluate a bounded orchestration question. No shell. No file edits.
```

Pass condition:

- first line is exactly `Disposition: hold`
- no tools or coding work are launched
- no queue/watch/parked/uppercase disposition labels appear

Fail condition:

- `QUEUED_FOR_PLANNING_ONLY` or any non-contract disposition appears
- planning-only request starts execution
- runtime failure is surfaced as vague environment commentary

### 6. Execution-Plane Smoke Gate

Command:

```text
scripts/observability/execution_plane_health_cycle.sh
```

Equivalent expanded form:

```text
python3 scripts/observability/native_hook_write_canary.py
python3 scripts/observability/execution_plane_smoke.py --include-agent-smoke --agent-timeout 180
python3 scripts/cos/queue_supervisor.py --json
python3 scripts/observability/collect_dashboard.py
```

Pass condition:

- smoke result JSON parses at `state/observability/execution-plane-smoke.json`
- gateway signal is `ok`
- hooks registry signal is `ok`
- shell execution signal is `ok`
- OpenClaw agent execution signal is `ok` when the agent smoke is in scope
- external-action verification is reported as usable only with explicit readback
- dashboard exposes `control_plane_vs_execution_plane`
- gateway diagnostic detail is represented separately from gateway reachability

Fail condition:

- shell execution is blocked, failed, or unverified
- OpenClaw agent execution is blocked, failed, or times out when in scope
- gateway or hook registry status is treated as proof of shell or agent execution
- gateway diagnostic detail timeout is treated as proof that machine execution is blocked when shell and agent smokes are green
- `Native hook relay unavailable`, `native hook relay not found`, or `relay unavailable` appears in fresh evidence

Limit:

- This proves the machine execution plane from terminal-local context.
- It does not prove that the exact live Telegram session can attach to that plane.

### 7. Relay Repair Gate

Command:

```text
python3 scripts/observability/repair_openclaw_relay.py --include-agent-smoke --agent-timeout 180
```

Pass condition:

- repair artifact parses at `state/observability/openclaw-relay-repair.json`
- stale task/session cleanup commands complete
- gateway restart succeeds
- gateway probe succeeds using configured gateway auth
- `openclaw hooks check` reports `Ready: 4` and `Not ready: 0`
- optional agent smoke returns `OK`
- fresh OpenClaw logs show zero new native-hook relay errors

Fail condition:

- repair cannot restart or probe the gateway
- hook registry remains not ready
- agent smoke fails when included
- fresh logs include relay-unavailable errors after repair

### 8. Native-Hook / Write-Path Canary Gate

Command:

```text
python3 scripts/observability/native_hook_write_canary.py
python3 scripts/observability/collect_dashboard.py --check
```

Pass condition:

- canary result JSON parses
- `status` is `ok` for `native_hook_write_path`
- result records `external_effect.occurred: false`
- dashboard represents gateway health as necessary but insufficient
- dashboard keeps `telegram_session_native_hook` separate from the terminal-local canary

Fail condition:

- canary reports `blocked`, `degraded`, or `error`
- canary result is missing, stale, or has an invalid timestamp
- native-hook relay is claimed healthy from gateway status alone
- `Native hook relay unavailable`, `native hook relay not found`, or `relay unavailable` appears in fresh evidence

Limit:

- This terminal-local canary proves only local write/read/remove execution substrate.
- It does not prove a live Telegram session native-hook relay; a live-session canary is a separate check.

### 9. Live Telegram Session Native-Hook Smoke Gate

Manual packet to run from the exact Telegram session being tested:

```text
Run this local-only smoke and report the resulting JSON path. Do not touch credentials, browser, portal, Bitwarden, MFA, tokens, cookies, passwords, submit, send, upload, attest, sign, certify, or finalize.

cd /home/baine/openclaw/orchestrator
python3 scripts/observability/live_session_native_hook_smoke.py --execution-origin telegram-live-session
python3 scripts/observability/collect_dashboard.py --check
```

Pass condition:

- the smoke command executes from the live Telegram session
- result JSON parses at `state/observability/live-session-native-hook-smoke.json`
- `execution_origin` is `telegram-live-session`
- `status` is `ok`
- result records `external_effect.occurred: false`
- dashboard shows live-session native-hook smoke fresh/ok separately from gateway health

Fail condition:

- Telegram reports `Native hook relay unavailable`, `native hook relay not found`, or `relay unavailable`
- result is missing, stale, invalid, or terminal-origin only
- `execution_origin` is not `telegram-live-session`
- dashboard marks gateway health as proof of live native-hook health

Limit:

- This is a trivial host-mutating file smoke only.
- It proves that the exact Telegram session can perform one safe local write/read/remove action; it does not approve credentials, browser, portal, or external commits.

## Closeout Format

Use this compact closeout:

```text
Runtime validation:
- config: pass|fail
- gateway: pass|fail
- security: pass|fail
- sessions: pass|fail
- behavior: pass|fail
- execution-plane smoke: pass|fail|unverified
- relay repair: pass|fail|unverified
- native-hook/write canary: pass|fail|unverified
- live Telegram native-hook smoke: pass|fail|unverified
- residual risk:
```

Do not report runtime stability as `DONE` if any gate is unverified.
