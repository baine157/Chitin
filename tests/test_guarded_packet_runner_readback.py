#!/usr/bin/env python3
"""Tests for guarded packet runner closeout readback quality."""

from __future__ import annotations

import json
import unittest

from scripts.cos.guarded_packet_runner import closeout_readback


def command_result(payload: dict, *, ok: bool = False, exit_code: int = 3) -> dict:
    return {
        "id": "validate_comphealth_mycomphealth_packet",
        "ok": ok,
        "exit_code": exit_code,
        "output_excerpt": json.dumps(payload),
    }


class GuardedPacketRunnerReadbackTests(unittest.TestCase):
    def test_post_login_blocker_maps_to_approval_gate(self) -> None:
        readback = closeout_readback(
            "BLOCKED",
            [
                command_result(
                    {
                        "status": "BLOCKED",
                        "result": "application packet validation blocked on active local packet blockers",
                        "issues": [],
                        "warnings": [],
                        "active_blocker_count": 5,
                        "checks": {
                            "field_map_parses": True,
                            "active_blockers_present": True,
                            "readback_present": True,
                            "verification_packet_present": True,
                            "final_action_prohibitions_present": True,
                            "post_login_fields_inaccessible": True,
                            "sensitive_values_absent": True,
                            "credentials_accessed": False,
                        },
                        "external_effect": {"occurred": False, "details": "none"},
                        "credentials_accessed": False,
                        "final_actions_performed": False,
                    }
                )
            ],
        )

        self.assertEqual(readback["blocked_reason"]["code"], "approval_gate")
        self.assertIn("credential_mfa_gate", readback["blocked_reason"]["secondary_codes"])
        self.assertEqual(readback["validator"]["active_blocker_count"], 5)

    def test_missing_artifact_issue_maps_to_missing_input(self) -> None:
        readback = closeout_readback(
            "BLOCKED",
            [
                command_result(
                    {
                        "status": "BLOCKED",
                        "result": "application packet validation blocked",
                        "issues": ["readback.md is missing"],
                        "checks": {},
                    }
                )
            ],
        )
        self.assertEqual(readback["blocked_reason"]["code"], "missing_input")

    def test_schema_issue_maps_to_schema_mismatch(self) -> None:
        readback = closeout_readback(
            "BLOCKED",
            [
                command_result(
                    {
                        "status": "BLOCKED",
                        "result": "application packet validation blocked",
                        "issues": ["field-map.json invalid json: expected value"],
                        "checks": {},
                    }
                )
            ],
        )
        self.assertEqual(readback["blocked_reason"]["code"], "schema_mismatch")

    def test_stale_artifact_issue_maps_to_stale_artifact(self) -> None:
        readback = closeout_readback(
            "BLOCKED",
            [
                command_result(
                    {
                        "status": "BLOCKED",
                        "result": "application packet validation blocked",
                        "issues": ["stale artifact: readback.md age_days=42.0 exceeds 30"],
                        "checks": {"required_artifacts_fresh": False},
                    }
                )
            ],
        )
        self.assertEqual(readback["blocked_reason"]["code"], "stale_artifact")

    def test_unstructured_failure_maps_to_validator_failed(self) -> None:
        readback = closeout_readback(
            "BLOCKED",
            [
                {
                    "id": "validate_comphealth_mycomphealth_packet",
                    "ok": False,
                    "exit_code": 3,
                    "output_excerpt": "not json",
                }
            ],
        )
        self.assertEqual(readback["blocked_reason"]["code"], "validator_failed")


if __name__ == "__main__":
    unittest.main()
