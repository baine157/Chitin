import { randomUUID } from "node:crypto";
import { mkdir, open, readFile, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { parseTaskPacket } from "./validation.ts";
import type { ClaimedTask, TaskEvent, TaskEventType, TaskPacket, TaskState, UsageProof } from "./types.ts";

const TASK_DIRS: TaskState[] = ["queued", "running", "waiting_approval", "done", "failed", "canceled"];
const QUARANTINE_DIR = "quarantine_parse_error";

export class DurableRunnerStore {
  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  async init(): Promise<void> {
    await mkdir(this.root, { recursive: true });
    await Promise.all([
      ...TASK_DIRS.map((state) => mkdir(this.taskDir(state), { recursive: true })),
      mkdir(join(this.root, "tasks", QUARANTINE_DIR), { recursive: true }),
      mkdir(this.runsDir(), { recursive: true }),
      mkdir(this.locksDir(), { recursive: true }),
      mkdir(join(this.root, "ledger"), { recursive: true }),
    ]);
  }

  taskDir(state: TaskState): string {
    return join(this.root, "tasks", state);
  }

  taskPath(state: TaskState, id: string): string {
    return join(this.taskDir(state), `${id}.json`);
  }

  runDir(taskId: string, runId: string): string {
    return join(this.runsDir(), taskId, runId);
  }

  stdoutPath(taskId: string, runId: string): string {
    return join(this.runDir(taskId, runId), "stdout.log");
  }

  stderrPath(taskId: string, runId: string): string {
    return join(this.runDir(taskId, runId), "stderr.log");
  }

  verificationPath(taskId: string, runId: string): string {
    return join(this.runDir(taskId, runId), "verification.json");
  }

  private runsDir(): string {
    return join(this.root, "runs");
  }

  private locksDir(): string {
    return join(this.root, "locks");
  }

  async enqueue(packet: TaskPacket): Promise<void> {
    const parsed = parseTaskPacket({ ...packet, state: "queued" });
    await this.init();
    const collision = await this.findByIdempotencyKey(parsed.idempotencyKey);
    if (collision) {
      throw new Error(`idempotency collision: key=${parsed.idempotencyKey} existing_task=${collision.id} state=${collision.state}`);
    }
    const target = this.taskPath("queued", parsed.id);
    await atomicWriteJson(target, { ...parsed, state: "queued", updatedAt: nowIso() });
    await this.appendEvent(parsed.id, "queued", { state: "queued" });
  }

  async claimNext(workerId: string, leaseMs: number): Promise<ClaimedTask | null> {
    await this.init();
    await this.quarantineMalformedQueuedPackets();
    const states: TaskState[] = ["running", "queued"];
    for (const state of states) {
      const entries = await listJsonFiles(this.taskDir(state));
      for (const file of entries) {
        const maybe = await this.withLock(idFromFile(file), async () => {
          const packet = await readPacketOrNull(join(this.taskDir(state), file));
          if (!packet) return null;
          if (state === "running" && !leaseExpired(packet)) return null;
          if (state === "queued" && packet.state !== "queued") return null;
          const runId = state === "running" && packet.activeRunId ? packet.activeRunId : randomUUID();
          const claimed: TaskPacket = {
            ...packet,
            state: "running",
            leaseOwner: workerId,
            leaseExpiresAt: new Date(Date.now() + leaseMs).toISOString(),
            activeRunId: runId,
            attempt: (packet.attempt ?? 0) + (state === "queued" ? 1 : 0),
            updatedAt: nowIso(),
          };
          await mkdir(this.runDir(packet.id, runId), { recursive: true });
          if (state === "queued") {
            await atomicWriteJson(this.taskPath("queued", packet.id), claimed);
            await rename(this.taskPath("queued", packet.id), this.taskPath("running", packet.id));
          } else {
            await atomicWriteJson(this.taskPath("running", packet.id), claimed);
          }
          await this.appendEvent(packet.id, "claimed", { workerId, runId, reclaimed: state === "running" });
          return { packet: claimed, runId };
        });
        if (maybe) return maybe;
      }
    }
    return null;
  }

  async transition(packet: TaskPacket, to: TaskState, payload: Record<string, unknown> = {}): Promise<TaskPacket> {
    if (!allowedTransition(packet.state, to)) throw new Error(`invalid task transition ${packet.state} -> ${to}`);
    if (to === "done") {
      const runId = typeof payload.runId === "string" ? payload.runId : packet.activeRunId;
      if (!runId) throw new Error("verification artifact missing: runId unavailable");
      const verification = await this.readVerification(packet.id, runId);
      if (!verification) throw new Error("verification artifact missing");
      if (verification.passed !== true) throw new Error("verification artifact not passed");
    }
    const next: TaskPacket = {
      ...packet,
      state: to,
      leaseOwner: undefined,
      leaseExpiresAt: undefined,
      updatedAt: nowIso(),
    };
    await atomicWriteJson(this.taskPath(packet.state, packet.id), next);
    await rename(this.taskPath(packet.state, packet.id), this.taskPath(to, packet.id));
    await this.appendEvent(packet.id, to === "done" ? "closed" : to === "failed" ? "failed" : to === "canceled" ? "canceled" : "approval_required", { state: to, ...payload });
    return next;
  }

  async approve(taskId: string, gateId: string): Promise<TaskPacket> {
    const packet = await this.getTask(taskId);
    if (!packet) throw new Error(`task not found: ${taskId}`);
    if (packet.state !== "waiting_approval") throw new Error(`task is not waiting approval: state=${packet.state}`);
    if (!packet.approvalGates.includes(gateId)) throw new Error(`gate not declared on task: ${gateId}`);
    const approved = new Set(packet.approvedGates ?? []);
    approved.add(gateId);
    const next: TaskPacket = {
      ...packet,
      approvedGates: Array.from(approved).sort(),
      state: "queued",
      updatedAt: nowIso(),
    };
    await atomicWriteJson(this.taskPath("waiting_approval", taskId), next);
    await rename(this.taskPath("waiting_approval", taskId), this.taskPath("queued", taskId));
    await this.appendEvent(taskId, "queued", { state: "queued", approvedGate: gateId });
    return next;
  }

  async getTask(taskId: string): Promise<TaskPacket | null> {
    for (const state of TASK_DIRS) {
      const packet = await readPacketOrNull(this.taskPath(state, taskId));
      if (packet) return packet;
    }
    return null;
  }

  async findByIdempotencyKey(key: string): Promise<TaskPacket | null> {
    for (const state of TASK_DIRS) {
      const entries = await listJsonFiles(this.taskDir(state));
      for (const file of entries) {
        const packet = await readPacketOrNull(join(this.taskDir(state), file));
        if (packet && packet.idempotencyKey === key) return packet;
      }
    }
    return null;
  }

  async readStatus(taskId: string): Promise<Record<string, unknown>> {
    const packet = await this.getTask(taskId);
    if (!packet) throw new Error(`task not found: ${taskId}`);
    const eventPath = join(this.root, "events", `${taskId}.jsonl`);
    const events = await readJsonLines(eventPath);
    const runId = packet.activeRunId ?? lastRunId(events);
    const artifacts = runId
      ? {
          runId,
          stdout: this.stdoutPath(taskId, runId),
          stderr: this.stderrPath(taskId, runId),
          verification: this.verificationPath(taskId, runId),
          stdoutExists: await exists(this.stdoutPath(taskId, runId)),
          stderrExists: await exists(this.stderrPath(taskId, runId)),
          verificationExists: await exists(this.verificationPath(taskId, runId)),
        }
      : null;
    return {
      task: packet,
      eventCount: events.length,
      lastEvent: events.length > 0 ? events[events.length - 1] : null,
      artifacts,
    };
  }

  async renewLease(taskId: string, workerId: string, leaseMs: number): Promise<TaskPacket | null> {
    const packet = await readPacketOrNull(this.taskPath("running", taskId));
    if (!packet) return null;
    if (packet.state !== "running") return null;
    if (packet.leaseOwner !== workerId) return null;
    const renewed: TaskPacket = {
      ...packet,
      leaseExpiresAt: new Date(Date.now() + leaseMs).toISOString(),
      updatedAt: nowIso(),
    };
    await atomicWriteJson(this.taskPath("running", taskId), renewed);
    await this.appendEvent(taskId, "claimed", {
      workerId,
      runId: renewed.activeRunId ?? null,
      renewal: true,
      leaseExpiresAt: renewed.leaseExpiresAt,
    });
    return renewed;
  }

  async appendEvent(taskId: string, type: TaskEventType, payload: Record<string, unknown>): Promise<void> {
    const event: TaskEvent = {
      schemaVersion: 1,
      id: randomUUID(),
      taskId,
      at: nowIso(),
      type,
      payload,
    };
    await mkdir(join(this.root, "events"), { recursive: true });
    await appendJsonLine(join(this.root, "events", `${taskId}.jsonl`), event);
  }

  async writeRunArtifact(taskId: string, runId: string, name: string, content: string): Promise<string> {
    const path = join(this.runDir(taskId, runId), name);
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, content, "utf8");
    return path;
  }

  async proveUsage(maxFreshMs = 120_000): Promise<UsageProof> {
    const eventFiles = await listMatchingFiles(join(this.root, "events"), [".json", ".jsonl"]);
    const runTaskDirs = await safeReaddir(this.runsDir());
    const watchHealthPath = join(this.root, "state", "watch-health.json");
    const watchHealthExists = await exists(watchHealthPath);
    const watchHealthMtime = watchHealthExists ? (await stat(watchHealthPath)).mtime.toISOString() : null;
    const eventsFreshest = await freshestMtime(join(this.root, "events"), eventFiles);
    const runsFreshest = await freshestRunMtime(this.runsDir(), runTaskDirs);
    const used = isFresh(eventsFreshest, maxFreshMs) || isFresh(runsFreshest, maxFreshMs) || isFresh(watchHealthMtime, maxFreshMs);
    const cleanupEntries = await countJsonlLines(join(this.root, "ledger", "quarantine_cleanup.jsonl"));
    return {
      status: "ok",
      used,
      checkedAt: nowIso(),
      maxFreshMs,
      evidence: {
        events: { fileCount: eventFiles.length, freshestAt: eventsFreshest },
        runs: { taskDirCount: runTaskDirs.length, freshestAt: runsFreshest },
        watchHealth: { exists: watchHealthExists, mtime: watchHealthMtime },
        ledger: { cleanupEntries },
      },
    };
  }

  async cleanupQuarantine(maxAgeHours = 14 * 24, dryRun = false): Promise<{ status: "ok"; prunableCount: number; prunedCount: number }> {
    await this.init();
    const qDir = join(this.root, "tasks", QUARANTINE_DIR);
    const files = await listJsonFiles(qDir);
    const cutoffMs = Date.now() - maxAgeHours * 60 * 60 * 1000;
    const prunable: string[] = [];
    for (const file of files) {
      const full = join(qDir, file);
      const info = await stat(full);
      if (info.mtimeMs < cutoffMs) prunable.push(full);
    }
    let prunedCount = 0;
    if (!dryRun) {
      for (const path of prunable) {
        await rm(path, { force: true });
        prunedCount += 1;
      }
    }
    await appendJsonLine(join(this.root, "ledger", "quarantine_cleanup.jsonl"), {
      kind: "quarantine_cleanup",
      at: nowIso(),
      maxAgeHours,
      dryRun,
      prunableCount: prunable.length,
      prunedCount,
    });
    return { status: "ok", prunableCount: prunable.length, prunedCount };
  }

  private async withLock<T>(id: string, fn: () => Promise<T>): Promise<T | null> {
    const lockPath = join(this.locksDir(), `${id}.lock`);
    let handle;
    try {
      handle = await open(lockPath, "wx");
    } catch {
      return null;
    }
    try {
      return await fn();
    } finally {
      await handle.close();
      await rm(lockPath, { force: true });
    }
  }

  private async quarantineMalformedQueuedPackets(): Promise<void> {
    const queuedDir = this.taskDir("queued");
    const qDir = join(this.root, "tasks", QUARANTINE_DIR);
    const entries = await listJsonFiles(queuedDir);
    for (const file of entries) {
      const full = join(queuedDir, file);
      try {
        parseTaskPacket(JSON.parse(await readFile(full, "utf8")));
      } catch (error) {
        const target = join(qDir, file);
        await mkdir(qDir, { recursive: true });
        await rename(full, target);
        await appendJsonLine(join(this.root, "ledger", "quarantine_parse_error.jsonl"), {
          kind: "quarantine_parse_error",
          at: nowIso(),
          file,
          source: full,
          target,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  private async readVerification(taskId: string, runId: string): Promise<{ passed?: boolean } | null> {
    try {
      return JSON.parse(await readFile(this.verificationPath(taskId, runId), "utf8")) as { passed?: boolean };
    } catch {
      return null;
    }
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

function leaseExpired(packet: TaskPacket): boolean {
  return !packet.leaseExpiresAt || Date.parse(packet.leaseExpiresAt) <= Date.now();
}

function allowedTransition(from: TaskState, to: TaskState): boolean {
  return (
    (from === "running" && ["waiting_approval", "done", "failed", "canceled"].includes(to)) ||
    (from === "waiting_approval" && ["queued", "canceled"].includes(to)) ||
    (from === "queued" && to === "canceled")
  );
}

async function readPacketOrNull(path: string): Promise<TaskPacket | null> {
  try {
    return parseTaskPacket(JSON.parse(await readFile(path, "utf8")));
  } catch {
    return null;
  }
}

async function listJsonFiles(dir: string): Promise<string[]> {
  try {
    return (await readdir(dir)).filter((name) => name.endsWith(".json")).sort();
  } catch {
    return [];
  }
}

async function listMatchingFiles(dir: string, extensions: string[]): Promise<string[]> {
  try {
    const files = await readdir(dir);
    return files.filter((file) => extensions.some((ext) => file.endsWith(ext))).sort();
  } catch {
    return [];
  }
}

async function safeReaddir(dir: string): Promise<string[]> {
  try {
    return await readdir(dir);
  } catch {
    return [];
  }
}

async function freshestMtime(dir: string, files: string[]): Promise<string | null> {
  let maxMs = 0;
  for (const file of files) {
    const info = await stat(join(dir, file));
    if (info.mtimeMs > maxMs) maxMs = info.mtimeMs;
  }
  return maxMs ? new Date(maxMs).toISOString() : null;
}

async function freshestRunMtime(runsDir: string, taskDirs: string[]): Promise<string | null> {
  let maxMs = 0;
  for (const taskId of taskDirs) {
    const runIds = await safeReaddir(join(runsDir, taskId));
    for (const runId of runIds) {
      const info = await stat(join(runsDir, taskId, runId));
      if (info.mtimeMs > maxMs) maxMs = info.mtimeMs;
    }
  }
  return maxMs ? new Date(maxMs).toISOString() : null;
}

function isFresh(at: string | null, maxFreshMs: number): boolean {
  if (!at) return false;
  return Date.now() - Date.parse(at) <= maxFreshMs;
}

async function countJsonlLines(path: string): Promise<number> {
  try {
    const raw = await readFile(path, "utf8");
    return raw
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0).length;
  } catch {
    return 0;
  }
}

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

function idFromFile(file: string): string {
  return file.replace(/\.json$/, "");
}

async function atomicWriteJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const tmp = `${path}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(tmp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(tmp, path);
}

async function appendJsonLine(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const { appendFile } = await import("node:fs/promises");
  await appendFile(path, `${JSON.stringify(value)}\n`, "utf8");
}

async function readJsonLines(path: string): Promise<Record<string, unknown>[]> {
  try {
    const raw = await readFile(path, "utf8");
    return raw
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
  } catch {
    return [];
  }
}

function lastRunId(events: Record<string, unknown>[]): string | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const payload = events[i].payload;
    if (typeof payload === "object" && payload !== null && typeof (payload as { runId?: unknown }).runId === "string") {
      return (payload as { runId: string }).runId;
    }
  }
  return null;
}
