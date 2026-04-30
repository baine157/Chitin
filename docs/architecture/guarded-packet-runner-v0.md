# Guarded Packet Runner v0

## Purpose

Provide a fail-closed runtime for bounded CoS packet execution so the agent can
continue safe maintenance work while the principal is away.

This slice is intentionally narrow:

- runtime lane: `openclaw_update_health`
- manifest-backed lane-local pilot: `onboarding_application_packet_audit`
- strict packet schema validation
- strict lane guard enforcement
- deterministic closeout artifact per run

## Implementation

Runner:

- `scripts/cos/guarded_packet_runner.py`

Lane manifest:

- `lane-manifests/onboarding_application_packet_audit.yaml`

Lane manifest validator:

- `scripts/cos/validate_lane_manifest.py`

Queue and state:

- `state/cos/packets/queue/` incoming packets
- `state/cos/packets/done/` archived successful packets
- `state/cos/packets/blocked/` archived blocked or needs-decision packets
- `state/cos/packets/closeouts/` proof-bearing closeout JSON artifacts

## Packet Schema (v0)

Required fields:

- `packet_id`: must match `PKT-YYYYMMDD-short-slug-NN`
- `disposition`: `build-now | hold | needs-input`
- `objective`: non-empty string
- `lane`: `openclaw_update_health` or `onboarding_application_packet_audit`
- `priority`: `P0 | P1 | P2`
- `authority.level`: integer 1..5
- `authority.external_commit_allowed`: boolean
- `idempotency.key`: non-empty string
- `idempotency.duplicate_policy`: `skip | update | ask | replace`
- `done_condition`: non-empty list of strings
- `evidence_required`: non-empty list of strings

Optional:

- `commands`: command ID list. If omitted, lane defaults are used.
- `packet_type`: when present for manifest-backed lanes, must be listed in
  `allowed_packet_types`.

## Lane Guard Enforcement (v0)

`openclaw_update_health` requires:

- `authority.level <= 2`
- `authority.external_commit_allowed == false`
- all command IDs in lane allowlist:
  - `openclaw_update_status_json`
  - `openclaw_update_dry_run_json`
  - `openclaw_gateway_health`
  - `openclaw_gateway_probe`
  - `openclaw_status_deep`

If any guard fails, the runner:

- writes a `BLOCKED` closeout
- moves packet to `state/cos/packets/blocked/`
- exits non-zero

Invalid packet policy:

- unreadable JSON or schema-invalid packets are quarantined immediately
- runner writes a `BLOCKED` validation closeout with exact errors
- packet is moved to `state/cos/packets/blocked/`
- this prevents `--once` starvation by a single bad packet at queue head

`onboarding_application_packet_audit` is now loaded from its lane manifest when
the manifest exists. The manifest contract records:

- `lane_id`
- `workspace`
- `allowed_packet_types`
- `commands.validator.id`
- `commands.validator.argv`
- optional `commands.dry_run`
- `live_run.allowed`
- `live_run.authority_max_level`
- `live_run.external_commit_allowed`
- `outputs.status_path`
- `outputs.closeout_dir`
- `forbidden_actions`
- `human_gates`
- `canary.id`
- `canary.command`
- `canary.expected_statuses`

The runner validates the manifest before accepting the lane. The manifest-backed
onboarding lane requires:

- `authority.level <= 2`
- `authority.external_commit_allowed == false`
- packet `lane` matches manifest `lane_id`
- packet `packet_type`, when present, is allowed by `allowed_packet_types`
- all packet command IDs are in the manifest-backed command allowlist:
  - `validate_comphealth_mycomphealth_packet`

The onboarding audit command is local and deterministic:

- reads packet artifacts under
  `/home/baine/openclaw/onboarding-ops/work/application-packets/comphealth-mycomphealth/`
- validates `field-map.json`, blockers, readback, verification packet, final-action
  prohibitions, and obvious sensitive-value absence
- does not access credentials, Bitwarden, portal login, browser sessions, cookies,
  MFA, captcha, or external systems
- returns `BLOCKED` or `PARTIAL`; it must not claim `DONE` while post-login fields
  remain inaccessible
- runner closeout records `external_effect.occurred == false`

The hardcoded onboarding lane remains the conceptual fallback in code history,
but current execution should resolve from the manifest. `openclaw_update_health`
remains hardcoded in v0.

## Lane Manifest Schema (v0)

Required fields:

- `lane_id`: string
- `workspace`: absolute path string
- `allowed_packet_types`: non-empty string list
- `commands.validator.id`: string
- `commands.validator.argv`: non-empty string list
- `live_run.allowed`: boolean; must be true for runner execution
- `live_run.authority_max_level`: integer
- `live_run.external_commit_allowed`: boolean
- `outputs.closeout_dir`: path string
- `forbidden_actions`: non-empty string list
- `human_gates`: non-empty string list
- `canary.id`: string
- `canary.command`: non-empty string list
- `canary.expected_statuses`: non-empty list of supported closeout statuses

Supported canary statuses:

- `DONE`
- `PARTIAL`
- `BLOCKED`
- `NEEDS DECISION`

Onboarding manifest safety invariants:

- `workspace` must be `/home/baine/openclaw/onboarding-ops`
- `live_run.authority_max_level <= 2`
- `live_run.external_commit_allowed == false`
- `forbidden_actions` must include:
  - `submit`
  - `upload`
  - `attest`
  - `sign`
  - `certify`
  - `finalize`
- `commands.validator.argv` must not contain:
  - `bw`
  - `bitwarden`
  - `xurl`
  - `gog`
  - browser login actions
  - submit, upload, send, attest, sign, certify, finalize actions
  - obvious credential, password, token, cookie, session, MFA, or captcha actions

Validation command:

```bash
python3 scripts/cos/validate_lane_manifest.py lane-manifests/onboarding_application_packet_audit.yaml
```

Invalid manifest policy:

- the manifest is rejected before lane execution
- runner startup reports `[manifest-invalid]` with the bad field
- the onboarding manifest-backed lane is not silently replaced with fallback execution
- error messages name fields and policies; they do not dump full manifest payloads

Future lane guidance:

- add one manifest per durable lane only after that lane has a deterministic
  validator or executor
- keep manifests as lane metadata, not domain truth
- lane-specific facts and artifacts stay in the lane workspace
- orchestrator may store packet metadata, authority limits, command allowlists,
  closeout paths, canary commands, and forbidden-action policy
- do not add manifests for GBrain, medical-logs, vendor/Gmail/calendar, or X
  until each lane has an equivalent fail-closed pilot

Runtime failure policy:

- hard-fail commands block the packet (`BLOCKED`)
- `openclaw_gateway_probe` is soft-fail (`PARTIAL`) when core health checks pass

## Blocked Reason Readback (v0)

Closeouts include structured `readback` and top-level `blocked_reason` fields so
`BLOCKED` packets explain themselves without requiring the operator to parse raw
stdout excerpts.

Blocked reason taxonomy:

- `missing_input`: required local input artifact is missing or empty
- `stale_artifact`: local artifact appears stale or cannot prove current state
- `schema_mismatch`: packet, manifest, or lane artifact does not match schema
- `validator_failed`: lane validator failed without a more specific reason
- `approval_gate`: human approval or operator action is required before continuing
- `credential_mfa_gate`: credential, MFA, captcha, cookie, or session gate blocks progress
- `final_action_gate`: final action is prohibited or requires explicit approval

For the onboarding audit lane, an otherwise well-formed validator result with
active blockers and post-login fields inaccessible maps to `approval_gate` with
`credential_mfa_gate` as a secondary code. That means the lane is safe and useful:
the artifacts parse, final actions remain prohibited, no credentials were
accessed, no external effect occurred, and the remaining block is operator/login
gated rather than a malformed packet.

## Execution Contract

Command:

```bash
sh -lc 'cd /home/baine/openclaw/orchestrator && python3 scripts/cos/guarded_packet_runner.py --once'
```

Validation-only mode:

```bash
sh -lc 'cd /home/baine/openclaw/orchestrator && python3 scripts/cos/guarded_packet_runner.py --dry-run --once'
```

Behavior:

- validates schema
- validates lane guards
- enforces disposition
- executes allowed commands with timeout
- records command exit codes plus output excerpts
- writes closeout JSON
- archives packet to `done` or `blocked`

## Why This Fits Current CoS Constraints

- bounded scope
- deterministic status and evidence
- no external commit path
- no silent "done" claims
- usable by heartbeat/autonomy loops without broad permissions
