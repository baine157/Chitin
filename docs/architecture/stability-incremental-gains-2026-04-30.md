# Stability Incremental Gains - 2026-04-30

Purpose: bounded change ledger for the seven stability slices requested after
the lane-normalization pass.

## Slice Ledger

| slice | tracked change | local state change | verification |
| --- | --- | --- | --- |
| 1. automate decisive smoke | added `scripts/observability/execution_plane_health_cycle.sh` and `execution-plane-health-cycle.md` | refreshes `state/observability/*.json` when run | health cycle output + focused unittests |
| 2. clean dashboard truth debt | collector separates historical blocked closeouts from active blocked packet files | moved old blocked packet JSONs to `state/cos/packets/historical-blocked/2026-04-30/` and refreshed CoS registers | `queue_supervisor.py`, `collect_dashboard.py` |
| 3. commit GBrain RF syncs | committed in `gbrain` as `36a74f6` | none in orchestrator | `npm run build` |
| 4. gateway degraded-but-usable semantics | execution smoke preserves parsed gateway diagnostic detail; dashboard reports it separately | refreshed execution-plane smoke/dashboard | `tests.test_execution_plane_truth` |
| 5. health harness routing | `health-harness-v1.md` marks harness temporary/personal-ops-adjacent | `waiting-on.md` no longer waits on Baine for this routing decision | doc readback |
| 6. lane manifests | added manifests for orchestrator, GBrain, medical logs, deck ops, course live notes, rescue gateway, and Deep Sea General | none | `validate_lane_manifest.py` over all manifests |
| 7. security posture decisions | added `z420-security-posture-decisions-2026-04-30.md` and linked it from baseline | none | config-shape probe confirms gateway password is env-ref |

## Current Stability Label

After this slice, the intended label is:

```text
PARTIAL but usable:
- control plane: healthy
- execution plane: fresh/ok from terminal-local smoke
- live Telegram relay: only proven when live-session smoke is fresh
- connector auth: Gmail search/read still needs repair
- security posture: accepted local-first warnings are recorded; SSH/tailnet/BW residue remain unresolved decisions
```

## Non-Goals

- No external sends, submits, uploads, attestations, signatures, certifications,
  or finalizations.
- No recurring model-using timer was silently enabled.
- No health data was promoted into orchestrator doctrine.
- No ignored runtime state was forced into git history.
