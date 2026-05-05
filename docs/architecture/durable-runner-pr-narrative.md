# Durable Runner PR Narrative (Maintainer Draft)

## Problem

OpenClaw control-plane health (hooks/session/gateway) can be green while
execution-plane truth is unknown. We need a durable, local-first runner that
records task intent, policy enforcement, execution artifacts, and verified
terminal outcomes.

## Why This Belongs in OpenClaw

- aligns with conservative operator posture (fail-closed, auditable)
- provides a reliable fallback relay lane when hooks fail
- keeps infra minimal (local files + TypeScript, no external API coupling)
- improves incident debugging with deterministic artifacts

## Approach

- task packets persisted by state (`queued/running/waiting_approval/done/failed/canceled`)
- per-task append-only events JSONL
- lease ownership + renewal with reclaim on expiry
- policy-governed command execution (argv only, no shell mode)
- verification gate required for terminal `done`
- soak scripts + supervisor for unattended durability checks

## Evidence

- unit/integration tests: `node --test durable-runner/tests/*.test.ts`
- CLI smoke: `node durable-runner/src/cli.ts --help`
- machine-readable usage proof:
  - `node durable-runner/src/cli.ts prove --root <root>`
- soak report artifact:
  - `state/cos/durable-runner/soak-report.txt`

## Risks

- path conventions may be too OpenClaw-specific if `--root`/policy defaults are not used
- operational scripts depend on host service behavior (supervisor/systemd)
- policy manifest drift can break allowed command mapping if unmanaged

## Rollback

- stop soak services/scripts
- stop feeding tasks into durable-runner queue
- preserve task/event/run artifacts for incident review
- route execution back to existing hook-driven paths
