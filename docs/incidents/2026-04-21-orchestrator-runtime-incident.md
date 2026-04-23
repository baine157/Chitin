# 2026-04-21 Orchestrator Runtime Incident

## Summary

BearClaw failed to execute valid orchestration requests during the day for more than one reason.

There were three distinct failure classes:

1. real execution-path failures where Codex sandbox bootstrap died with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`
2. a separate OpenClaw embedded-run compatibility bug in `2026.4.15` where tool-enabled runs failed on `reasoning.effort 'minimal'`
3. BearClaw contract drift where valid operator intents were surfaced with the wrong disposition or with environment-heavy phrasing

Treating all three as one generic "environment failure" obscured the actual recovery path.

## Operator Impact

- `build-now` requests that should have produced a bounded task contract plus blocked status instead returned `needs-input due environment hard block`
- BearClaw over-reported total execution impossibility even though the runtime later recovered
- planning-only smoke tests kept violating the revised disposition contract by emitting `Disposition: QUEUED_FOR_PLANNING_ONLY`
- operator attention was spent on runtime speculation instead of a clean incident split and repair path

## Findings

### 1. Real bwrap failures did occur

The `bwrap` bootstrap error was not imaginary.

Evidence:

- `~/.openclaw/agents/main/sessions/10e04b96-60eb-4942-8b81-0edfc4b6d867.jsonl`
- `~/.openclaw/agents/lobster-builder/sessions/47070044-28a8-43aa-bf0f-6e00970d4720-topic-444.jsonl`

Representative failure text:

- `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`

This confirms that at least some delegated Codex execution paths were genuinely failing before command start.

### 2. The host namespace theory was overstated

The daytime recovery guidance suggested user namespaces might be disabled.

Current host checks do not support that theory:

- `kernel.unprivileged_userns_clone = 1`
- `user.max_user_namespaces = 256252`

That means the problem was not well described as a blanket host setting failure. It was more likely a session-specific or launcher-specific bubblewrap/bootstrap path failure.

### 3. A separate OpenClaw embedded-run bug was also present

The main OpenClaw lane was independently failing on tool-enabled runs with:

- `The following tools cannot be used with reasoning.effort 'minimal': image_gen, web_search.`

Evidence:

- `/tmp/openclaw/openclaw-2026-04-21.log`

Installed version at incident time:

- `OpenClaw 2026.4.15 (041266a)`

The installed changelog already documents a later fix:

- `CHANGELOG.md` notes: `Agents/OpenAI: map minimal thinking to OpenAI's supported low reasoning effort for GPT-5.4 requests, so embedded runs stop failing request validation.`

So part of the orchestration failure was a versioned runtime bug, not just a sandbox failure.

### 4. BearClaw violated the operator contract

The revised contract required operator-facing dispositions:

- `build-now`
- `hold`
- `needs-input`

But the live system still produced non-contract outputs such as:

- `Disposition: needs-input due environment hard block`
- `Disposition: QUEUED_FOR_PLANNING_ONLY`

This was a real orchestration/contract bug, independent of runtime instability.

## Remediation Performed

### Doctrine and prompt alignment

Updated the neutral orchestrator workspace doctrine to:

- preserve `build-now` intent across runtime failures
- separate disposition from execution status
- require planning-only requests to map to `hold`
- explicitly disallow queue-like disposition labels on the operator-facing surface

Updated the live BearClaw prompt in `~/.openclaw/openclaw.json` to reflect the same rules.

### Runtime upgrade

Updated OpenClaw from:

- `2026.4.15`

to:

- `2026.4.20`

### Post-update repair

The packaged `2026.4.20` install had its own local packaging defect:

- `openclaw update` completed the version bump
- `openclaw doctor` initially failed with `Cannot find module 'grammy'`
- the updated package imported `grammy` from the Telegram extension but did not include it in `dependencies`

Local repair performed:

- installed `grammy` into the package root
- reran `openclaw doctor`
- verified gateway health after repair

Doctor completed successfully with:

- plugin deps loaded
- Telegram OK
- no plugin load errors

## Current State

As of the latest remediation pass:

- OpenClaw is on `2026.4.20`
- gateway health is `OK`
- doctor completes successfully
- the original `minimal` reasoning crash on `2026.4.15` is no longer the active blocker

One BearClaw behavior bug still remains:

- planning-only smoke tests still emitted `Disposition: QUEUED_FOR_PLANNING_ONLY` in observed runs, even after prompt tightening

That means the infrastructure is healthier, but prompt-only enforcement is still insufficient to guarantee contract-correct disposition labels.

## Recommended Next Step

Move the disposition constraint out of prompt-only enforcement and into runtime logic or a reply post-processor:

- reject or rewrite any operator-facing disposition outside `build-now`, `hold`, `needs-input`
- map planning-only requests deterministically to `hold`
- preserve `build-now` plus `Status: blocked` whenever execution is blocked after a valid task contract exists

## Evidence Surface

- `~/.openclaw/openclaw.json`
- `/tmp/openclaw/openclaw-2026-04-21.log`
- `~/.openclaw/agents/main/sessions/10e04b96-60eb-4942-8b81-0edfc4b6d867.jsonl`
- `~/.openclaw/agents/main/sessions/70a24bc1-fb3c-4ce5-892f-6fca965b8022.jsonl`
- `~/.openclaw/agents/lobster-builder/sessions/47070044-28a8-43aa-bf0f-6e00970d4720-topic-444.jsonl`
