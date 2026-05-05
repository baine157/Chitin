// Minimal YAML parser for the lane-manifest subset used by durable-runner.
// Supports nested maps, scalar lists, and inline booleans/integers/strings.
export function parse(input: string): Record<string, unknown> {
  const lines = input.replace(/\r\n/g, "\n").split("\n");
  const root: Record<string, unknown> = {};
  const stack: Array<{ indent: number; kind: "map" | "list"; value: Record<string, unknown> | unknown[] }> = [
    { indent: -1, kind: "map", value: root },
  ];

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const rawLine = lines[lineIndex];
    const line = rawLine.split("#")[0];
    if (line.trim().length === 0) continue;
    const indent = countIndent(line);
    const trimmed = line.trim();

    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    const top = stack[stack.length - 1];

    if (trimmed.startsWith("- ")) {
      if (top.kind !== "list") throw new Error(`invalid YAML list placement: ${trimmed}`);
      (top.value as unknown[]).push(parseScalar(trimmed.slice(2).trim()));
      continue;
    }

    const colon = trimmed.indexOf(":");
    if (colon < 0) throw new Error(`invalid YAML key/value: ${trimmed}`);
    const key = trimmed.slice(0, colon).trim();
    const rest = trimmed.slice(colon + 1).trim();
    if (top.kind !== "map") throw new Error(`invalid YAML map placement: ${trimmed}`);

    if (rest.length > 0) {
      (top.value as Record<string, unknown>)[key] = parseScalar(rest);
      continue;
    }

    const nextLine = peekNextNonEmpty(lines, lineIndex);
    const nextTrimmed = nextLine?.trim() ?? "";
    if (nextTrimmed.startsWith("- ")) {
      const list: unknown[] = [];
      (top.value as Record<string, unknown>)[key] = list;
      stack.push({ indent, kind: "list", value: list });
    } else {
      const obj: Record<string, unknown> = {};
      (top.value as Record<string, unknown>)[key] = obj;
      stack.push({ indent, kind: "map", value: obj });
    }
  }
  return root;
}

function parseScalar(value: string): unknown {
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+$/.test(value)) return Number(value);
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}

function countIndent(line: string): number {
  let i = 0;
  while (i < line.length && line[i] === " ") i += 1;
  return i;
}

function peekNextNonEmpty(lines: string[], start: number): string | null {
  for (let i = start + 1; i < lines.length; i += 1) {
    const candidate = lines[i].split("#")[0];
    if (candidate.trim().length > 0) return candidate;
  }
  return null;
}
