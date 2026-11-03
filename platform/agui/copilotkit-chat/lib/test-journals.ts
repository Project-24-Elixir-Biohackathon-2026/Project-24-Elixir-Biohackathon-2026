// Test helper: a session's lines as the recorder writes them, without a recorder or an agent.
import { randomUUID } from "node:crypto";
import { EventType } from "@ag-ui/client";
import type { BaseEvent, Message } from "@ag-ui/client";
import type { RunStatus } from "./journal.ts";
import { withSession } from "./sessions.ts";
import type { Journals } from "./sessions.ts";

export type Seeded = { id: string; runId: string; user: Message; replyId: string };

/** One run: `text` as its new user message and "echo: <text>" as the reply. Without `opts.id` a new session
 *  starts with its `created` line; with it, the run continues that session from `opts.anchor`. */
export async function seedRun(
  journals: Journals,
  text: string,
  opts: { id?: string; anchor?: string | null; status?: RunStatus } = {},
): Promise<Seeded> {
  const id = opts.id ?? randomUUID();
  const runId = randomUUID();
  const user = { id: randomUUID(), role: "user", content: text } as Message;
  const replyId = `reply-${runId}`;
  const ids = { threadId: id, runId };
  const events = [
    { type: EventType.RUN_STARTED, ...ids },
    { type: EventType.TEXT_MESSAGE_START, messageId: replyId, role: "assistant" },
    { type: EventType.TEXT_MESSAGE_CONTENT, messageId: replyId, delta: `echo: ${text}` },
    { type: EventType.TEXT_MESSAGE_END, messageId: replyId },
    { type: EventType.RUN_FINISHED, ...ids },
  ] as BaseEvent[];
  await withSession(id, async () => {
    if (opts.id === undefined) await journals.append(id, { type: "created", version: 1, id }, "soon");
    await journals.append(id, {
      type: "run_start", run_id: runId, anchor: opts.anchor ?? null, messages: [user], ignored: [],
      request: { tools: [], context: [], state: {}, forwardedProps: {} }, source: "chat",
    }, "now");
    for (const event of events) await journals.append(id, { type: "event", run_id: runId, event }, "soon");
    await journals.append(id, { type: "run_end", run_id: runId, status: opts.status ?? "completed", error: null }, "now");
  });
  return { id, runId, user, replyId };
}
