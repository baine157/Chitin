# Build Log

## Initial Decisions

- Date initialized: 2026-04-20
- Workspace purpose: neutral BearClaw orchestration home
- Durable surface: `README.md`, `docs/`, and future reusable orchestration doctrine
- Local-only surface: `.openclaw/`, `state/`, and local bootstrap files
- Explicit boundary: this workspace is not a truth store for onboarding, medical logging, or other domain repos

## BearClaw Contract Import

- Imported the BearClaw orchestration contract from the onboarding workspace after repo-boundary cleanup
- General BearClaw doctrine now lives in the neutral orchestrator repo rather than inside `onboarding-ops`
- Contract scope covers intake, triage, task packets, delegated coding, verification gates, and model stratification
