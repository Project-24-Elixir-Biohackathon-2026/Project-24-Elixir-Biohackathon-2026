// What a tool-call card shows, worked out from the call's arguments and its result text. The page renders
// all of it as React text, never HTML: arguments are model output, results are tool output.

export type CallStatus = "inProgress" | "executing" | "complete";
export type CardState = "running" | "done" | "failed";

const MAX_RESULT_LINES = 40;
const MAX_RESULT_CHARS = 4000;

function text(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value) ?? String(value);
}

// One [key, value] row per argument. Arguments that are not an object (rare) are one row without a key.
export function argumentRows(parameters: unknown): [string, string][] {
  if (parameters === undefined || parameters === null) return [];
  if (typeof parameters !== "object" || Array.isArray(parameters)) return [["", text(parameters)]];
  return Object.entries(parameters as Record<string, unknown>).map(([key, value]) => [key, text(value)]);
}

// run_command's command, shown as a `$ <command>` line; "" while it is still streaming in. null for any
// other tool.
export function commandOf(name: string, parameters: unknown): string | null {
  if (name !== "run_command") return null;
  const command = (parameters as Record<string, unknown> | undefined)?.command;
  return typeof command === "string" ? command : "";
}

function cut(body: string): string {
  let shown = body.split("\n").slice(0, MAX_RESULT_LINES).join("\n");
  if (shown.length > MAX_RESULT_CHARS) shown = shown.slice(0, MAX_RESULT_CHARS);
  return shown.length < body.length ? `${shown}\n… (${body.length - shown.length} more characters)` : shown;
}

// run_command's output: the sandbox returns a list of {type, data} parts, a plain string in older builds.
function outputOf(output: unknown): string | null {
  if (typeof output === "string") return output;
  if (!Array.isArray(output)) return null;
  return output.map((part) => (typeof part?.data === "string" ? part.data : "")).join("").replace(/\r\n/g, "\n");
}

// A call failed when its result is a JSON object with a string `error` (the agent's own failures and the
// sandbox's HTTP errors) or a nonzero `exit_code` (a command that ran and failed). A result the agent cut to
// its output cap is not JSON: it is shown as is, and its leading `{"error":` or its `"exit_code"` still tell.
// A command still running when the call returned (`status: "running"`) is not a failure; its body says so.
export function readResult(name: string, result: string): { failed: boolean; body: string } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(result);
  } catch {
    const exit = /"exit_code"\s*:\s*(-?\d+)/.exec(result);
    return { failed: /^\s*\{\s*"error"\s*:/.test(result) || (exit !== null && Number(exit[1]) !== 0), body: cut(result) };
  }
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const r = parsed as Record<string, unknown>;
    if (typeof r.error === "string") return { failed: true, body: cut(r.error) };
    const exit = typeof r.exit_code === "number" ? r.exit_code : 0;
    const output = name === "run_command" ? outputOf(r.output) : null;
    if (output !== null) {
      const note = exit !== 0 ? `\n[exit code ${exit}]`
        : r.status === "running" ? `\n[still running: process ${text(r.id)}]` : "";
      return { failed: exit !== 0, body: cut(output) + note };
    }
    if (exit !== 0) return { failed: true, body: cut(JSON.stringify(parsed, null, 2)) };
  }
  return { failed: false, body: cut(JSON.stringify(parsed, null, 2)) };
}

export function cardState(status: CallStatus, result: string | undefined, name = ""): CardState {
  if (status !== "complete" || result === undefined) return "running";
  return readResult(name, result).failed ? "failed" : "done";
}

// A group of consecutive calls: running while any runs, then failed if any failed.
export function groupState(states: CardState[]): CardState {
  if (states.includes("running")) return "running";
  return states.includes("failed") ? "failed" : "done";
}

// A group header's list of tools, as Open WebUI's ConsecutiveDetailsGroup writes it: each name once, in
// the order first called, with its count when called more than once ("list_files, 2 run_command").
export function toolSummary(names: string[]): string {
  const counts = new Map<string, number>();
  for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);
  return [...counts].map(([name, n]) => (n > 1 ? `${n} ${name}` : name)).join(", ");
}
