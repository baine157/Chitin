# State, Routing, and Blast Radius Policy

## Purpose

Prevent the Chief of Staff layer from becoming coherent in chat while the underlying state, routing, or authority model quietly drifts.

This file covers five areas:

- state freshness
- routing boundaries
- divergence handling
- blast-radius control
- identifier discipline

## State Spine

The Chief of Staff may maintain a lightweight runtime state spine.

Recommended registers:

- `current-priorities`
- `open-loops`
- `waiting-on`
- `drafts-pending-review`
- `calendar-actions-pending`
- `blocked-packets`
- `recent-closeouts`

The state spine is for continuity.
It is not automatically the source of truth.

## Freshness Classes

### F0 - Ephemeral

Examples:

- current tool availability
- current gateway health
- current command output
- active browser/session state

Freshness rule:

- verify live before relying on it
- do not preserve as durable truth unless captured in an incident or closeout

### F1 - Short-Lived

Examples:

- inbox counts
- today's calendar availability
- current task blockage
- active draft state

Freshness rule:

- refresh before acting if older than the current working session or if external action is possible

### F2 - Operational

Examples:

- open loops
- waiting-on lists
- draft queues
- active project status

Freshness rule:

- state must include `last_checked`
- refresh when stale, contradicted, or before a consequential closeout

### F3 - Durable Doctrine

Examples:

- SOUL.md
- USER.md
- TOOLS.md
- AUTHORITY_MATRIX.md
- architecture docs

Freshness rule:

- treat as durable until explicitly changed
- check for local diffs before editing

## State Entry Minimum

Every state entry should include:

```yaml
id: stable-human-readable-id
title: short title
status: open | waiting | blocked | done | stale
owner: CoS | Orchestrator | named specialist | principal
source: packet_id, thread, file, message, or external object
last_checked: YYYY-MM-DD or timestamp
next_review: YYYY-MM-DD or trigger
authority_level: 1 | 2 | 3 | 4 | 5
notes: compact operational meaning
```

## Divergence Handling

Divergence exists when local state conflicts with an upstream source, current tool output, or principal instruction.

Rules:

- External systems beat local summaries for external state.
- Current principal instruction beats stale packet assumptions.
- Runtime evidence beats planned state.
- If divergence affects external consequence, stop before commit.
- Mark stale local entries instead of silently overwriting meaning.

Closeout for divergence should include:

- what conflicted
- source checked
- which source is treated as current
- what was updated or intentionally left stale
- whether principal decision is needed

## Routing Boundaries

Default routing:

- Orchestrator workspace: orchestration doctrine, packets, closeouts, execution policy, incidents.
- Research Fellow / GBrain: research strategy, Daily Briefs, owned-surface intake, research vault maintenance.
- Medical logs: Lobster's Log, local transcription, case-entry preparation, ACGME no-submit workflows.
- Onboarding ops: onboarding doctrine, heartbeat, canary work, reference models.
- Deep Sea / General: general Telegram topic handling and non-domain-specific messages.
- Personal operations: inbox, calendar, health, admin, and life operations only when explicitly routed or when a CoS task requires it.

Rules:

- Do not use `onboarding-ops` as a fallback workspace for unrelated work.
- Do not let General become a holding bucket for Research Fellow or medical-log work.
- Do not store domain truth in the orchestrator workspace unless the orchestrator itself is the domain.
- If routing is ambiguous, classify and hold rather than writing into the nearest repo.

## Blast Radius Rules

### B0 - Observe

Read-only work.

Allowed by default inside relevant scope.

### B1 - Local Reversible

Local edits that are easy to inspect and revert.

Allowed inside bounded packet with clear path and done condition.

### B2 - Local Durable State

State registers, memory-like notes, trackers, or workflow ledgers.

Requires clear ownership, timestamp, and readback.

### B3 - External Preparation

Drafts, proposed event plans, candidate replies, or prepared artifacts that do not create final external effect.

Requires explicit statement that no final external action occurred.

### B4 - External Commit or High-Consequence Change

Sends, forwards, archive/delete/label commits, live calendar changes, notifications, recurring changes, bulk operations, destructive actions, or professional/admin commitments.

Requires explicit authority and precise closeout.

## Bulk Action Preview Rule

Before any bulk or destructive action:

- identify affected set
- preview count and examples
- state expected consequence
- state reversibility
- request explicit go if consequence is material

Ambiguous cleanup language never authorizes destructive cleanup.

## Identifier Policy

Stable identifiers prevent duplicate action and make closeouts auditable.

Use:

- packet IDs for work packets
- external object IDs for Gmail/Calendar objects when available
- file paths plus section headings for doc edits
- state entry IDs for open loops
- idempotency keys for state-changing or external actions

Identifier rules:

- Never rely only on chat phrasing for a repeated action.
- Carry IDs forward into closeout.
- If an object has no stable external ID, create a local stable slug and date.
- For recurring or bulk actions, track both group ID and affected item IDs when possible.

## CoS Review Cadence

The state spine should be reviewed lightly, not constantly.

Recommended cadence:

- immediate refresh before external commit
- daily scan for P0/P1 open loops if CoS heartbeat is active
- weekly pruning of stale or completed entries
- incident-driven review after approval loops, duplicate actions, or routing mistakes

The goal is trustworthy continuity, not another inbox.
