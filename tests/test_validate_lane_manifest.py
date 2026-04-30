#!/usr/bin/env python3
"""Tests for guarded-runner lane manifest validation."""

from __future__ import annotations

import copy
import unittest

from scripts.cos.validate_lane_manifest import ManifestValidationError, validate_manifest_payload


def valid_manifest() -> dict:
    return {
        "lane_id": "onboarding_application_packet_audit",
        "workspace": "/home/baine/openclaw/onboarding-ops",
        "allowed_packet_types": ["application_packet_audit"],
        "commands": {
            "validator": {
                "id": "validate_comphealth_mycomphealth_packet",
                "argv": [
                    "python3",
                    "/home/baine/openclaw/onboarding-ops/scripts/validate-application-packet.py",
                    "--packet-dir",
                    "/home/baine/openclaw/onboarding-ops/work/application-packets/comphealth-mycomphealth",
                    "--json",
                ],
            }
        },
        "live_run": {
            "allowed": True,
            "authority_max_level": 2,
            "external_commit_allowed": False,
        },
        "outputs": {
            "status_path": "/home/baine/openclaw/orchestrator/state/observability/lane-status/onboarding_application_packet_audit.json",
            "closeout_dir": "/home/baine/openclaw/orchestrator/state/cos/packets/closeouts",
        },
        "forbidden_actions": [
            "portal_login",
            "bitwarden",
            "password_token_mfa_cookie_session_handling",
            "submit",
            "send",
            "upload",
            "attest",
            "sign",
            "certify",
            "finalize",
            "external_commit",
        ],
        "human_gates": [
            "post_login_fields_inaccessible",
            "any_external_action",
            "credential_needed",
            "authority_level_gt_2",
        ],
        "canary": {
            "id": "onboarding_application_packet_audit_canary",
            "command": [
                "python3",
                "/home/baine/openclaw/onboarding-ops/scripts/validate-application-packet.py",
                "--packet-dir",
                "/home/baine/openclaw/onboarding-ops/work/application-packets/comphealth-mycomphealth",
                "--json",
            ],
            "expected_statuses": ["BLOCKED", "PARTIAL"],
        },
    }


class LaneManifestValidationTests(unittest.TestCase):
    def assert_invalid(self, manifest: dict, expected: str) -> None:
        with self.assertRaisesRegex(ManifestValidationError, expected):
            validate_manifest_payload(manifest)

    def test_valid_onboarding_manifest_passes(self) -> None:
        manifest = validate_manifest_payload(valid_manifest())
        self.assertEqual(manifest["lane_id"], "onboarding_application_packet_audit")
        self.assertEqual(manifest["live_run"]["authority_max_level"], 2)

    def test_missing_required_field_fails(self) -> None:
        manifest = valid_manifest()
        del manifest["commands"]
        self.assert_invalid(manifest, "commands must be an object")

    def test_external_commit_allowed_true_fails(self) -> None:
        manifest = valid_manifest()
        manifest["live_run"]["external_commit_allowed"] = True
        self.assert_invalid(manifest, "external_commit_allowed must be false")

    def test_live_run_allowed_false_fails(self) -> None:
        manifest = valid_manifest()
        manifest["live_run"]["allowed"] = False
        self.assert_invalid(manifest, "live_run.allowed must be true")

    def test_authority_max_level_three_fails(self) -> None:
        manifest = valid_manifest()
        manifest["live_run"]["authority_max_level"] = 3
        self.assert_invalid(manifest, "authority_max_level must be <= 2")

    def test_missing_final_action_forbidden_action_fails(self) -> None:
        manifest = valid_manifest()
        manifest["forbidden_actions"].remove("finalize")
        self.assert_invalid(manifest, "missing required final-action prohibition: finalize")

    def test_unsafe_validator_command_fails(self) -> None:
        manifest = valid_manifest()
        manifest["commands"]["validator"]["argv"] = ["bw", "get", "password", "example"]
        self.assert_invalid(manifest, "validator.argv contains unsafe")

    def test_invalid_canary_status_fails(self) -> None:
        manifest = valid_manifest()
        manifest["canary"]["expected_statuses"] = ["DONE", "MAYBE"]
        self.assert_invalid(manifest, "unsupported status: MAYBE")

    def test_fixture_mutation_isolated(self) -> None:
        manifest = valid_manifest()
        copied = copy.deepcopy(manifest)
        validate_manifest_payload(copied)
        self.assertEqual(manifest["live_run"]["external_commit_allowed"], False)


if __name__ == "__main__":
    unittest.main()
