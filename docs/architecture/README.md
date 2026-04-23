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
- `runtime-validation-checklist.md`: required gates before claiming live BearClaw/OpenClaw stability.
- `orchestration-smoke-tests.md`: golden and red-team scenarios for contract drift.
- `stack-inefficiency-audit.md`: current inefficiencies, risks, and cleanup sequence.
- `health-harness-v1.md`: local-first personal health harness concept; this is not core orchestration doctrine.

Organization rule:

- Keep constitutional files at repo root.
- Keep schemas and policies under `docs/architecture/`.
- Keep local runtime data under `state/` or `.openclaw/`.
- Do not turn this workspace into a truth store for domain repos.
