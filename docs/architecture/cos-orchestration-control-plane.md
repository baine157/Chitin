# CoS Orchestration Control Plane

## Purpose

Define the operating separation between the principal-facing Chief of Staff layer and the internal orchestration layer.

The goal is one quiet executive surface backed by a governed execution system.

## Layer Model

### Principal

The principal sets direction, priorities, constraints, and approval for consequential actions.

The principal should not need to supervise:

- retries
- tool choice
- subordinate agents
- packet mechanics
- approval churn
- raw tool output

### Chief of Staff

The Chief of Staff is the executive interface.

Responsibilities:

- interpret principal intent
- decide altitude
- set priority
- normalize work into direct answers or bounded packets
- protect attention
- retain continuity
- escalate only decision-grade material
- verify that returned work is usable before surfacing it

The Chief of Staff owns principal-facing language.

### Internal Orchestrator

The orchestrator is below the line.

Responsibilities:

- execute bounded packets
- choose tool lanes
- delegate to specialists when useful
- enforce authority limits
- collect evidence
- manage retries without chatter
- return proof-bearing closeouts

The orchestrator does not become a second principal-facing chat surface by default.

### Specialist Agents and Tools

Specialists and tools are subordinate execution functions.

They may optimize within packet scope.
They may not redefine mission, risk tolerance, authority boundary, or done condition.

### Runtime State

Runtime state stores continuity, not truth by assertion.

State is useful only when it is:

- timestamped
- scoped
- owned
- refreshable
- reconciled against source systems when external state matters

## Work Classification

Use the smallest process that preserves trust.

### Direct Work

Use for low-risk answers, brief analysis, and trivial internal edits.

Requirements:

- no external consequence
- no ambiguous authority
- no meaningful blast radius
- no need for delegation

Output can be a direct answer or a compact done report.

### Packetized Work

Use for meaningful execution that needs a durable scope.

Triggers:

- repo or file changes
- delegated agent work
- multi-step tool use
- state register updates
- verification-sensitive work
- work that could otherwise drift

Use `packet-and-closeout-schema.md`.

### Consequential Work

Use packetized work plus explicit authority controls.

Triggers:

- email send, forward, archive, delete, or workflow-changing labels
- live calendar creation, modification, cancellation, or invitation response
- third-party notification
- recurring action
- bulk action
- high-consequence professional, administrative, financial, legal, or medical-adjacent action

Use `AUTHORITY_MATRIX.md` and `state-routing-blast-radius-policy.md`.

## Command Surface

The principal-facing command surface should stay small.

Canonical commands:

- `go`: execute the current packet now.
- `hold`: park the current packet without executing.
- `deep`: use higher verification or higher capability.
- `quiet`: minimize outward progress updates.
- `verbose`: allow detailed progress for the current packet only.

These commands alter execution mode.
They do not automatically widen authority.

## Status Surface

Allowed outward states:

- `STARTED`
- `BLOCKED`
- `NEEDS DECISION`
- `EXCEPTION`
- `DONE`

Optional modifier:

- `PARTIAL`

Do not expose internal state-machine noise unless requested.

## Escalation Standard

Escalate only when one of these is true:

- principal judgment is actually needed
- authority is missing
- safety boundary changes
- scope changes materially
- verification fails in a way that affects outcome
- external consequence would be created
- divergence is found between state and source of truth

Routine internal uncertainty should be handled below the line.

## Anti-Bureaucracy Rule

The control plane should reduce overhead, not create it.

Default rule:

- trivial work: direct
- meaningful work: packetized
- consequential work: packetized, authority-scoped, and proof-bearing

If process becomes larger than the task, collapse to the smallest safe form.
