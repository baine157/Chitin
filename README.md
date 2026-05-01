# Orchestrator Workspace

Purpose:

- neutral home base for BearClaw private DM orchestration
- intake, triage, task-packet generation, and delegated build control
- no canonical records, no medical logging, no onboarding truth store

Rules:

- this workspace is not a project build target by default
- implementation should happen in explicit repo paths handed to delegated builders
- durable conclusions belong in the relevant workspace, not here
- onboarding-ops must not be used as the inherited fallback workspace for unrelated DM work
- general BearClaw orchestration doctrine belongs under `docs/architecture/`

## Organization

- root files define identity, user profile, tool policy, and authority thresholds
- `docs/architecture/` holds reusable operating doctrine and schemas
- `state/` and `.openclaw/` hold local runtime material
- domain truth belongs in the relevant domain workspace, not here

Start with `docs/architecture/README.md` when looking for the current architecture map.

## CoS Mode (Default)

Use this thread as your CoS surface and run orchestration internally.

- you give objective and priority
- CoS converts requests into bounded packets
- orchestrator frames, dispatches, tracks, and verifies packets
- execution lanes and machine runners return evidence
- operator-visible updates stay at `STARTED`, `BLOCKED`, `NEEDS DECISION`, `EXCEPTION`, or `DONE`

Detailed layer separation: `docs/architecture/cos-orchestration-control-plane.md`.
Packet and closeout rules: `docs/architecture/packet-and-closeout-schema.md`.
State, routing, and blast-radius rules: `docs/architecture/state-routing-blast-radius-policy.md`.
Runtime validation: `docs/architecture/runtime-validation-checklist.md`.
Drift tests: `docs/architecture/orchestration-smoke-tests.md`.
Current inefficiency audit: `docs/architecture/stack-inefficiency-audit.md`.

## Lightweight Command Surface

- `go`: execute current packet now
- `hold`: park current packet
- `deep`: run higher-verification execution mode
- `quiet`: force low-noise updates
- `verbose`: allow detailed progress for current packet only

## Approval Discipline

- batch commands into minimal approval windows
- request durable scoped approval once per packet family where possible
- stop retry loops and emit one blocker instead of repeated approval spam
