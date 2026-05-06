export const TASK_STATES = [
  "queued",
  "running",
  "waiting_approval",
  "done",
  "failed",
  "canceled",
] as const;

export type TaskState = (typeof TASK_STATES)[number];
export type AuthorityLevel = 1 | 2 | 3 | 4 | 5;

export type VerificationSpec =
  | { type: "exit_code_zero" }
  | { type: "artifact_exists"; path: string }
  | { type: "stdout_contains"; value: string };

export interface TaskCommand {
  id: string;
  argv: string[];
  shell?: false;
}

export interface ExternalEffectPolicy {
  allowed: boolean;
  description: string;
}

export interface TaskPacket {
  schemaVersion: 1;
  id: string;
  idempotencyKey: string;
  title: string;
  laneId: string;
  workspace: string;
  command: TaskCommand;
  state: TaskState;
  authorityLevel: AuthorityLevel;
  externalEffect: ExternalEffectPolicy;
  approvalGates: string[];
  approvedGates?: string[];
  verificationRequired: VerificationSpec[];
  createdAt: string;
  updatedAt: string;
  leaseOwner?: string;
  leaseExpiresAt?: string;
  activeRunId?: string;
  attempt?: number;
}

export type TaskEventType =
  | "queued"
  | "claimed"
  | "started"
  | "approval_required"
  | "stdout_artifact"
  | "stderr_artifact"
  | "command_exit"
  | "verification_passed"
  | "verification_failed"
  | "closed"
  | "failed"
  | "canceled";

export interface TaskEvent {
  schemaVersion: 1;
  id: string;
  taskId: string;
  at: string;
  type: TaskEventType;
  payload: Record<string, unknown>;
}

export interface VerificationCheckResult {
  type: VerificationSpec["type"];
  passed: boolean;
  summary: string;
}

export interface VerificationResult {
  schemaVersion: 1;
  taskId: string;
  runId: string;
  passed: boolean;
  checks: VerificationCheckResult[];
  summary: string;
  at: string;
}

export interface RunnerPolicy {
  schemaVersion: 1;
  laneId: string;
  workspace: string;
  authorityMaxLevel: AuthorityLevel;
  externalCommitAllowed: boolean;
  allowedCommands: Record<string, string[]>;
  forbiddenActions: string[];
  humanGates: string[];
}

export interface ClaimedTask {
  packet: TaskPacket;
  runId: string;
}

export interface WatchHealthSnapshot {
  schemaVersion: 1;
  status: "QUEUE_SUPERVISOR_CLEAR" | "QUEUE_SUPERVISOR_ALERT";
  workerId: string;
  laneId: string;
  at: string;
  metrics: {
    loops: number;
    processed: number;
    idleLoops: number;
    reclaimed: number;
    renewals: number;
    renewFailures: number;
    failures: number;
    queueDiagnosisAlerts: number;
    quarantinedParseErrors: number;
    lockContentionSkips: number;
  };
  execution_plane_truth: {
    queue_liveness: "necessary_but_insufficient";
    lease_heartbeat: "required_for_running_truth";
  };
  activeTask: null | {
    taskId: string;
    runId: string;
    leaseExpiresAt: string;
  };
}

export interface UsageProof {
  status: "ok";
  used: boolean;
  checkedAt: string;
  maxFreshMs: number;
  evidence: {
    events: { fileCount: number; freshestAt: string | null };
    runs: { taskDirCount: number; freshestAt: string | null };
    watchHealth: { exists: boolean; mtime: string | null };
    ledger: { cleanupEntries: number };
  };
}
