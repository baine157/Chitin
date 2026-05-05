#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { DurableRunnerStore } from "./store.ts";
import { DurableRunner, loadPolicy } from "./runner.ts";
import { parseTaskPacket } from "./validation.ts";

const DEFAULT_ROOT = "state/cos/durable-runner";

async function main(): Promise<number> {
  const [command, ...args] = process.argv.slice(2);
  if (!command || command === "--help" || command === "-h") {
    printHelp();
    return 0;
  }
  const root = option(args, "--root") ?? DEFAULT_ROOT;
  if (command === "init") {
    await new DurableRunnerStore(root).init();
    console.log(JSON.stringify({ status: "ok", root }));
    return 0;
  }
  if (command === "enqueue") {
    const file = positional(args, 0);
    if (!file) throw new Error("enqueue requires a task packet path");
    const packet = parseTaskPacket(JSON.parse(await readFile(file, "utf8")));
    await new DurableRunnerStore(root).enqueue(packet);
    console.log(JSON.stringify({ status: "queued", id: packet.id }));
    return 0;
  }
  if (command === "tick") {
    const policyPath = option(args, "--policy") ?? option(args, "--manifest");
    if (!policyPath) throw new Error("tick requires --policy");
    const runner = new DurableRunner({
      root,
      policy: await loadPolicy(policyPath),
      workerId: option(args, "--worker") ?? `worker-${process.pid}`,
      leaseMs: Number(option(args, "--lease-ms") ?? "120000"),
    });
    const worked = await runner.tick();
    console.log(JSON.stringify({ status: worked ? "processed" : "idle" }));
    return 0;
  }
  if (command === "watch") {
    const policyPath = option(args, "--policy") ?? option(args, "--manifest");
    if (!policyPath) throw new Error("watch requires --policy or --manifest");
    const runner = new DurableRunner({
      root,
      policy: await loadPolicy(policyPath),
      workerId: option(args, "--worker") ?? `worker-${process.pid}`,
      leaseMs: Number(option(args, "--lease-ms") ?? "120000"),
    });
    await runner.watch({
      root,
      policy: await loadPolicy(policyPath),
      workerId: option(args, "--worker") ?? `worker-${process.pid}`,
      leaseMs: Number(option(args, "--lease-ms") ?? "120000"),
      pollMs: Number(option(args, "--poll-ms") ?? "1000"),
      maxLoops: option(args, "--max-loops") ? Number(option(args, "--max-loops")) : undefined,
      heartbeatEveryMs: option(args, "--heartbeat-ms") ? Number(option(args, "--heartbeat-ms")) : undefined,
    });
    console.log(JSON.stringify({ status: "watch_complete" }));
    return 0;
  }
  if (command === "approve") {
    const taskId = positional(args, 0);
    const gateId = positional(args, 1);
    if (!taskId || !gateId) throw new Error("approve requires <task-id> <gate-id>");
    const updated = await new DurableRunnerStore(root).approve(taskId, gateId);
    console.log(JSON.stringify({ status: "approved", id: updated.id, gate: gateId, state: updated.state }));
    return 0;
  }
  if (command === "status") {
    const taskId = positional(args, 0);
    if (!taskId) throw new Error("status requires <task-id>");
    const status = await new DurableRunnerStore(root).readStatus(taskId);
    console.log(JSON.stringify(status, null, 2));
    return 0;
  }
  throw new Error(`unknown command: ${command}`);
}

function option(args: string[], name: string): string | undefined {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}

function positional(args: string[], index: number): string | undefined {
  return args.filter((arg) => !arg.startsWith("--"))[index];
}

function printHelp(): void {
  console.log(`durable-runner

Commands:
  init [--root DIR]
  enqueue <task.json> [--root DIR]
  tick (--policy <policy.json|policy.yaml> | --manifest <lane.yaml>) [--root DIR] [--worker ID] [--lease-ms MS]
  watch (--policy <policy.json|policy.yaml> | --manifest <lane.yaml>) [--root DIR] [--worker ID] [--lease-ms MS] [--poll-ms MS] [--max-loops N] [--heartbeat-ms MS]
  approve <task-id> <gate-id> [--root DIR]
  status <task-id> [--root DIR]
`);
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    console.error(JSON.stringify({ status: "error", error: error instanceof Error ? error.message : String(error) }));
    process.exitCode = 1;
  });
