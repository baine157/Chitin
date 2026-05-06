import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename } from "node:path";
import { parse as parseYaml } from "./yaml.ts";
import { DurableRunnerStore } from "./store.ts";
import { enforcePolicy, parseRunnerPolicy } from "./validation.ts";
import type { RunnerPolicy, TaskPacket, VerificationResult, VerificationSpec, WatchHealthSnapshot } from "./types.ts";

export interface RunnerOptions {
  root: string;
  policy: RunnerPolicy;
  workerId: string;
  leaseMs: number;
}

export interface WatchOptions extends RunnerOptions {
  pollMs: number;
  maxLoops?: number;
  heartbeatEveryMs?: number;
}

export class DurableRunner {
  private readonly options: RunnerOptions;
  private readonly store: DurableRunnerStore;

  constructor(options: RunnerOptions) {
    this.options = options;
    this.store = new DurableRunnerStore(options.root);
  }

  async tick(): Promise<boolean> {
    const claimed = await this.store.claimNext(this.options.workerId, this.options.leaseMs);
    if (!claimed) return false;
    const { packet, runId } = claimed;
    await this.processClaimed(packet, runId);
    return true;
  }

  async watch(options: WatchOptions): Promise<void> {
    const started = Date.now();
    const heartbeatEveryMs = options.heartbeatEveryMs ?? Math.max(1_000, Math.floor(options.leaseMs / 2));
    const maxLoops = options.maxLoops ?? Number.POSITIVE_INFINITY;
    let loops = 0;
    let processed = 0;
    let idleLoops = 0;
    let reclaimed = 0;
    let renewals = 0;
    let renewFailures = 0;
    let failures = 0;
    let active: { taskId: string; runId: string; leaseExpiresAt: string } | null = null;
    let nextHeartbeatAt = Date.now() + heartbeatEveryMs;

    while (loops < maxLoops) {
      loops += 1;
      const claimed = await this.store.claimNext(options.workerId, options.leaseMs);
      if (!claimed) {
        idleLoops += 1;
        await this.writeHealth({
          options,
          loops,
          processed,
          idleLoops,
          reclaimed,
          renewals,
          renewFailures,
          failures,
          active,
        });
        await sleep(options.pollMs);
        continue;
      }
      const { packet, runId } = claimed;
      if (packet.attempt && packet.attempt > 1) reclaimed += 1;
      active = { taskId: packet.id, runId, leaseExpiresAt: packet.leaseExpiresAt ?? new Date(Date.now() + options.leaseMs).toISOString() };
      const heartbeatTimer = setInterval(async () => {
        try {
          const renewed = await this.store.renewLease(packet.id, options.workerId, options.leaseMs);
          if (renewed?.leaseExpiresAt) {
            renewals += 1;
            active = { taskId: renewed.id, runId: renewed.activeRunId ?? runId, leaseExpiresAt: renewed.leaseExpiresAt };
          } else {
            renewFailures += 1;
          }
        } catch {
          renewFailures += 1;
        }
      }, heartbeatEveryMs);
      try {
        await this.processClaimed(packet, runId);
        processed += 1;
      } catch {
        failures += 1;
      } finally {
        clearInterval(heartbeatTimer);
        active = null;
      }
      if (Date.now() >= nextHeartbeatAt) {
        await this.writeHealth({
          options,
          loops,
          processed,
          idleLoops,
          reclaimed,
          renewals,
          renewFailures,
          failures,
          active,
        });
        nextHeartbeatAt = Date.now() + heartbeatEveryMs;
      }
      await sleep(0);
    }

    await this.writeHealth({
      options,
      loops,
      processed,
      idleLoops,
      reclaimed,
      renewals,
      renewFailures,
      failures,
      active,
    });
    await this.store.appendEvent(`watch-${options.workerId}`, "closed", {
      loops,
      processed,
      idleLoops,
      reclaimed,
      renewals,
      renewFailures,
      failures,
      durationMs: Date.now() - started,
    });
  }

  private async processClaimed(packet: TaskPacket, runId: string): Promise<void> {
    try {
      enforcePolicy(packet, this.options.policy);
      const missingGate = packet.approvalGates.find((gate) => !(packet.approvedGates ?? []).includes(gate));
      if (missingGate) {
        await this.store.transition(packet, "waiting_approval", { gate: missingGate });
        return;
      }
      await this.store.appendEvent(packet.id, "started", { runId, argv0: packet.command.argv[0] });
      const result = await runArgv(packet);
      const stdoutPath = await this.store.writeRunArtifact(packet.id, runId, "stdout.log", result.stdout);
      const stderrPath = await this.store.writeRunArtifact(packet.id, runId, "stderr.log", result.stderr);
      await this.store.appendEvent(packet.id, "stdout_artifact", { path: stdoutPath, bytes: result.stdout.length });
      await this.store.appendEvent(packet.id, "stderr_artifact", { path: stderrPath, bytes: result.stderr.length });
      await this.store.appendEvent(packet.id, "command_exit", { code: result.exitCode });
      const verification = await verify(packet, runId, result.exitCode, stdoutPath, this.store);
      await this.store.writeRunArtifact(packet.id, runId, "verification.json", JSON.stringify(verification, null, 2));
      if (verification.passed) {
        await this.store.appendEvent(packet.id, "verification_passed", { runId, checks: verification.checks.length });
        await this.store.transition(packet, "done", { runId });
      } else {
        await this.store.appendEvent(packet.id, "verification_failed", { runId, summary: verification.summary });
        await this.store.transition(packet, "failed", { runId, reason: "verification_failed" });
      }
    } catch (error) {
      await this.store.appendEvent(packet.id, "failed", { runId, error: error instanceof Error ? error.message : String(error) });
      await this.store.transition(packet, "failed", { runId, reason: "runner_error" });
      throw error;
    }
  }

  private async writeHealth(input: {
    options: WatchOptions;
    loops: number;
    processed: number;
    idleLoops: number;
    reclaimed: number;
    renewals: number;
    renewFailures: number;
    failures: number;
    active: null | { taskId: string; runId: string; leaseExpiresAt: string };
  }): Promise<void> {
    const status: WatchHealthSnapshot["status"] = input.failures === 0 && input.renewFailures === 0 ? "QUEUE_SUPERVISOR_CLEAR" : "QUEUE_SUPERVISOR_ALERT";
    const snapshot: WatchHealthSnapshot = {
      schemaVersion: 1,
      status,
      workerId: input.options.workerId,
      laneId: input.options.policy.laneId,
      at: new Date().toISOString(),
      metrics: {
        loops: input.loops,
        processed: input.processed,
        idleLoops: input.idleLoops,
        reclaimed: input.reclaimed,
        renewals: input.renewals,
        renewFailures: input.renewFailures,
        failures: input.failures,
        queueDiagnosisAlerts: 0,
        quarantinedParseErrors: 0,
        lockContentionSkips: 0,
      },
      execution_plane_truth: {
        queue_liveness: "necessary_but_insufficient",
        lease_heartbeat: "required_for_running_truth",
      },
      activeTask: input.active,
    };
    const path = `${this.options.root}/state/watch-health.json`;
    await mkdir(`${this.options.root}/state`, { recursive: true });
    await writeFile(path, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  }
}

export async function loadPolicy(path: string): Promise<RunnerPolicy> {
  const raw = await readFile(path, "utf8");
  if (path.endsWith(".json")) {
    return parseRunnerPolicy(JSON.parse(raw));
  }
  if (path.endsWith(".yaml") || path.endsWith(".yml")) {
    return parseRunnerPolicy(policyFromLaneManifest(parseYaml(raw)));
  }
  throw new Error(`unsupported policy format: ${path}`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function policyFromLaneManifest(value: unknown): Record<string, unknown> {
  const manifest = value as Record<string, unknown>;
  const liveRun = manifest.live_run as Record<string, unknown>;
  const commands = manifest.commands as Record<string, unknown>;
  const allowedCommands: Record<string, string[]> = {};
  for (const commandBlock of Object.values(commands)) {
    if (typeof commandBlock !== "object" || commandBlock === null) continue;
    const id = (commandBlock as { id?: unknown }).id;
    const argv = (commandBlock as { argv?: unknown }).argv;
    if (typeof id === "string" && Array.isArray(argv) && argv.every((x) => typeof x === "string")) {
      allowedCommands[id] = argv as string[];
    }
  }
  return {
    schemaVersion: 1,
    laneId: manifest.lane_id,
    workspace: manifest.workspace,
    authorityMaxLevel: liveRun.authority_max_level,
    externalCommitAllowed: liveRun.external_commit_allowed,
    allowedCommands,
    forbiddenActions: manifest.forbidden_actions,
    humanGates: manifest.human_gates,
  };
}

async function runArgv(packet: TaskPacket): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  const timeoutMs = 30_000;
  const outputCapBytes = 1024 * 1024;
  return new Promise((resolve, reject) => {
    const [cmd, ...args] = packet.command.argv;
    const child = spawn(cmd, args, {
      cwd: packet.workspace,
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, timeoutMs);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      if (stdout.length > outputCapBytes) stdout = stdout.slice(0, outputCapBytes);
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      if (stderr.length > outputCapBytes) stderr = stderr.slice(0, outputCapBytes);
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ exitCode: timedOut ? 124 : code ?? 1, stdout, stderr });
    });
  });
}

async function verify(
  packet: TaskPacket,
  runId: string,
  exitCode: number,
  stdoutPath: string,
  store: DurableRunnerStore,
): Promise<VerificationResult> {
  const checks = [];
  for (const spec of packet.verificationRequired) {
    checks.push(await verifyOne(spec, exitCode, stdoutPath));
  }
  const passed = checks.every((check) => check.passed);
  return {
    schemaVersion: 1,
    taskId: packet.id,
    runId,
    passed,
    checks,
    summary: passed ? "all verification checks passed" : "one or more verification checks failed",
    at: new Date().toISOString(),
  };
}

async function verifyOne(spec: VerificationSpec, exitCode: number, stdoutPath: string): Promise<{ type: VerificationSpec["type"]; passed: boolean; summary: string }> {
  if (spec.type === "exit_code_zero") {
    return { type: spec.type, passed: exitCode === 0, summary: `exit_code=${exitCode}` };
  }
  if (spec.type === "artifact_exists") {
    try {
      await readFile(spec.path, "utf8");
      return { type: spec.type, passed: true, summary: `artifact exists: ${basename(spec.path)}` };
    } catch {
      return { type: spec.type, passed: false, summary: `artifact missing: ${spec.path}` };
    }
  }
  const stdout = await readFile(stdoutPath, "utf8");
  return { type: spec.type, passed: stdout.includes(spec.value), summary: `stdout_contains=${JSON.stringify(spec.value)}` };
}
