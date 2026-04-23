# Packet and Closeout Schema

## Purpose

Define the minimum durable structure needed to hand work from the Chief of Staff to the internal orchestrator or a specialist agent, then return a verified closeout.

The schema should prevent drift without turning every task into paperwork.

## When To Use A Packet

Use a packet for work that is nontrivial, delegated, state-changing, verification-sensitive, or externally consequential.

Do not require a full packet for a simple answer or a trivial read-only check.

## Packet ID

Format:

```text
PKT-YYYYMMDD-short-slug-NN
```

Example:

```text
PKT-20260422-gmail-draft-01
```

Rules:

- Use the local date of packet creation.
- Keep the slug human-readable.
- Increment `NN` only when multiple packets share the same date and slug.
- Carry the packet ID into closeout, state updates, drafts, and follow-up notes.

## Packet Schema

```yaml
packet_id: PKT-YYYYMMDD-short-slug-NN
objective: One sentence describing the intended outcome.
priority: P0 | P1 | P2
source: Principal instruction, standing rule, or named upstream artifact.
owner: Chief of Staff | Orchestrator | named specialist
mode: direct | packetized | deep | quiet | verbose
scope:
  in:
    - Exact work included.
  out:
    - Explicit non-goals and boundaries.
paths:
  repo: /absolute/path when code or docs are touched
  state: /absolute/path when state is touched
authority:
  level: 1 | 2 | 3 | 4 | 5
  source: current instruction | standing rule | bounded packet | safe default
  external_commit_allowed: true | false
tool_classes:
  - A | B | C | D | E | F
constraints:
  - Safety, privacy, style, model, workspace, or execution constraints.
done_condition:
  - Observable condition required for completion.
evidence_required:
  - Readback, tests, screenshots, object IDs, sent-state, or other proof.
freshness_required:
  - State or source systems that must be checked before acting.
blast_radius:
  tier: B0 | B1 | B2 | B3 | B4
  affected_objects: bounded description
idempotency:
  key: Stable key that prevents duplicate external or state-changing actions.
  duplicate_policy: skip | update | ask | replace
escalation_threshold:
  - Exact condition that requires returning to the principal.
```

## Priority Definitions

- `P0`: urgent, blocking, high-risk, or time-sensitive.
- `P1`: important and active, but not immediate emergency.
- `P2`: useful, maintenance, exploratory, or deferred.

## Authority Defaults

- Internal read/analyze defaults to Level 1.
- Internal write/stage defaults to Level 2 when path and purpose are clear.
- External draft/propose defaults to Level 3.
- External commit defaults to Level 4 and requires explicit current authority unless a narrow standing rule exists.
- Standing external authority is Level 5 and should be rare.

## Blast Radius Tiers

- `B0`: read-only, no state change.
- `B1`: local reversible internal write.
- `B2`: local workflow state change or durable internal register update.
- `B3`: single bounded external draft, proposal, or reversible external preparation.
- `B4`: external commit, third-party-visible change, recurring change, bulk action, destructive action, or high-consequence action.

## Closeout Schema

```yaml
packet_id: PKT-YYYYMMDD-short-slug-NN
status: DONE | PARTIAL | BLOCKED | NEEDS DECISION | EXCEPTION
objective: Restate objective in one line.
result: What changed or what was learned.
artifacts:
  changed:
    - Files, drafts, events, messages, or state objects changed.
  inspected:
    - Important files, systems, or objects inspected.
authority_used:
  level: 1 | 2 | 3 | 4 | 5
  source: current instruction | standing rule | bounded packet | safe default
external_effect:
  occurred: true | false
  details: Recipients, attendees, notifications, labels, archive/delete/send state, or "none".
verification:
  - Evidence that done condition was met.
  - Readback or test results where relevant.
state_updates:
  - Runtime state or ledgers updated, if any.
residual_risk:
  - Remaining uncertainty, stale data, unverified behavior, or follow-up.
next_action:
  - None, blocked ask, approval needed, or recommended follow-up.
```

## Closeout Rules

Closeout should be brief but proof-bearing.

Required truths:

- Say whether external effect occurred.
- Say what was verified.
- Say what remains unverified.
- Say whether the work is complete, partial, blocked, or needs a decision.

Do not report `DONE` when only intent, draft, or partial execution exists.

## Idempotency Rules

Every state-changing or external packet needs an idempotency key.

Use one of these sources:

- upstream message ID
- calendar event ID
- file path plus intended section
- packet ID plus target object
- stable slug plus date

Duplicate handling:

- If the same idempotency key already completed, do not repeat the external action.
- If a draft exists, update the draft rather than creating another draft unless told otherwise.
- If a calendar event exists, propose an update rather than creating a duplicate.
- If duplicate status is uncertain, stop at preview and ask for authority before committing.

## Minimal Packet Template

```text
Packet: PKT-YYYYMMDD-short-slug-NN
Objective:
Priority:
Scope:
Out of scope:
Authority:
Done:
Evidence:
Escalate if:
```

Use the minimal template for ordinary internal work.
Use the full schema for consequential, delegated, or repeated workflows.
