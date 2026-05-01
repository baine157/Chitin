# Architecture Index

This directory holds reusable BearClaw / Chief of Staff orchestration doctrine.

Root files define constitution and top-level behavior:

- `SOUL.md`: identity, mission, chain of command, executive shielding.
- `USER.md`: principal profile and principal-facing preferences.
- `TOOLS.md`: tool classes, routing ladders, approval discipline, verification.
- `AUTHORITY_MATRIX.md`: permission thresholds and externally consequential action rules.

Architecture files define reusable operating mechanics:

- `bearclaw-orchestration-contract.md`: primary operator-facing contract.
- `cos-orchestration-control-plane.md`: layer separation and command surface ownership.
- `packet-and-closeout-schema.md`: packet format, closeout format, evidence rules, idempotency.
- `state-routing-blast-radius-policy.md`: state freshness, routing boundaries, divergence handling, blast radius, identifiers.
- `runtime-validation-checklist.md`: required gates before claiming live BearClaw/OpenClaw stability, including execution-plane smoke and relay repair proof.
- `orchestration-smoke-tests.md`: golden and red-team scenarios for contract drift.
- `stack-inefficiency-audit.md`: current inefficiencies, risks, and cleanup sequence.
- `guarded-packet-runner-v0.md`: fail-closed packet execution lane for autonomous CoS maintenance.
- `queue-supervisor-sla-v0.md`: queue SLA monitor and alert contract for packet execution health.
- `dreaming-and-reflection-boundary.md`: where reflective synthesis belongs, where it does not, and why it is not execution proof.
- `health-harness-v1.md`: local-first personal health harness concept; this is not core orchestration doctrine.

Organization rule:

- Keep constitutional files at repo root.
- Keep schemas and policies under `docs/architecture/`.
- Keep local runtime data under `state/` or `.openclaw/`.
- Do not turn this workspace into a truth store for domain repos.
- Do not flatten "gateway reachable" into "machine execution available"; dashboard truth must keep the control plane and execution plane separate.
