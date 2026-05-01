#!/usr/bin/env python3
"""Tests for lane promotion check semantics."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts.cos import lane_promotion_check as promotion


class LanePromotionCheckTests(unittest.TestCase):
    def test_real_onboarding_lane_is_promotable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dash_path = tmp_path / "dashboard.json"
            smoke_path = tmp_path / "smoke.json"
            canary_path = tmp_path / "canary.json"
            execution_smoke_path = tmp_path / "execution-smoke.json"
            timestamp = datetime.now(timezone.utc).isoformat()
            dash_path.write_text(
                json.dumps(
                    {
                        "packet_execution": {
                            "recent": [
                                {
                                    "lane": "onboarding_application_packet_audit",
                                    "packet_id": "PKT-test",
                                    "status": "BLOCKED",
                                    "external_effect": {"occurred": False},
                                }
                            ]
                        },
                        "system_trust": {
                            "execution_substrate": {
                                "control_plane_vs_execution_plane": {
                                    "gateway_alive": "ok",
                                    "hooks_registry_ready": "ok",
                                    "shell_execution_usable": "ok",
                                    "openclaw_agent_execution_usable": "ok",
                                    "telegram_cos_session": "unverified",
                                    "native_relay_usable": "unverified",
                                },
                                "gateway_health": {"role": "necessary_but_insufficient"},
                                "telegram_session_native_hook": {"status": "unverified"},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            smoke_path.write_text(json.dumps({"status": "ok", "timestamp": timestamp}), encoding="utf-8")
            canary_path.write_text(json.dumps({"status": "ok", "timestamp": timestamp}), encoding="utf-8")
            execution_smoke_path.write_text(json.dumps({"status": "ok", "timestamp": timestamp}), encoding="utf-8")

            with mock.patch.object(promotion, "DASHBOARD_PATH", dash_path), mock.patch.object(
                promotion, "NATIVE_HOOK_SMOKE_PATH", smoke_path
            ), mock.patch.object(promotion, "LOCAL_WRITE_CANARY_PATH", canary_path), mock.patch.object(
                promotion, "EXECUTION_PLANE_SMOKE_PATH", execution_smoke_path
            ):
                result = promotion.run_checks("onboarding_application_packet_audit")

        self.assertEqual(result["promotion_status"], "promotable")
        self.assertEqual(result["target_trust_level"], "bounded_portal_adjacent_work")
        self.assertIn("manifest_validates", result["checks"])
        self.assertTrue(result["evidence"])

    def test_unsupported_lane_is_not_promotable(self) -> None:
        result = promotion.run_checks("gbrain_research_fellow")

        self.assertEqual(result["promotion_status"], "not_promotable")
        self.assertFalse(result["checks"]["supported_lane"]["ok"])

    def test_gateway_health_does_not_imply_telegram_hook_health(self) -> None:
        dashboard = {
            "packet_execution": {
                "recent": [
                    {
                        "lane": "onboarding_application_packet_audit",
                        "packet_id": "PKT-test",
                        "status": "BLOCKED",
                        "external_effect": {"occurred": False},
                    }
                ]
            },
            "system_trust": {
                "execution_substrate": {
                    "control_plane_vs_execution_plane": {
                        "gateway_alive": "ok",
                        "hooks_registry_ready": "ok",
                        "shell_execution_usable": "ok",
                        "openclaw_agent_execution_usable": "ok",
                        "telegram_cos_session": "unverified",
                        "native_relay_usable": "unverified",
                    },
                    "gateway_health": {"role": "necessary_but_insufficient"},
                    "telegram_session_native_hook": {"status": "unverified"},
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dash_path = tmp_path / "dashboard.json"
            smoke_path = tmp_path / "smoke.json"
            canary_path = tmp_path / "canary.json"
            execution_smoke_path = tmp_path / "execution-smoke.json"
            timestamp = datetime.now(timezone.utc).isoformat()
            dash_path.write_text(json.dumps(dashboard), encoding="utf-8")
            smoke_path.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "timestamp": timestamp,
                        "telegram_session_native_hook": {"status": "unverified"},
                        "gateway_health": {"role": "necessary_but_insufficient"},
                    }
                ),
                encoding="utf-8",
            )
            canary_path.write_text(json.dumps({"status": "ok", "timestamp": timestamp}), encoding="utf-8")
            execution_smoke_path.write_text(json.dumps({"status": "ok", "timestamp": timestamp}), encoding="utf-8")

            with mock.patch.object(promotion, "DASHBOARD_PATH", dash_path), mock.patch.object(
                promotion, "NATIVE_HOOK_SMOKE_PATH", smoke_path
            ), mock.patch.object(promotion, "LOCAL_WRITE_CANARY_PATH", canary_path), mock.patch.object(
                promotion, "EXECUTION_PLANE_SMOKE_PATH", execution_smoke_path
            ):
                result = promotion.run_checks("onboarding_application_packet_audit")

        check = result["checks"]["telegram_hook_not_inferred_from_gateway"]
        self.assertTrue(check["ok"])
        self.assertIn("telegram_session_native_hook=unverified", check["detail"])


if __name__ == "__main__":
    unittest.main()
