// A journal's lines → the conversation (spec §13, *Rebuilding the conversation*, decision 11). For each run in
// journal order: the path to its anchor, then its new messages, then its events applied with @ag-ui/client's
// defaultApplyEvents, the code the browser runs. The messages a run added are chained by parentId: the first
// under the anchor, each later one under the one before. One module for the run route, the session API and
// the exporter, so the chat and the archive cannot disagree.
import { defaultApplyEvents } from "@ag-ui/client";
import type { AbstractAgent, BaseEvent, Message, RunAgentInput } from "@ag-ui/client";
import { from } from "rxjs";
import { parseJournal } from "./journal.ts";
import type { Ignored, Line, MetaFields, RequestFields, RunStartLine, RunStatus } from "./journal.ts";

export type Node = { message: Message; parentId: string | null; runId: string };
export type RunView = {
  run_id: string; anchor: string | null; new_messages: Message[]; ignored: Ignored[]; request: RequestFields;
  status: RunStatus | "incomplete"; error: string | null;
  started_at: string; ended_at: string | null; last_at: string; // last_at: run_end's, else its last event's
  added: string[]; // ids this run added, in order of first appearance (new messages first)
  events: number;
};
export type Conversation = {
  id: string; created_at: string | null;
  meta: Required<Pick<MetaFields, "tags" | "pinned" | "hidden">> & { title: string | null; deleted_at: string | null };
  first_user_text: string | null;
  nodes: Map<string, Node>;
  children: Map<string | null, string[]>; // null: the root's children
  runs: RunView[]; // journal order of run_start
  tip: string | null; // decision 9
  tip_run: string | null;
  last_line_at: string | null;
  skipped: number; // torn or unparsable lines: rebuildText sets it, rebuild leaves it 0
};

type Pending = { start: RunStartLine; events: BaseEvent[]; end: { at: string; status: RunStatus; error: string | null } | null;
  last_at: string; last_index: number };

// The run's messages after its events, as the browser would hold them; an event that throws ends the
// application there (the messages up to it are kept).
async function applyEvents(id: string, run: Pending, start: Message[]): Promise<Message[]> {
  const input: RunAgentInput = {
    threadId: id, runId: run.start.run_id, messages: start, tools: run.start.request.tools as RunAgentInput["tools"],
    context: run.start.request.context as RunAgentInput["context"], state: run.start.request.state,
    forwardedProps: run.start.request.forwardedProps,
  };
  // defaultApplyEvents reads the starting messages from the agent and sets pendingInterrupts on it.
  const agent = { messages: structuredClone(start), pendingInterrupts: [] } as unknown as AbstractAgent;
  let messages = start;
  await new Promise<void>((resolve) => {
    defaultApplyEvents(input, from(run.events), agent, []).subscribe({
      next: (mutation) => {
        if (mutation.messages !== undefined) messages = mutation.messages;
      },
      error: (error: unknown) => {
        console.warn(`journal ${id}: run ${run.start.run_id}: event application stopped: ${error instanceof Error ? error.name : "error"}`);
        resolve();
      },
      complete: () => resolve(),
    });
  });
  return messages;
}

export function pathTo(conv: Conversation, id: string | null): Message[] {
  const path: Message[] = [];
  for (let at = id; at !== null; ) {
    const node = conv.nodes.get(at);
    if (!node) break;
    path.push(node.message);
    at = node.parentId;
  }
  return path.reverse();
}

// A point the agent may continue from: a user message, or the last message an ended run (one with a run_end)
// added, but only if every tool call any message that run added holds is answered by a `tool` message the
// same run added (a call the last message itself holds, with nothing later in the run to answer it, is the
// special case this excludes: a run cancelled or failed mid tool call), so the agent is never sent a dangling
// tool call (§13). A run without a run_end may still be writing: a call it adds later to its last message
// would be answered only on its own branch, so its last message is no boundary until it ends.
export function isBoundary(conv: Conversation, id: string): boolean {
  const node = conv.nodes.get(id);
  if (!node) return false;
  if (node.message.role === "user") return true;
  const run = conv.runs.find((r) => r.added.at(-1) === id);
  if (!run || run.status === "incomplete") return false;
  const calls = new Set<string>();
  const answered = new Set<string>();
  for (const addedId of run.added) {
    const message = conv.nodes.get(addedId)!.message;
    for (const call of (message as { toolCalls?: { id: string }[] }).toolCalls ?? []) calls.add(call.id);
    const toolCallId = (message as { toolCallId?: string }).toolCallId;
    if (message.role === "tool" && toolCallId !== undefined) answered.add(toolCallId);
  }
  return [...calls].every((callId) => answered.has(callId));
}

export function branchOfTip(conv: Conversation): Message[] {
  return pathTo(conv, conv.tip);
}

export async function rebuild(id: string, lines: Line[]): Promise<Conversation> {
  const conv: Conversation = {
    id, created_at: null,
    meta: { title: null, tags: [], pinned: false, hidden: false, deleted_at: null },
    first_user_text: null, nodes: new Map(), children: new Map(), runs: [], tip: null, tip_run: null,
    last_line_at: null, skipped: 0,
  };
  const pending = new Map<string, Pending>();
  const order: Pending[] = [];
  lines.forEach((line, index) => {
    conv.last_line_at = line.at;
    switch (line.type) {
      case "created":
        conv.created_at ??= line.at;
        break;
      case "meta":
        if ("title" in line) conv.meta.title = line.title ?? null;
        if ("tags" in line) conv.meta.tags = line.tags ?? [];
        if ("pinned" in line) conv.meta.pinned = line.pinned === true;
        if ("hidden" in line) conv.meta.hidden = line.hidden === true;
        if ("deleted_at" in line) conv.meta.deleted_at = line.deleted_at ?? null;
        break;
      case "run_start": {
        if (pending.has(line.run_id)) {
          console.warn(`journal ${id}: second run_start for run ${line.run_id} skipped`);
          break;
        }
        const run: Pending = { start: line, events: [], end: null, last_at: line.at, last_index: index };
        pending.set(line.run_id, run);
        order.push(run);
        break;
      }
      case "event": {
        const run = pending.get(line.run_id);
        if (!run) {
          console.warn(`journal ${id}: event for run ${line.run_id} skipped (no run_start)`);
          break;
        }
        if (run.end) {
          // An ended run may be another run's anchor: nothing after its run_end may change it.
          console.warn(`journal ${id}: event for run ${line.run_id} skipped (after its run_end)`);
          break;
        }
        run.events.push(line.event);
        [run.last_at, run.last_index] = [line.at, index];
        break;
      }
      case "run_end": {
        const run = pending.get(line.run_id);
        if (!run) {
          console.warn(`journal ${id}: run_end for run ${line.run_id} skipped (no run_start)`);
          break;
        }
        if (run.end) break; // the first run_end counts
        run.end = { at: line.at, status: line.status, error: line.error ?? null };
        [run.last_at, run.last_index] = [line.at, index];
        break;
      }
    }
  });
  // Review Focus 3: without a created line, the first parsed line's time.
  conv.created_at ??= lines[0]?.at ?? null;

  let tipIndex = -1;
  for (const run of order) {
    const anchor = run.start.anchor;
    if (anchor !== null && !conv.nodes.has(anchor)) {
      console.warn(`journal ${id}: run ${run.start.run_id}: anchor ${anchor} not found, rebuilt from the root`);
    }
    const parentOfFirst = anchor !== null && conv.nodes.has(anchor) ? anchor : null;
    const path = pathTo(conv, parentOfFirst);
    const pathIds = new Set(path.map((m) => m.id));
    const after = await applyEvents(id, run, [...path, ...run.start.messages]);
    // The run's messages: its new messages first (as sent, unless an event changed them), then every other
    // message its events added, in order of first appearance.
    const latest = new Map(after.map((m) => [m.id, m]));
    const candidates = [...run.start.messages, ...after];
    const added: string[] = [];
    let parent = parentOfFirst;
    for (const candidate of candidates) {
      const mid = candidate.id;
      if (pathIds.has(mid) || added.includes(mid)) continue;
      if (conv.nodes.has(mid)) {
        console.warn(`journal ${id}: run ${run.start.run_id}: message ${mid} already held, skipped`);
        continue;
      }
      const message = latest.get(mid) ?? candidate;
      conv.nodes.set(mid, { message, parentId: parent, runId: run.start.run_id });
      const siblings = conv.children.get(parent) ?? [];
      siblings.push(mid);
      conv.children.set(parent, siblings);
      if (conv.first_user_text === null && message.role === "user" && typeof message.content === "string") {
        conv.first_user_text = message.content;
      }
      added.push(mid);
      parent = mid;
    }
    conv.runs.push({
      run_id: run.start.run_id, anchor: run.start.anchor, new_messages: run.start.messages,
      ignored: run.start.ignored, request: run.start.request,
      status: run.end?.status ?? "incomplete", error: run.end?.error ?? null,
      started_at: run.start.at, ended_at: run.end?.at ?? null, last_at: run.last_at,
      added, events: run.events.length,
    });
    // Decision 9: the tip is the last message of the run that ended (or last wrote) last, among the runs
    // that added a message; the journal's line order decides, not the clock.
    if (added.length > 0 && run.last_index > tipIndex) {
      tipIndex = run.last_index;
      conv.tip = added.at(-1)!;
      conv.tip_run = run.start.run_id;
    }
  }
  return conv;
}

// A journal file's text → its conversation, with the lines parseJournal skipped counted.
export async function rebuildText(id: string, text: string): Promise<Conversation> {
  const { lines, skipped } = parseJournal(text);
  const conv = await rebuild(id, lines);
  conv.skipped = skipped;
  return conv;
}
