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

## Closeout Format

Use this compact closeout:

```text
Runtime validation:
- config: pass|fail
- gateway: pass|fail
- security: pass|fail
- sessions: pass|fail
- behavior: pass|fail
- residual risk:
```

Do not report runtime stability as `DONE` if any gate is unverified.
