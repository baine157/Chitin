import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, utimes, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DurableRunnerStore } from "../src/store.ts";
import { DurableRunner, loadPolicy } from "../src/runner.ts";
import type { RunnerPolicy, TaskPacket } from "../src/types.ts";

const now = new Date().toISOString();

test("processes a queued task only after verification passes", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const policy: RunnerPolicy = {
    schemaVersion: 1,
    laneId: "test_lane",
    workspace,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { smoke: ["printf", "durable-runner-ok"] },
    forbiddenActions: [],
    humanGates: [],
  };
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_runner",
    idempotencyKey: "idem_20260501_runner",
    title: "runner smoke",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "durable-runner-ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }, { type: "stdout_contains", value: "durable-runner-ok" }],
    createdAt: now,
    updatedAt: now,
  };
  const store = new DurableRunnerStore(root);
  await store.enqueue(packet);
  const runner = new DurableRunner({ root, policy, workerId: "test-worker", leaseMs: 60_000 });
  assert.equal(await runner.tick(), true);
  const done = JSON.parse(await readFile(join(root, "tasks", "done", `${packet.id}.json`), "utf8"));
  assert.equal(done.state, "done");
  const events = await readFile(join(root, "events", `${packet.id}.jsonl`), "utf8");
  assert.match(events, /verification_passed/);
});

test("moves tasks with missing approval gates to waiting_approval", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const policy: RunnerPolicy = {
    schemaVersion: 1,
    laneId: "test_lane",
    workspace,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { smoke: ["printf", "ok"] },
    forbiddenActions: [],
    humanGates: ["before_execute"],
  };
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_gate",
    idempotencyKey: "idem_20260501_gate",
    title: "approval gate",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: ["before_execute"],
    approvedGates: [],
    verificationRequired: [{ type: "exit_code_zero" }],
    createdAt: now,
    updatedAt: now,
  };
  const store = new DurableRunnerStore(root);
  await store.enqueue(packet);
  const runner = new DurableRunner({ root, policy, workerId: "test-worker", leaseMs: 60_000 });
  assert.equal(await runner.tick(), true);
  const waiting = JSON.parse(await readFile(join(root, "tasks", "waiting_approval", `${packet.id}.json`), "utf8"));
  assert.equal(waiting.state, "waiting_approval");
});

test("does not mark a task done when verification fails", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const marker = join(workspace, "marker.txt");
  await writeFile(marker, "not used", "utf8");
  const policy: RunnerPolicy = {
    schemaVersion: 1,
    laneId: "test_lane",
    workspace,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { smoke: ["printf", "wrong"] },
    forbiddenActions: [],
    humanGates: [],
  };
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_verify_fail",
    idempotencyKey: "idem_20260501_verify_fail",
    title: "verify fail",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "wrong"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }, { type: "stdout_contains", value: "expected" }],
    createdAt: now,
    updatedAt: now,
  };
  const store = new DurableRunnerStore(root);
  await store.enqueue(packet);
  const runner = new DurableRunner({ root, policy, workerId: "test-worker", leaseMs: 60_000 });
  assert.equal(await runner.tick(), true);
  const failed = JSON.parse(await readFile(join(root, "tasks", "failed", `${packet.id}.json`), "utf8"));
  assert.equal(failed.state, "failed");
});

test("idempotency collision is rejected", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const store = new DurableRunnerStore(root);
  const base: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_collision_a",
    idempotencyKey: "idem_collision_key",
    title: "collision A",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }],
    createdAt: now,
    updatedAt: now,
  };
  await store.enqueue(base);
  await assert.rejects(
    () =>
      store.enqueue({
        ...base,
        id: "task_20260501_collision_b",
        title: "collision B",
      }),
    /idempotency collision/,
  );
});

test("approval transitions waiting_approval back to queued", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const policy: RunnerPolicy = {
    schemaVersion: 1,
    laneId: "test_lane",
    workspace,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { smoke: ["printf", "ok"] },
    forbiddenActions: [],
    humanGates: ["before_execute"],
  };
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_approve",
    idempotencyKey: "idem_20260501_approve",
    title: "approval required",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: ["before_execute"],
    approvedGates: [],
    verificationRequired: [{ type: "exit_code_zero" }],
    createdAt: now,
    updatedAt: now,
  };
  const store = new DurableRunnerStore(root);
  await store.enqueue(packet);
  const runner = new DurableRunner({ root, policy, workerId: "test-worker", leaseMs: 60_000 });
  await runner.tick();
  await store.approve(packet.id, "before_execute");
  const queued = JSON.parse(await readFile(join(root, "tasks", "queued", `${packet.id}.json`), "utf8"));
  assert.equal(queued.state, "queued");
  assert.deepEqual(queued.approvedGates, ["before_execute"]);
});

test("loads existing lane manifest YAML into a runnable policy", async () => {
  const repoRoot = join(import.meta.dirname, "..", "..");
  const policy = await loadPolicy(join(repoRoot, "lane-manifests", "orchestrator_control_plane_health.yaml"));
  assert.equal(policy.laneId, "orchestrator_control_plane_health");
  assert.equal(policy.workspace, repoRoot);
  assert.equal(policy.authorityMaxLevel, 2);
  assert.equal(policy.externalCommitAllowed, false);
  assert.ok(policy.allowedCommands.orchestrator_control_plane_unittest);
});

test("watch emits queue-supervisor style health snapshot with lease heartbeat metrics", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const policy: RunnerPolicy = {
    schemaVersion: 1,
    laneId: "test_lane",
    workspace,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { smoke: ["printf", "watch-ok"] },
    forbiddenActions: [],
    humanGates: [],
  };
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_watch",
    idempotencyKey: "idem_20260501_watch",
    title: "watch smoke",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "watch-ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }, { type: "stdout_contains", value: "watch-ok" }],
    createdAt: now,
    updatedAt: now,
  };
  const store = new DurableRunnerStore(root);
  await store.enqueue(packet);
  const runner = new DurableRunner({ root, policy, workerId: "watch-worker", leaseMs: 2_000 });
  await runner.watch({
    root,
    policy,
    workerId: "watch-worker",
    leaseMs: 2_000,
    pollMs: 5,
    heartbeatEveryMs: 200,
    maxLoops: 2,
  });
  const health = JSON.parse(await readFile(join(root, "state", "watch-health.json"), "utf8"));
  assert.equal(health.status, "QUEUE_SUPERVISOR_CLEAR");
  assert.equal(health.execution_plane_truth.queue_liveness, "necessary_but_insufficient");
  assert.equal(health.execution_plane_truth.lease_heartbeat, "required_for_running_truth");
  assert.equal(typeof health.metrics.renewals, "number");
  assert.equal(typeof health.metrics.processed, "number");
  assert.equal(typeof health.metrics.queueDiagnosisAlerts, "number");
  assert.equal(typeof health.metrics.quarantinedParseErrors, "number");
  assert.equal(typeof health.metrics.lockContentionSkips, "number");
});

test("quarantines malformed queued packets instead of silent skip", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const queueDir = join(root, "tasks", "queued");
  await writeFile(join(root, "dummy.txt"), "x", "utf8");
  const store = new DurableRunnerStore(root);
  await store.init();
  await writeFile(join(queueDir, "task_bad_parse_001.json"), "{not-json", "utf8");
  const runner = new DurableRunner({
    root,
    policy: {
      schemaVersion: 1,
      laneId: "test_lane",
      workspace: "/tmp",
      authorityMaxLevel: 2,
      externalCommitAllowed: false,
      allowedCommands: { smoke: ["printf", "ok"] },
      forbiddenActions: [],
      humanGates: [],
    },
    workerId: "test-worker",
    leaseMs: 1000,
  });
  assert.equal(await runner.tick(), false);
  await assert.doesNotReject(() => readFile(join(root, "tasks", "quarantine_parse_error", "task_bad_parse_001.json"), "utf8"));
});

test("status reports artifact existence flags", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const store = new DurableRunnerStore(root);
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260501_status_artifacts",
    idempotencyKey: "idem_20260501_status_artifacts",
    title: "status artifact flags",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }],
    createdAt: now,
    updatedAt: now,
  };
  await store.enqueue(packet);
  const runner = new DurableRunner({
    root,
    policy: {
      schemaVersion: 1,
      laneId: "test_lane",
      workspace,
      authorityMaxLevel: 2,
      externalCommitAllowed: false,
      allowedCommands: { smoke: ["printf", "ok"] },
      forbiddenActions: [],
      humanGates: [],
    },
    workerId: "test-worker",
    leaseMs: 60_000,
  });
  await runner.tick();
  const status = await store.readStatus(packet.id);
  const artifacts = (status as { artifacts?: Record<string, unknown> }).artifacts;
  assert.equal(artifacts?.stdoutExists, true);
  assert.equal(artifacts?.stderrExists, true);
  assert.equal(artifacts?.verificationExists, true);
});

test("store blocks done transition without verification artifact", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const store = new DurableRunnerStore(root);
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260504_done_guard",
    idempotencyKey: "idem_20260504_done_guard",
    title: "done transition guard",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }],
    createdAt: now,
    updatedAt: now,
  };
  await store.enqueue(packet);
  const claimed = await store.claimNext("worker-guard", 60_000);
  assert.ok(claimed);
  await assert.rejects(() => store.transition(claimed.packet, "done", { runId: claimed.runId }), /verification artifact missing/);
});

test("proveUsage returns machine-readable durable evidence", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const workspace = await mkdtemp(join(tmpdir(), "durable-workspace-"));
  const policy: RunnerPolicy = {
    schemaVersion: 1,
    laneId: "test_lane",
    workspace,
    authorityMaxLevel: 2,
    externalCommitAllowed: false,
    allowedCommands: { smoke: ["printf", "prove-ok"] },
    forbiddenActions: [],
    humanGates: [],
  };
  const store = new DurableRunnerStore(root);
  const packet: TaskPacket = {
    schemaVersion: 1,
    id: "task_20260504_prove",
    idempotencyKey: "idem_20260504_prove",
    title: "proof smoke",
    laneId: "test_lane",
    workspace,
    command: { id: "smoke", argv: ["printf", "prove-ok"], shell: false },
    state: "queued",
    authorityLevel: 2,
    externalEffect: { allowed: false, description: "local stdout only" },
    approvalGates: [],
    verificationRequired: [{ type: "exit_code_zero" }, { type: "stdout_contains", value: "prove-ok" }],
    createdAt: now,
    updatedAt: now,
  };
  await store.enqueue(packet);
  const runner = new DurableRunner({ root, policy, workerId: "prove-worker", leaseMs: 60_000 });
  await runner.tick();
  const proof = await store.proveUsage(60_000);
  assert.equal(proof.status, "ok");
  assert.equal(proof.used, true);
  const evidence = proof.evidence as { events: { fileCount: number }; runs: { taskDirCount: number } };
  assert.ok(evidence.events.fileCount >= 1);
  assert.ok(evidence.runs.taskDirCount >= 1);
});

test("cleanup-quarantine honors default 14-day retention semantics", async () => {
  const root = await mkdtemp(join(tmpdir(), "durable-runner-"));
  const store = new DurableRunnerStore(root);
  await store.init();
  const quarantineDir = join(root, "tasks", "quarantine_parse_error");
  await mkdir(quarantineDir, { recursive: true });
  const oldPath = join(quarantineDir, "task_old_001.json");
  const freshPath = join(quarantineDir, "task_fresh_001.json");
  await writeFile(oldPath, "bad", "utf8");
  await writeFile(freshPath, "bad", "utf8");
  const sixteenDaysAgo = new Date(Date.now() - 16 * 24 * 60 * 60 * 1000);
  await utimes(oldPath, sixteenDaysAgo, sixteenDaysAgo);

  const dryRun = await store.cleanupQuarantine(14 * 24, true);
  assert.equal(dryRun.prunableCount, 1);
  await assert.doesNotReject(() => readFile(oldPath, "utf8"));
  await assert.doesNotReject(() => readFile(freshPath, "utf8"));

  const actual = await store.cleanupQuarantine(14 * 24, false);
  assert.equal(actual.prunedCount, 1);
  await assert.rejects(() => readFile(oldPath, "utf8"));
  await assert.doesNotReject(() => readFile(freshPath, "utf8"));
  const ledger = await readFile(join(root, "ledger", "quarantine_cleanup.jsonl"), "utf8");
  assert.match(ledger, /"kind":"quarantine_cleanup"/);
  assert.match(ledger, /"prunedCount":1/);
});
