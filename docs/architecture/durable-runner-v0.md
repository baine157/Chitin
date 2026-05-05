# Durable Runner v0

## Purpose

The durable runner is a small execution substrate for bounded local work. It
separates control-plane liveness from execution-plane truth: a healthy chat
session, gateway, or hook registry is not the same thing as verified host work.

The v0 contract is deliberately narrow:

- tasks are durable files, not in-memory jobs
- packets name a lane and command, but policy decides what may run
- commands are argv arrays; shell strings are rejected
- idempotency keys are enforced across all task states
- events are append-only JSONL
- stdout, stderr, and verification are run artifacts
- tasks cannot become `done` until verification passes
- external effects are denied unless the lane policy permits them

## Non-Goals

- no external API coupling
- no browser, portal, credential, send, submit, upload, sign, certify, or finalize actions
- no general fallback shell agent
- no UI-first workflow
- no retry/backoff policy beyond lease-based recovery

## State Layout

```text
state/cos/durable-runner/
  tasks/
    queued/
    running/
    waiting_approval/
    done/
    failed/
    canceled/
  events/
    <task-id>.jsonl
  runs/
    <task-id>/<run-id>/
      stdout.log
      stderr.log
      verification.json
  locks/
```

## Commands

```bash
node durable-runner/src/cli.ts init
node durable-runner/src/cli.ts enqueue path/to/task.json
node durable-runner/src/cli.ts tick --manifest lane-manifests/orchestrator_control_plane_health.yaml
node durable-runner/src/cli.ts watch --manifest lane-manifests/orchestrator_control_plane_health.yaml --poll-ms 1000 --heartbeat-ms 60000
node durable-runner/src/cli.ts approve <task-id> <gate-id>
node durable-runner/src/cli.ts status <task-id>
```

`tick` processes at most one task. A future service can call it in a loop, but
v0 keeps the primitive easy to reason about and test.

Approval-gated tasks move into `waiting_approval` and only return to `queued`
through explicit `approve`.

## Heartbeat Language Alignment

Watch mode writes `state/watch-health.json` with:

- queue supervisor style status: `QUEUE_SUPERVISOR_CLEAR` or `QUEUE_SUPERVISOR_ALERT`
- lease-heartbeat metrics: renewals, renewal failures, reclaimed running tasks
- execution-plane truth markers:
  - `queue_liveness: necessary_but_insufficient`
  - `lease_heartbeat: required_for_running_truth`

This mirrors the current stack language: control-plane liveness does not prove
execution-plane truth. Lease heartbeat is treated as an execution substrate
signal, not a gateway/chat signal.

## Public Review Bar

This runner should be judged as infrastructure, not as autonomy. Its job is to
record what was requested, what policy allowed, what ran, what artifacts exist,
and why the outcome is `done`, `failed`, `waiting_approval`, or `canceled`.
