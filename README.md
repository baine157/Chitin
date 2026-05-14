# Chitin

Durable local execution runner for OpenClaw.

Chitin provides execution-plane truth when control-plane health alone is not enough. It runs bounded tasks with explicit policy, durable state transitions, append-only events, and verification-gated outcomes.

Status: Prototype / not production-ready.

>>>>>>> 9be4e61 (chitin: add CI workflow and finalize prototype docs/examples)
## Why This Exists

- Hooks/sessions can look healthy while real host work is unknown.
- Operators need durable, auditable artifacts for what ran and why it passed/failed.
- OpenClaw needs a local-first fallback relay lane when ephemeral paths fail.

## Quickstart

From repo root:

```bash
node durable-runner/src/cli.ts init
<<<<<<< HEAD
node durable-runner/src/cli.ts enqueue <task.json>
node durable-runner/src/cli.ts tick --manifest lane-manifests/orchestrator_control_plane_health.yaml
node durable-runner/src/cli.ts status <task-id>
=======
node durable-runner/src/cli.ts enqueue durable-runner/examples/task.smoke.json
node durable-runner/src/cli.ts tick --manifest lane-manifests/orchestrator_control_plane_health.yaml
node durable-runner/src/cli.ts status task_smoke_001
>>>>>>> 9be4e61 (chitin: add CI workflow and finalize prototype docs/examples)
```

Watch mode:

```bash
node durable-runner/src/cli.ts watch \
  --manifest lane-manifests/orchestrator_control_plane_health.yaml \
  --poll-ms 1000 \
  --heartbeat-ms 60000
```

Approval gates:

```bash
node durable-runner/src/cli.ts approve <task-id> <gate-id>
```

## CLI Surface

- `init`
- `enqueue <task.json>`
- `tick --policy <json|yaml> | --manifest <lane.yaml>`
- `watch --policy <json|yaml> | --manifest <lane.yaml>`
- `approve <task-id> <gate-id>`
- `status <task-id>`
- `cleanup-quarantine [--dry-run] [--max-age-hours N]`
- `prove [--max-fresh-ms N]`

## Task Model

States:

`queued -> running -> waiting_approval | done | failed | canceled`

Durable artifacts:

- task packet per state directory
- append-only event log: `events/<task-id>.jsonl`
- per-run outputs: `runs/<task-id>/<run-id>/{stdout.log,stderr.log,verification.json}`
- ledger entries for cleanup/ops lifecycle

## Reliability Guarantees

- explicit transition guards
- lease-based ownership + renewal/reclaim
- per-task lock safety for claim/renew/transition
- no terminal `done` without verification artifact and passing checks
- quarantine cleanup writes ledger evidence

## Operational Soak

<<<<<<< HEAD
Use scripts in `scripts/cos/`:

- `durable_runner_soak_start.sh`
- `durable_runner_soak_status.sh`
- `durable_runner_soak_stop_and_report.sh`
- `durable_runner_soak_supervisor.sh`

Runbook:

- `docs/architecture/durable-runner-soak-runbook.md`
=======
Soak scripts are optional and local-repo scoped only:

- `scripts/cos/durable_runner_soak_start.sh`
- `scripts/cos/durable_runner_soak_status.sh`
- `scripts/cos/durable_runner_soak_stop_and_report.sh`
- `scripts/cos/durable_runner_soak_supervisor.sh`
>>>>>>> 9be4e61 (chitin: add CI workflow and finalize prototype docs/examples)

## Proof of Use

Machine-readable usage proof:

```bash
node durable-runner/src/cli.ts prove --root state/cos/durable-runner/run
```

This reports whether Chitin is actively being used and returns evidence paths/freshness for health, events, runs, and ledger.

## Testing

```bash
node --test durable-runner/tests/*.test.ts
node durable-runner/src/cli.ts --help
```

## Non-Goals

- No external API coupling for core runner operation
- No hidden in-memory state as source of truth
- No direct replacement of hooks; this is a durable fallback/relay lane
<<<<<<< HEAD

=======
>>>>>>> 9be4e61 (chitin: add CI workflow and finalize prototype docs/examples)
