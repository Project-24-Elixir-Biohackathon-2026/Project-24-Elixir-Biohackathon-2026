// A client's history against the journal (spec §13, *The run route*, step 2; decision 2). The anchor is the
// client message the journal holds that the journal added last; the new messages are the user messages after
// it (in the client's order) whose ids the journal does not hold; whatever else differs from the journal is
// ignored content, recorded with its kind. Pure: no I/O, no clock.
import type { Message } from "@ag-ui/client";
import type { Ignored } from "./journal.ts";
import { isBoundary, pathTo } from "./rebuild.ts";
import type { Conversation, Node } from "./rebuild.ts";

export type Classification = { anchor: string | null; path: Message[]; newMessages: Message[]; ignored: Ignored[] };

// JSON with object keys sorted at every depth, so key order never counts as a difference.
function sorted(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sorted);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((k) => [k, sorted((value as Record<string, unknown>)[k])]));
  }
  return value;
}

const blank = (v: unknown) => v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0);

// The compared fields only: role, content, tool calls (id, name, arguments) and tool call id. An absent field
// and an empty one compare equal; fields CopilotKit may add (name, metadata, encryptedValue, a tool call's
// type) are not compared.
export function canonical(message: Message): string {
  const m = message as { role?: unknown; content?: unknown; toolCalls?: unknown; toolCallId?: unknown };
  const fields: Record<string, unknown> = { role: m.role };
  if (!blank(m.content)) fields.content = m.content;
  if (Array.isArray(m.toolCalls) && m.toolCalls.length > 0) {
    fields.toolCalls = m.toolCalls.map((call: { id?: unknown; function?: { name?: unknown; arguments?: unknown } }) =>
      ({ id: call?.id, name: call?.function?.name, arguments: call?.function?.arguments }));
  } else if (!blank(m.toolCalls)) {
    fields.toolCalls = m.toolCalls; // not a list: compared as sent, so a garbage value counts as edited
  }
  if (!blank(m.toolCallId)) fields.toolCallId = m.toolCallId;
  return JSON.stringify(sorted(fields));
}

const idOf = (message: Message): string | null => (typeof message?.id === "string" ? message.id : null);

export function classify(conv: Conversation | null, client: Message[]): Classification {
  const nodes = conv?.nodes ?? new Map<string, Node>();
  const order = new Map([...nodes.keys()].map((id, index) => [id, index])); // journal order (rebuild's insertion)
  const known = (id: string | null): id is string => id !== null && nodes.has(id);

  // The anchor: of the client's messages the journal holds, the one it added last (Review Focus 1: the
  // client's own order does not decide). Its position in the client's history splits before from after.
  let anchor: string | null = null;
  let anchorAt = -1;
  for (const [index, message] of client.entries()) {
    const id = idOf(message);
    if (message?.role === "system" || !known(id)) continue;
    if (anchor === null || order.get(id)! > order.get(anchor)!) [anchor, anchorAt] = [id, index];
  }

  // An anchor inside a run moves back to the last boundary on its path; the journal's messages after that
  // boundary are deleted, so the agent is never sent a dangling tool call.
  const cut: string[] = [];
  const path = conv ? pathTo(conv, anchor) : [];
  if (conv) {
    while (path.length > 0 && !isBoundary(conv, path.at(-1)!.id)) cut.unshift(path.pop()!.id);
    anchor = path.at(-1)?.id ?? null;
  }

  const ignored: Ignored[] = [];
  const newMessages: Message[] = [];
  const seen = new Set<string>();
  for (const [index, message] of client.entries()) {
    const id = idOf(message);
    if (message?.role === "system") {
      ignored.push({ kind: "system", message });
      continue;
    }
    if (known(id)) {
      // Review Focus 2: a known id is never new, wherever it stands; it is ignored only if it differs.
      if (canonical(message) !== canonical(nodes.get(id)!.message)) ignored.push({ kind: "edited", message });
      seen.add(id);
      continue;
    }
    if (id !== null && index > anchorAt && message.role === "user" && !seen.has(id)) {
      newMessages.push(message);
    } else {
      ignored.push({ kind: "fabricated", message });
    }
    if (id !== null) seen.add(id);
  }

  // Deleted, in path order: the path's messages the client left out, then every cut message (the path and the
  // cut are disjoint).
  for (const message of path) if (!seen.has(message.id)) ignored.push({ kind: "deleted", message: message.id });
  for (const id of cut) ignored.push({ kind: "deleted", message: id });
  return { anchor, path, newMessages, ignored };
}
