# Durable Runner 24h Soak Runbook

This runbook executes a 24-hour canary soak for `durable-runner` on the
`orchestrator_control_plane_health` lane.

Default soak root is now:

`${REPO_ROOT}/state/cos/durable-runner`

This is intentional so watch health flows directly into the existing
repo-local durable-runner state tree.

## Start

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
bash "${REPO_ROOT}/scripts/cos/durable_runner_soak_start.sh"
```

Optional args:

```text
<root_dir> <duration_hours> <poll_ms> <lease_ms> <heartbeat_ms> <collect_every_sec> <worker_id>
```

The dashboard collector is optional in this repo. Set `COLLECTOR=/path/to/script`
before starting a soak if a host-local collector exists; otherwise the soak runs
with collector reporting disabled.

## Status

```bash
bash "${REPO_ROOT}/scripts/cos/durable_runner_soak_status.sh"
```

Machine-readable proof:

```bash
node "${REPO_ROOT}/durable-runner/src/cli.ts" prove --root "${REPO_ROOT}/state/cos/durable-runner/run"
```

## Stop + Report

```bash
bash "${REPO_ROOT}/scripts/cos/durable_runner_soak_stop_and_report.sh"
```

## Pass Criteria

- no stuck tasks in `running` at end of soak
- no duplicate terminal outcomes for same task id
- watch health status is `QUEUE_SUPERVISOR_CLEAR` (or alert root-caused and bounded)
- `renewFailures` is `0` or explained with bounded incident evidence
- `queueDiagnosisAlerts` and `quarantinedParseErrors` are `0` or explained with fixes
- quarantine cleanup ledger entries are present and consistent

## Failure Criteria

- silent queue non-progress with queued tasks and no diagnosis alert
- unexpected data loss (missing terminal state + missing event trail)
- unbounded `running` tasks after worker interruption/restart
- repeated lease renewal failures without recovery
