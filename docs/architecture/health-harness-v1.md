# Health Harness v1 (Lightweight)

## Routing Status

This is a local/personal experiment, not core orchestrator doctrine.

It may remain here only as a temporary personal-ops-adjacent harness because it
can inform Chief-of-Staff decisions about energy, sleep debt, and training load.
It must not become a general OpenClaw control-plane dependency, dashboard truth
source, or domain truth store.

Future cleanup path:

- move the implementation to a dedicated personal-ops workspace, or
- keep only a routing note here and store health data outside `orchestrator/`.

Until that move happens, all health data stays local, ignored, and separate from
CoS packet execution state.

## Goal

Track sleep, lifting, weight, and nutrition with a local-first loop and minimal overhead.

## Scope (v1)

- Daily ingest into one normalized JSON file.
- Daily scorecard generation.
- Basic alert checks.
- Weekly summary generation.

## Sources

- WHOOP: sleep/recovery/strain.
- Apple Health: activity and backup health metrics.
- VeSync or MacroFactor: bodyweight source of truth.
- MacroFactor: calories and macros.

## Guard Rails

- Read-only source pulls.
- No outbound sharing.
- No auto-delete behavior.
- All data stored locally in this workspace.

## Canonical File Layout

- `state/health-harness/data/normalized-daily.json`
- `state/health-harness/data/alerts.json`
- `state/health-harness/output/daily-scorecard.md`
- `state/health-harness/output/weekly-summary.md`
- `state/health-harness/config.json` (local secrets/ids, ignored by git)
- `state/health-harness/config.example.json` (template)

## Normalized Daily Schema

```json
{
  "date": "2026-04-22",
  "sleep": {
    "hours": 7.4,
    "efficiency_pct": 89,
    "resting_hr": 52
  },
  "recovery": {
    "whoop_recovery_pct": 71,
    "hrv_ms": 62
  },
  "training": {
    "whoop_strain": 13.2,
    "lifting_minutes": 52,
    "lifting_sets_hard": 14
  },
  "body": {
    "weight_lb": 191.6,
    "weight_trend_7d_lb": 192.4
  },
  "nutrition": {
    "calories": 2480,
    "protein_g": 212,
    "carbs_g": 240,
    "fat_g": 76
  }
}
```

## Alerts (v1)

- Sleep debt: `sleep.hours < 6.5` for 2 consecutive days.
- Recovery warning: `whoop_recovery_pct < 34`.
- Load mismatch: high strain day (`>= 14`) with low calories (`< target - 400`).
- Weight drift: 7-day trend up/down beyond configured threshold.

## Daily Loop

1. Refresh source pulls.
2. Update `normalized-daily.json`.
3. Run scorecard script.
4. Run alerts script (or inline rule check).

## Weekly Loop

1. Aggregate last 7 entries.
2. Emit concise trends:
   - sleep avg and variance
   - training load trend
   - weight trend
   - nutrition adherence

## Implementation Note

v1 is intentionally simple: file-based, script-driven, no dashboard requirement.

## iOS-First Architecture

For iPhone-first usage, Apple Health is the broker layer between apps.

Source-of-truth order in harness:

- Sleep / Recovery / Strain:
  - Primary: WHOOP
  - Fallback: Apple Health
- Weight:
  - Primary: VeSync
  - Fallback: Apple Health
  - Secondary fallback: MacroFactor
- Nutrition:
  - Primary: MacroFactor
  - Fallback: Apple Health

This keeps each metric aligned to the most reliable upstream source while still allowing broker fallback when one feed is missing.
