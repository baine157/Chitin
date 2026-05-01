#!/usr/bin/env python3
"""Tests for execution-plane truth separation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.observability import collect_dashboard
from scripts.observability import execution_plane_smoke


class ExecutionPlaneTruthTests(unittest.TestCase):
    def test_gateway_green_does_not_make_execution_plane_ok(self) -> None:
        result = collect_dashboard.native_hook_truth(
            closeouts=[],
            write_canary={"status": "ok"},
            live_session_smoke={"status": "unverified"},
            execution_plane_smoke={
                "status": "unverified",
                "signals": {
                    "gateway": {"status": "ok"},
                    "hooks_registry": {"status": "ok"},
                    "shell_execution": {"status": "ok"},
                    "openclaw_agent_execution": {"status": "unverified"},
                    "codex_session_attach": {"status": "unverified"},
                    "external_action_verification": {"status": "unverified"},
                },
            },
        )

        split = result["control_plane_vs_execution_plane"]
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(split["gateway_alive"], "ok")
        self.assertEqual(split["native_relay_usable"], "unverified")
        self.assertEqual(split["shell_execution_usable"], "ok")
        self.assertIn("Do not claim sent/submitted/finalized", result["external_action_gate"])

    def test_execution_plane_failed_shell_degrades_substrate(self) -> None:
        result = collect_dashboard.native_hook_truth(
            closeouts=[],
            write_canary={"status": "ok"},
            live_session_smoke={"status": "ok"},
            execution_plane_smoke={
                "status": "degraded",
                "signals": {
                    "gateway": {"status": "ok"},
                    "hooks_registry": {"status": "ok"},
                    "shell_execution": {"status": "failed"},
                    "openclaw_agent_execution": {"status": "unverified"},
                },
            },
        )

        self.assertEqual(result["status"], "degraded")

    def test_execution_plane_smoke_output_is_dashboard_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "state" / "observability" / "execution-plane-smoke.json"
            with mock.patch.object(execution_plane_smoke, "OBSERVABILITY_DIR", out.parent), mock.patch.object(
                execution_plane_smoke, "REPO_ROOT", Path(tmp)
            ), mock.patch.object(execution_plane_smoke, "gateway_probe", return_value={"status": "ok"}), mock.patch.object(
                execution_plane_smoke, "hooks_check", return_value={"status": "ok"}
            ), mock.patch.object(
                execution_plane_smoke, "shell_execution", return_value={"status": "ok"}
            ), mock.patch.object(
                execution_plane_smoke, "codex_cli", return_value={"status": "ok"}
            ), mock.patch.object(
                execution_plane_smoke,
                "agent_smoke",
                return_value={"status": "unverified", "skipped": True},
            ):
                args = type(
                    "Args",
                    (),
                    {
                        "include_agent_smoke": False,
                        "agent_timeout": 180,
                    },
                )()
                payload = execution_plane_smoke.build_payload(args)
                execution_plane_smoke.write_json(out, payload)

            saved = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(saved["status"], "unverified")
        self.assertEqual(saved["signals"]["shell_execution"]["status"], "ok")
        self.assertEqual(saved["signals"]["external_action_verification"]["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
