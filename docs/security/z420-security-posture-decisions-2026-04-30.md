# Z420 Security Posture Decisions - 2026-04-30

Scope: local OpenClaw/Z420 security posture decisions after the April stability
work. This is a decision register, not a remediation script.

## Current Decision Table

| item | decision | status | next check |
| --- | --- | --- | --- |
| gateway password | keep password auth, but config must reference `OPENCLAW_GATEWAY_TOKEN` instead of storing an inline secret | accepted with hygiene requirement | every runtime validation |
| sandbox-off agents | acceptable only as a single-operator local workstation risk, with external effects gated | accepted with constraints | before autonomy expansion |
| trusted proxy headers unset | acceptable while gateway remains loopback/private and not public internet | accepted for local-first posture | if exposure changes |
| deep gateway probe timeout | watch condition, not proof of execution failure when shell and agent smokes are green | watch | execution-plane health cycle |
| SSH on all interfaces | not remediated in this slice; requires explicit network/access decision | unresolved | next host-security pass |
| Tailnet Serve control UI | not remediated in this slice; requires ACL/tailnet trust review | unresolved | next host-security pass |
| duplicate gateway listeners | watch for stale processes; do not kill without session-impact check | watch | incident response or weekly check |
| browser CDP on loopback | acceptable only during intentional browser work; close stale profiles when work is done | watch | browser-lane closeout |
| Bitwarden session residue in logs | do not expand secret handling in chat; prepare redaction/quarantine separately | unresolved | secret-hygiene pass |

## Verified Gateway Password Shape

The gateway is configured for password auth, but the password field is an
environment reference:

```text
gateway.auth.mode = password
gateway.auth.password.source = env
gateway.auth.password.id = OPENCLAW_GATEWAY_TOKEN
gateway.bind = loopback
gateway.auth.allowTailscale = false
```

That is acceptable for the current local-first posture. A literal password in
`~/.openclaw/openclaw.json` would be a blocker.

## Promotion Rule

Do not expand autonomy while any of these are true:

- execution-plane smoke is not fresh/ok
- native-hook/live-session smoke is stale or degraded for the session in scope
- security audit has a new critical finding
- gateway exposure changes without a new posture decision
- a task requires final external action without action-specific readback

## Next High-Value Security Slice

Prepare a read-only host-security pass that answers only:

- Is SSH reachable beyond the intended network boundary?
- Is Tailnet Serve exposing only the intended OpenClaw surfaces?
- Are duplicate gateway listeners active or stale?
- Are stale browser/CDP profiles still running after browser work?
- Where can `BW_SESSION` residue be redacted without losing useful audit logs?
