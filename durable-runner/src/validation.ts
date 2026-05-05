import { TASK_STATES, type RunnerPolicy, type TaskPacket, type VerificationSpec } from "./types.ts";

const ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$/;
const ABS_PATH_RE = /^\//;
const FORBIDDEN_ARG_RE = /\b(password|passwd|token|cookie|session|mfa|captcha|bitwarden|submit|upload|send|attest|sign|certify|finalize)\b/i;

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ValidationError(`${field} must be a non-empty string`);
  }
  return value;
}

function requireStringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new ValidationError(`${field} must be a non-empty string array`);
  }
  return value.map((item, index) => requireString(item, `${field}[${index}]`));
}

function requireAuthority(value: unknown): 1 | 2 | 3 | 4 | 5 {
  if (![1, 2, 3, 4, 5].includes(value as number)) {
    throw new ValidationError("authorityLevel must be an integer between 1 and 5");
  }
  return value as 1 | 2 | 3 | 4 | 5;
}

function validateVerificationSpec(value: unknown, field: string): VerificationSpec {
  if (!isRecord(value)) throw new ValidationError(`${field} must be an object`);
  if (value.type === "exit_code_zero") return { type: "exit_code_zero" };
  if (value.type === "artifact_exists") return { type: "artifact_exists", path: requireString(value.path, `${field}.path`) };
  if (value.type === "stdout_contains") return { type: "stdout_contains", value: requireString(value.value, `${field}.value`) };
  throw new ValidationError(`${field}.type is unsupported`);
}

export function parseTaskPacket(value: unknown): TaskPacket {
  if (!isRecord(value)) throw new ValidationError("task packet must be an object");
  if (value.schemaVersion !== 1) throw new ValidationError("schemaVersion must be 1");

  const id = requireString(value.id, "id");
  if (!ID_RE.test(id)) throw new ValidationError("id contains unsupported characters");
  const idempotencyKey = requireString(value.idempotencyKey, "idempotencyKey");
  if (!ID_RE.test(idempotencyKey)) throw new ValidationError("idempotencyKey contains unsupported characters");

  const laneId = requireString(value.laneId, "laneId");
  const workspace = requireString(value.workspace, "workspace");
  if (!ABS_PATH_RE.test(workspace)) throw new ValidationError("workspace must be absolute");

  if (!isRecord(value.command)) throw new ValidationError("command must be an object");
  const commandId = requireString(value.command.id, "command.id");
  const argv = requireStringArray(value.command.argv, "command.argv");
  if (value.command.shell !== undefined && value.command.shell !== false) {
    throw new ValidationError("command.shell is not supported in durable runner v0");
  }
  if (argv.some((arg) => FORBIDDEN_ARG_RE.test(arg))) {
    throw new ValidationError("command.argv contains a forbidden action or credential term");
  }

  const state = requireString(value.state, "state");
  if (!TASK_STATES.includes(state as TaskPacket["state"])) throw new ValidationError("state is unsupported");

  if (!isRecord(value.externalEffect)) throw new ValidationError("externalEffect must be an object");
  if (typeof value.externalEffect.allowed !== "boolean") throw new ValidationError("externalEffect.allowed must be boolean");
  const verificationRequired = Array.isArray(value.verificationRequired)
    ? value.verificationRequired.map((item, index) => validateVerificationSpec(item, `verificationRequired[${index}]`))
    : (() => {
        throw new ValidationError("verificationRequired must be an array");
      })();
  if (verificationRequired.length === 0) throw new ValidationError("verificationRequired must not be empty");

  return {
    schemaVersion: 1,
    id,
    idempotencyKey,
    title: requireString(value.title, "title"),
    laneId,
    workspace,
    command: { id: commandId, argv, shell: false },
    state: state as TaskPacket["state"],
    authorityLevel: requireAuthority(value.authorityLevel),
    externalEffect: {
      allowed: value.externalEffect.allowed,
      description: requireString(value.externalEffect.description, "externalEffect.description"),
    },
    approvalGates: Array.isArray(value.approvalGates) ? value.approvalGates.map((item, index) => requireString(item, `approvalGates[${index}]`)) : [],
    approvedGates: Array.isArray(value.approvedGates) ? value.approvedGates.map((item, index) => requireString(item, `approvedGates[${index}]`)) : [],
    verificationRequired,
    createdAt: requireString(value.createdAt, "createdAt"),
    updatedAt: requireString(value.updatedAt, "updatedAt"),
    leaseOwner: typeof value.leaseOwner === "string" ? value.leaseOwner : undefined,
    leaseExpiresAt: typeof value.leaseExpiresAt === "string" ? value.leaseExpiresAt : undefined,
    activeRunId: typeof value.activeRunId === "string" ? value.activeRunId : undefined,
    attempt: typeof value.attempt === "number" ? value.attempt : 0,
  };
}

export function parseRunnerPolicy(value: unknown): RunnerPolicy {
  if (!isRecord(value)) throw new ValidationError("runner policy must be an object");
  if (value.schemaVersion !== 1) throw new ValidationError("policy schemaVersion must be 1");
  const allowedCommands = value.allowedCommands;
  if (!isRecord(allowedCommands)) throw new ValidationError("allowedCommands must be an object");
  const parsedCommands: Record<string, string[]> = {};
  for (const [id, argv] of Object.entries(allowedCommands)) {
    parsedCommands[id] = requireStringArray(argv, `allowedCommands.${id}`);
  }
  return {
    schemaVersion: 1,
    laneId: requireString(value.laneId, "laneId"),
    workspace: requireString(value.workspace, "workspace"),
    authorityMaxLevel: requireAuthority(value.authorityMaxLevel),
    externalCommitAllowed: value.externalCommitAllowed === true,
    allowedCommands: parsedCommands,
    forbiddenActions: Array.isArray(value.forbiddenActions) ? value.forbiddenActions.map((item, index) => requireString(item, `forbiddenActions[${index}]`)) : [],
    humanGates: Array.isArray(value.humanGates) ? value.humanGates.map((item, index) => requireString(item, `humanGates[${index}]`)) : [],
  };
}

export function enforcePolicy(packet: TaskPacket, policy: RunnerPolicy): void {
  if (packet.laneId !== policy.laneId) throw new ValidationError(`task laneId ${packet.laneId} does not match policy ${policy.laneId}`);
  if (packet.workspace !== policy.workspace) throw new ValidationError("task workspace does not match lane policy");
  if (packet.authorityLevel > policy.authorityMaxLevel) throw new ValidationError("task authorityLevel exceeds lane policy");
  if (packet.externalEffect.allowed && !policy.externalCommitAllowed) throw new ValidationError("external effects are not allowed by lane policy");
  const allowedArgv = policy.allowedCommands[packet.command.id];
  if (!allowedArgv) throw new ValidationError(`command ${packet.command.id} is not allowed by lane policy`);
  if (JSON.stringify(packet.command.argv) !== JSON.stringify(allowedArgv)) {
    throw new ValidationError(`command ${packet.command.id} argv does not match lane policy`);
  }
}
