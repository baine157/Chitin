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

## Commit Closeout

- 2026-04-20: committed initial orchestrator workspace doctrine and BearClaw contract as `2f19907`

## Boundary Clarification

- 2026-04-21: narrowed BearClaw onboarding language to explicitly mean human-in-the-loop onboarding workspace support, not autonomous real-world onboarding execution

## Contract Alignment

- 2026-04-21: aligned BearClaw operator-facing dispositions to `build-now`, `hold`, and `needs-input`
- 2026-04-21: added blocked-runtime doctrine so local execution failures preserve user intent and return a concise resumable status instead of an environment-heavy deflection
- 2026-04-21: tightened the disposition rule so planning-only work maps to `hold` and non-contract labels such as `queue` or `queued_for_planning_only` are explicitly disallowed on the operator-facing surface
- 2026-04-21: added `docs/incidents/2026-04-21-orchestrator-runtime-incident.md` to capture the split between real bwrap failures, the `2026.4.15` minimal-reasoning runtime bug, and BearClaw contract drift

## Runtime Optimization

- 2026-04-21: shortened the BearClaw DM system prompt in `~/.openclaw/openclaw.json` to reduce per-turn token overhead while preserving the orchestration contract
- 2026-04-21: enabled idle session resets for direct and group chats in `~/.openclaw/openclaw.json` so stale Telegram context does not keep compounding across long-lived threads
- 2026-04-21: set `tools.fs.workspaceOnly=true` in `~/.openclaw/openclaw.json` to narrow filesystem blast radius and reduce audit noise from broad file access
- 2026-04-21: removed 19 stale backup and deleted session artifacts from `~/.openclaw/agents/main/sessions`, reclaiming about 21.4 MB of dead state without touching live session files
- 2026-04-21: fixed a gateway auth-provider mismatch by switching the main OpenClaw model selections from `codex/...` aliases to `openai-codex/...`, matching the configured OAuth profiles and clearing repeated embedded-run `401 Unauthorized` failures
- 2026-04-21: removed the last unused plain `codex/gpt-5.4` alias from `~/.openclaw/openclaw.json` so the main config exposes a single unambiguous `openai-codex/...` model path
- 2026-04-21: recovered the main embedded Codex lane by patching OpenClaw's `provider-auth-runtime-BOA0fEzs.js` so `openai-codex` app-server launches use the real `~/.codex` home instead of a stale bridge clone; verified with `openclaw gateway health`, a successful `openclaw agent --json` run on the main agent, and a Telegram confirmation delivered to chat `8620278310`

## Control-Plane Hardening

- 2026-04-22: added `docs/architecture/README.md` as the architecture navigation surface
- 2026-04-22: added `docs/architecture/cos-orchestration-control-plane.md` to make the Chief of Staff / internal orchestrator separation explicit
- 2026-04-22: added `docs/architecture/packet-and-closeout-schema.md` to centralize packet, closeout, evidence, and idempotency rules
- 2026-04-22: added `docs/architecture/state-routing-blast-radius-policy.md` to define state freshness, routing boundaries, divergence handling, blast radius, and identifiers
- 2026-04-22: added `docs/architecture/runtime-validation-checklist.md` after live smoke showed health checks can pass while stale sessions preserve bad disposition behavior
- 2026-04-22: added `docs/architecture/orchestration-smoke-tests.md` to capture golden and red-team scenarios for CoS/orchestrator drift
- 2026-04-22: added `docs/architecture/stack-inefficiency-audit.md` to capture current inefficiencies and cleanup sequence
