# Changelog

## v0.2.0 - 2026-05-05

### Added
- Chitin durable-runner core in TypeScript with explicit task lifecycle:
  `queued`, `running`, `waiting_approval`, `done`, `failed`, `canceled`.
- CLI commands: `init`, `enqueue`, `tick`, `watch`, `approve`, `status`,
  `cleanup-quarantine`, `prove`.
- Durable artifacts and evidence model:
  append-only task events, per-run logs, verification output, and ledger entries.
- Soak operation scripts:
  start/status/stop/supervisor lifecycle under `scripts/cos/`.
- CI workflow for runner tests and CLI help smoke check.

### Changed
- Transition hardening at store boundary, including verification-gated `done`.
- README updated with prototype status and portable quickstart.
- Test suite expanded for reclaim/approval/quarantine/proof and CI portability.

### Verification
- `node --test durable-runner/tests/*.test.ts` passing.
- `node durable-runner/src/cli.ts --help` passing.

### Known non-goals
- Not a hook replacement; durable fallback lane only.
- No external API coupling required for core runner behavior.
