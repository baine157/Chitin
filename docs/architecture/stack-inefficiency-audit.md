# Stack Inefficiency Audit

Date: 2026-04-22

Scope: BearClaw / Chief of Staff / orchestrator workspace and adjacent OpenClaw operating stack.

## Summary

The stack's main inefficiency is not lack of intelligence.
It is unclear separation between durable doctrine, operational schemas, runtime state, and domain-specific work.

The strongest corrective move is to keep one principal-facing Chief of Staff surface while making the below-the-line machinery explicit, compact, and auditable.

## Findings

### 1. Schemas Were Embedded Instead Of Canonical

Problem:

Packet shape, closeout expectations, command surface, state freshness, and blast-radius policy were spread across README text, contract text, TOOLS.md, and AUTHORITY_MATRIX.md.

Impact:

- hard to test
- easy to drift
- difficult for smaller execution lanes to apply consistently
- increases chance of verbose or improvised closeouts

Correction:

- `packet-and-closeout-schema.md` is now the canonical packet and closeout reference.
- `state-routing-blast-radius-policy.md` is now the canonical state/routing/blast-radius reference.
- `cos-orchestration-control-plane.md` is now the canonical layer-separation reference.

### 2. Root Files Were Carrying Too Much Operational Detail

Problem:

Root files are good for identity, user profile, tools, and authority.
They are poor places for every reusable schema and operational variant.

Impact:

- root gets intimidating
- future edits become high-risk
- doctrinal files become less readable

Correction:

Keep root files constitutional.
Move mechanics into `docs/architecture/`.

### 3. Stale Bootstrap File Still Exists

Problem:

`BOOTSTRAP.md` is still present even though the workspace has established `SOUL.md`, `USER.md`, `TOOLS.md`, `IDENTITY.md`, and operating doctrine.

Impact:

- creates contradictory "first run" instructions
- wastes attention during future orientation
- tempts unnecessary identity/setup work

Recommended cleanup:

Remove or archive `BOOTSTRAP.md` after confirming it is no longer needed.

This audit does not delete it because the current task is architecture hardening, and deletion should be intentional.

### 4. Personal Health Harness Is In The Orchestrator Workspace

Problem:

`docs/architecture/health-harness-v1.md` and `state/health-harness/` live inside the neutral orchestrator workspace.

Impact:

- conflicts with the workspace rule that orchestrator is not a domain truth store
- risks mixing personal operations data with orchestration doctrine
- increases confusion over what this repo owns

Recommended cleanup:

Either:

- explicitly mark health harness as a temporary/local experiment, or
- move it to a personal-ops workspace and leave only a routing note here.

Do not silently promote health data to orchestrator canonical state.

### 5. Runtime Truth Still Lives Outside Docs

Problem:

Live behavior can depend on `~/.openclaw/openclaw.json`, gateway state, connector state, and session stores.
Docs alone are not the runtime source of truth.

Impact:

- architecture may look correct while live behavior drifts
- runtime fixes may not be reflected in doctrine
- smoke tests can pass for docs and fail in Telegram or embedded execution

Recommended cleanup:

Add a tiny runtime validation checklist that includes:

- current OpenClaw config path
- gateway health
- active model/provider aliases
- live BearClaw prompt/policy alignment
- one planning-only smoke test
- one blocked-runtime smoke test

### 6. Approval Discipline Exists But Needs Idempotency Hooks

Problem:

Approval throttling is documented, but duplicate prevention is not yet central enough.

Impact:

- repeated drafts
- duplicate calendar holds
- re-applied labels
- repeated external actions after retry or resume

Correction:

`packet-and-closeout-schema.md` now requires idempotency keys for state-changing or external packets.

### 7. Routing Boundaries Need To Be Enforced Before Writes

Problem:

The user has multiple real workspaces, and topic labels are operational boundaries.
The stack can still accidentally write adjacent work into the nearest available repo.

Impact:

- Research Fellow, medical logs, onboarding, and general orchestration can contaminate each other
- future agents may inherit wrong context
- audits become harder

Correction:

`state-routing-blast-radius-policy.md` defines default routing and the "classify and hold" fallback.

### 8. Formatting Defects Make Governance Docs Harder To Parse

Problem:

Some existing governance files have joined lines where bullets or headings ran together.

Impact:

- weaker readability
- higher chance of misinterpretation by humans or smaller models

Recommended cleanup:

Fix line joins in `TOOLS.md` and `AUTHORITY_MATRIX.md`.

## Suggested Cleanup Sequence

1. Adopt the new architecture index as the navigation surface.
2. Fix formatting defects in tool and authority docs.
3. Decide whether to remove/archive `BOOTSTRAP.md`.
4. Decide whether health harness belongs here or in a personal-ops workspace.
5. Add a runtime validation checklist for live `~/.openclaw` alignment.
6. Add lightweight golden/red-team tests against packet, closeout, authority, and routing behavior.

## Efficiency Rule Going Forward

Before adding a new doc, ask:

- Is this constitutional doctrine?
- Is this operational schema?
- Is this runtime state?
- Is this domain truth?
- Is this an incident or test?

Then place it accordingly.

If the answer is unclear, do not write into a domain repo.
Classify, hold, and ask for the smallest routing decision.
