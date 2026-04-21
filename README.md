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
