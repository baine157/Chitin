import test from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { enforcePolicy, parseTaskPacket, parseRunnerPolicy, ValidationError } from "../src/validation.ts";

const now = new Date().toISOString();
const repoRoot = join(import.meta.dirname, "..", "..");

test("validates and enforces a manifest-like lane policy", () => {
  const packet = parseTaskPacket({
    schemaVersion: 1,
    id: "task_20260501_smoke",
    idempotencyKey: "idem_20260501_smoke",
    title: "smoke",
    laneId: "orchestrator_control_plane_health",
    workspace: repoRoot,
    command: { id: "echo_smoke", argv: ["printf", "durable-runner-ok"] },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }, { type: "stdout_contains", value: "durable-runner-ok" }],
    createdAt: now,
    updatedAt: now,
  });
  const policy = parseRunnerPolicy({
    schemaVersion: 1,
    laneId: "orchestrator_control_plane_health",
    workspace: repoRoot,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { echo_smoke: ["printf", "durable-runner-ok"] },
    forbiddenActions: ["submit", "send", "upload", "attest", "sign", "certify", "finalize"],
    humanGates: ["any_external_action"],
  });
  assert.doesNotThrow(() => enforcePolicy(packet, policy));
});

test("rejects shell mode and credential/final-action argv terms", () => {
  assert.throws(
    () =>
      parseTaskPacket({
        schemaVersion: 1,
        id: "task_20260501_bad",
        idempotencyKey: "idem_20260501_bad",
        title: "bad",
        laneId: "lane",
        workspace: "/tmp",
        command: { id: "bad", argv: ["echo", "password"], shell: false },
        state: "queued",
        authorityLevel: 1,
        externalEffect: { allowed: false, description: "none" },
        approvalGates: [],
        verificationRequired: [{ type: "exit_code_zero" }],
        createdAt: now,
        updatedAt: now,
      }),
    ValidationError,
  );
});

test("rejects packet authority above lane policy", () => {
  const packet = parseTaskPacket({
    schemaVersion: 1,
    id: "task_20260501_high",
    idempotencyKey: "idem_20260501_high",
    title: "high",
    laneId: "lane",
    workspace: "/tmp",
    command: { id: "noop", argv: ["printf", "ok"] },
    state: "queued",
    authorityLevel: 3,
    externalEffect: { allowed: false, description: "none" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }],
    createdAt: now,
    updatedAt: now,
  });
  const policy = parseRunnerPolicy({
    schemaVersion: 1,
    laneId: "lane",
    workspace: "/tmp",
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { noop: ["printf", "ok"] },
    forbiddenActions: [],
    humanGates: [],
  });
  assert.throws(() => enforcePolicy(packet, policy), /authorityLevel/);
});
