# Queue Supervisor + SLA Alerts v0

## Purpose

Detect packet-queue degradation early and emit a compact operational contract that
can be forwarded to Chief of Staff while the principal is away.

## Runner

- `scripts/cos/queue_supervisor.py`

## Output Contract

The supervisor emits exactly one of:

- `QUEUE_SUPERVISOR_CLEAR`
- `QUEUE_SUPERVISOR_ALERT` plus compact fields:
  - `Item:`
  - `Status:`
  - `Need:`
  - `Boundary:`

## Baseline Behavior

On first run, it writes a baseline state file and returns clear. Historical setup
artifacts are not retro-alerted on the initialization run.

State file:

- `state/cos/packets/supervisor_state.json`

## Current SLA Checks

- queue depth above threshold (`--max-queue-depth`, default `20`)
- oldest queued packet age above threshold (`--queue-stale-minutes`, default `360`)
- blocked-packet spike since last run (`--blocked-new-threshold`, default `3`)
- non-empty queue with no processing progress for too long (`--processing-idle-minutes`, default `240`)

## Usage

```bash
sh -lc 'cd /home/baine/openclaw/orchestrator && python3 scripts/cos/queue_supervisor.py'
```

JSON mode:

```bash
sh -lc 'cd /home/baine/openclaw/orchestrator && python3 scripts/cos/queue_supervisor.py --json'
```

## Integration Pattern

1. Run one maintenance cycle command.
2. Maintenance cycle runs guarded packet then queue supervisor.
3. Stay quiet on clear.
4. Forward concise alert on supervisor alert.

## Maintenance Harness Gates

`scripts/cos/weekend_maintenance_cycle.sh` is fail-closed before packet execution:

- hard preflight gate:
  - `openclaw gateway probe --json` must be reachable + `admin-capable`
  - `openclaw hooks check` must report `Ready: 4`, `Not ready: 0`
- conservative topology gate:
  - `gateway.bind=loopback`
  - expected auth posture from `~/.openclaw/openclaw.json`
- runtime version pin gate:
  - pinned `openclaw --version`
  - pinned `node --version`
- state hygiene:
  - `openclaw tasks maintenance --apply`
  - `openclaw sessions cleanup --all-agents --enforce --fix-missing`
- relay canary:
  - run one lightweight real `openclaw agent` command path
  - scan newly appended OpenClaw logs for
    `native hook relay not found|Native hook relay unavailable|relay unavailable`
  - on hit, restart gateway, rerun preflight + canary once, and fail closed if
    relay errors persist

Wrapper command:

```bash
sh -lc 'cd /home/baine/openclaw/orchestrator && scripts/cos/weekend_maintenance_cycle.sh'
```
