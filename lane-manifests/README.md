# Lane Manifests

Lane manifests define the minimum control-plane contract for serious OpenClaw
workspaces.

They are not domain truth. They are the orchestration boundary:

- workspace owner path
- allowed packet types
- validator command
- maximum live-run authority
- external-effect policy
- forbidden final actions
- human gates
- canary command

Current manifest-backed lanes:

- `orchestrator_control_plane_health.yaml`
- `onboarding_application_packet_audit.yaml`
- `medical_logs_lobster.yaml`
- `gbrain_research_fellow.yaml`
- `deck_ops_study_cards.yaml`
- `course_live_notes.yaml`
- `rescue_gateway.yaml`
- `deepsea_general_topic_routing.yaml`

Validate one manifest:

```bash
python3 scripts/cos/validate_lane_manifest.py lane-manifests/gbrain_research_fellow.yaml
```

Validate all manifests:

```bash
for manifest in lane-manifests/*.yaml; do
  python3 scripts/cos/validate_lane_manifest.py "$manifest"
done
```

## Boundary Rule

All current manifests are authority level 2 or lower and disallow external
commit. Sending, submitting, uploading, attesting, signing, certifying,
finalizing, credential handling, and portal login remain human-gated.
