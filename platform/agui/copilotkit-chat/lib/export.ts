// A rebuilt session → an Open WebUI chat (spec §14, *The Open WebUI chat*); a directory of journals → the bundle
// write_run.py renders. Each run becomes one assistant message whose `output` items are the run's AG-UI messages
// in the order they first appeared, in Open WebUI v0.11.3's shapes; user messages stay messages. Besides
// `output`, a run's message may carry `spe_run` (its status), `spe_ignored` (what was sent but unused) and,
// for a command run (spec §15), `spe_command` (its name and focus, refused and failed runs included); a
// remapped message carries `spe_original_id` (the id it forged). The journals are only read.
import fs from "node:fs/promises";
import path from "node:path";
import type { Command } from "./command.ts";
import { MARKER_PREFIX } from "./compaction.ts";
import type { Ignored } from "./journal.ts";
import { idOfJournal } from "./journal.ts";
import { rebuildText } from "./rebuild.ts";
import type { Conversation, RunView } from "./rebuild.ts";
import { autoTitle } from "./sessions.ts";

export type ArchiveMode = "live" | "final";
export type OutputItem = Record<string, unknown> & { type: string; id: string };
export type SpeRun = { run_id: string; status: RunView["status"]; started_at: string; ended_at: string | null; error: string | null };
export type ExportedMessage = {
  id: string; parentId: string | null; childrenIds: string[]; role: string; content: string; timestamp: number;
  output?: OutputItem[]; spe_run?: SpeRun; spe_ignored?: Ignored[]; spe_original_id?: string; spe_command?: Command;
};
export type OpenWebUIChat = {
  id: string; title: string; created_at: number; updated_at: number; archived: boolean;
  meta: { tags: string[]; spe_deleted_at?: string };
  chat: {
    title: string;
    history: { messages: Record<string, ExportedMessage>; currentId: string | null };
    messages: ExportedMessage[];
  };
};
export type Bundle = {
  exported_at: number; spe_archive_mode: ArchiveMode; chats: OpenWebUIChat[];
  tags: { id: string; name: string }[]; notes: [];
};

// The exported assistant message of a run. Open WebUI never writes this prefix.
const RUN_MESSAGE_PREFIX = "spe-run-";
// A remapped id (see toOpenWebUIChat's freshIdFor): also forged, so two remaps can never collide either.
const FRESH_ID_PREFIX = "spe-msg-";

export function runMessageId(runId: string): string {
  return RUN_MESSAGE_PREFIX + runId;
}

// The fields of an AG-UI message the export reads; Message is a union, and every member is read the same way.
export type Loose = {
  id: string; role: string; content?: unknown; toolCallId?: string; error?: string;
  toolCalls?: { id: string; function: { name: string; arguments: string } }[];
};

function seconds(iso: string | null): number {
  const t = iso === null ? NaN : Date.parse(iso);
  return Number.isFinite(t) ? Math.floor(t / 1000) : 0;
}

function textOf(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((p) => (p !== null && typeof p === "object" && (p as { type?: unknown }).type === "text"
      ? String((p as { text?: unknown }).text ?? "") : "")).join("");
  }
  return content === undefined || content === null ? "" : JSON.stringify(content);
}

const parts = (text: string) => [{ type: "output_text", text }];

// One AG-UI message → its Open WebUI output items. An assistant message's text comes before its tool calls.
export function outputItems(message: Loose): OutputItem[] {
  const status = "completed";
  switch (message.role) {
    case "assistant": {
      const items: OutputItem[] = [];
      const text = textOf(message.content);
      if (text !== "" || !message.toolCalls?.length) {
        items.push({ type: "message", id: message.id, role: "assistant", content: parts(text), status });
      }
      for (const call of message.toolCalls ?? []) {
        items.push({ type: "function_call", id: call.id, call_id: call.id, name: call.function.name,
          arguments: call.function.arguments, status });
      }
      return items;
    }
    case "tool": {
      const text = textOf(message.content);
      const output = message.error ? (text ? `${text}\n` : "") + message.error : text;
      return [{ type: "function_call_output", id: message.id, call_id: message.toolCallId ?? null,
        output: [{ type: "input_text", text: output }], status }];
    }
    case "reasoning":
      return [{ type: "reasoning", id: message.id, content: parts(textOf(message.content)), status }];
    default: // a message of another role from the agent's own MESSAGES_SNAPSHOT: kept, with its role
      return [{ type: "message", id: message.id, role: message.role, content: parts(textOf(message.content)), status }];
  }
}

// The run's reply as Open WebUI shows it: its assistant text, without a compaction marker's summary.
function replyText(items: OutputItem[]): string {
  return items
    .filter((i) => i.type === "message" && i.role === "assistant" && !(i.id as string).startsWith(MARKER_PREFIX))
    .map((i) => (i.content as { text: string }[]).map((p) => p.text).join(""))
    .filter((t) => t !== "")
    .join("\n\n");
}

export function toOpenWebUIChat(conv: Conversation): OpenWebUIChat {
  // Null-prototype: a journal/client message id of "__proto__" (or another `Object.prototype` key) must still
  // land as an own key, not reach the prototype's own setter and silently vanish from history.messages (spec
  // §14, *The Open WebUI chat*).
  const messages: Record<string, ExportedMessage> = Object.create(null) as Record<string, ExportedMessage>;
  const order: string[] = [];
  const owner = new Map<string, string>(); // AG-UI message id → the exported message that holds it
  let remapped = 0;
  const put = (m: ExportedMessage) => {
    messages[m.id] = m;
    order.push(m.id);
  };
  // A journal/client message id that already lives in `messages`, or that forges the run-message prefix or
  // this remap's own prefix, is exported under a fresh id instead, carrying the original (never the run's own
  // synthetic id, which is always exactly runMessageId(run_id) and never remapped). Without this, a
  // participant could craft a user message id equal to its own run's exported id and make that run message
  // its own parent, hanging the currentId → parentId walk below (spec §14, *The Open WebUI chat*). The
  // candidate is tried until it is free of every id exported so far, not just the forged id's own slot, so two
  // forged ids in the same chat can never collide with each other either.
  const freshIdFor = (id: string): { id: string; original?: string } => {
    if (!Object.hasOwn(messages, id) && !id.startsWith(RUN_MESSAGE_PREFIX) && !id.startsWith(FRESH_ID_PREFIX)) {
      return { id };
    }
    let candidate: string;
    do {
      candidate = `${FRESH_ID_PREFIX}${remapped++}`;
    } while (Object.hasOwn(messages, candidate));
    return { id: candidate, original: id };
  };
  for (const run of conv.runs) {
    const fresh = new Set(run.new_messages.map((m) => m.id));
    let parent = run.anchor === null ? null : owner.get(run.anchor) ?? null;
    for (const m of run.new_messages) {
      const message = (conv.nodes.get(m.id)?.message ?? m) as unknown as Loose;
      const { id: exportedId, original } = freshIdFor(m.id);
      put({
        id: exportedId, parentId: parent, childrenIds: [], role: message.role, content: textOf(message.content),
        timestamp: seconds(run.started_at), ...(original !== undefined ? { spe_original_id: original } : {}),
      });
      owner.set(m.id, exportedId);
      parent = exportedId;
    }
    const id = runMessageId(run.run_id);
    const output: OutputItem[] = [];
    for (const added of run.added) {
      const node = fresh.has(added) ? undefined : conv.nodes.get(added);
      if (!node) continue;
      output.push(...outputItems(node.message as unknown as Loose));
      owner.set(added, id);
    }
    put({
      id, parentId: parent, childrenIds: [], role: "assistant", content: replyText(output),
      timestamp: seconds(run.ended_at ?? run.last_at), output,
      spe_run: { run_id: run.run_id, status: run.status, started_at: run.started_at, ended_at: run.ended_at, error: run.error },
      spe_ignored: run.ignored,
      ...(run.command ? { spe_command: { name: run.command.name, focus: run.command.focus } } : {}),
    });
  }
  for (const id of order) {
    const parentId = messages[id].parentId;
    if (parentId !== null) messages[parentId]?.childrenIds.push(id);
  }
  const currentId = conv.tip_run === null ? null : runMessageId(conv.tip_run);
  const branch: ExportedMessage[] = [];
  for (let id = currentId; id !== null && messages[id]; id = messages[id].parentId) branch.unshift(messages[id]);
  const title = conv.meta.title
    ?? autoTitle(conv.first_user_text === null ? [] : [{ id: "first", role: "user", content: conv.first_user_text }]);
  return {
    id: conv.id,
    title,
    created_at: seconds(conv.created_at),
    updated_at: seconds(conv.last_line_at ?? conv.created_at),
    archived: conv.meta.hidden,
    meta: { tags: [...conv.meta.tags], ...(conv.meta.deleted_at ? { spe_deleted_at: conv.meta.deleted_at } : {}) },
    chat: { title, history: { messages, currentId }, messages: branch },
  };
}

// Every <uuid>.jsonl in `dir`, hidden and deleted sessions included; any other file is not a journal.
export async function exportJournals(dir: string, mode: ArchiveMode,
  opts: { now?: () => Date } = {}): Promise<Bundle> {
  const names = (await fs.readdir(dir)).filter((name) => idOfJournal(name) !== null).sort();
  const chats: OpenWebUIChat[] = [];
  for (const name of names) {
    // rebuildText: the torn or unparsable lines are counted in the conversation's `skipped`.
    const text = await fs.readFile(path.join(dir, name), "utf8");
    chats.push(toOpenWebUIChat(await rebuildText(idOfJournal(name) as string, text)));
  }
  const tags = [...new Set(chats.flatMap((c) => c.meta.tags))].sort().map((t) => ({ id: t, name: t }));
  return { exported_at: seconds((opts.now ?? (() => new Date()))().toISOString()), spe_archive_mode: mode, chats,
    tags, notes: [] };
}

// The bundle file as the exporter writes it, and as the committed fixtures hold it.
export function bundleJson(bundle: Bundle): string {
  return JSON.stringify(bundle, null, 1) + "\n";
}
