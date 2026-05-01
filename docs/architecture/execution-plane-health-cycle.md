# Execution Plane Health Cycle

## Purpose

Keep OpenClaw execution reliability observable without flattening several
different facts into one "OpenClaw is up" claim.

This cycle is the bounded stability check for the machine execution plane. It
is local-first, proof-bearing, and safe to run from the Z420 terminal.

## Command

```bash
cd /home/baine/openclaw/orchestrator
scripts/observability/execution_plane_health_cycle.sh
```

The cycle runs:

- `native_hook_write_canary.py`
- `execution_plane_smoke.py --include-agent-smoke --agent-timeout 180`
- `queue_supervisor.py --json`
- `collect_dashboard.py`

## Truth Split

The dashboard must keep these facts separate:

- Telegram CoS session liveness
- gateway reachability
- gateway diagnostic detail
- hook registry readiness
- native relay usability
- shell execution usability
- OpenClaw agent execution usability
- Codex terminal/session attach availability
- external-action verification availability

Gateway diagnostic detail can be `degraded` while the execution plane remains
usable. That is a watch condition, not proof that shell or agent execution is
blocked.

## Scheduling Guidance

Do not silently install a recurring agent-smoke timer without an explicit
operator decision, because the agent smoke uses model runtime. If scheduled,
prefer a low-frequency user timer such as every 6 to 12 hours and keep the
external-effect boundary local-only.

Suggested timer command:

```bash
cd /home/baine/openclaw/orchestrator
OPENCLAW_EXECUTION_HEALTH_AGENT_TIMEOUT=180 scripts/observability/execution_plane_health_cycle.sh
```

## Pass Condition

Treat the cycle as green when:

- execution substrate status is `ok`
- gateway is reachable
- hook registry is ready
- shell execution is usable
- OpenClaw agent execution is usable
- no fresh native-hook relay errors are seen
- external-action verification remains gated by explicit readback

## Fail-Closed Rule

If a Telegram session reports `Native hook relay unavailable`, do not keep
retrying from that stale session. Run this health cycle from the host terminal,
then rerun the live Telegram session smoke from the exact Telegram session
before claiming live-session relay recovery.
