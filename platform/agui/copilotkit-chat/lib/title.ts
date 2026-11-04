// A session's model-written title (POST /api/sessions/{id}/title, lib/api.ts): what the agent's POST /title
// is sent, read from the journal (never from the browser), and the call itself. Node-only: the browser asks
// for a title through lib/client.ts, never the agent.
import type { Message } from "@ag-ui/client";
import { isCompactionMarker } from "./compaction.ts";
import { pathTo } from "./rebuild.ts";
import type { Conversation } from "./rebuild.ts";
import { messageText } from "./sessions.ts";

export type TitleMessage = { role: "user" | "assistant"; content: string };
/** Asks for a title for the session `threadId` from its first message and answer; throws when there is none. */
export type Titler = (threadId: string, messages: TitleMessage[]) => Promise<string>;

export const TITLE_TIMEOUT_MS = 30_000;

/** The agent did not answer 200 with a title: its status (404 disabled, 422 no usable title, ...). */
export class TitleUnavailable extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`the agent answered ${status}`);
    this.name = "TitleUnavailable";
    this.status = status;
  }
}

/** The first user message and the first answer: the first completed run's own user message, and the text of
 *  the assistant messages that run added (compaction markers and tool calls left out; none when it has no
 *  text). null when no run completed or the user message has no text. */
export function firstExchange(conv: Conversation): TitleMessage[] | null {
  const run = conv.runs.find((r) => r.status === "completed");
  if (!run) return null;
  const added = run.added.map((id) => conv.nodes.get(id)!.message);
  // The run's own user message; a regenerate (no new user message) answers the last one on its path.
  const user = added.find((m) => m.role === "user") ?? pathTo(conv, run.anchor).findLast((m) => m.role === "user");
  const question = user ? messageText(user).trim() : "";
  if (!question) return null;
  const answer = added
    .filter((m: Message) => m.role === "assistant" && !isCompactionMarker(m))
    .map((m) => messageText(m).trim())
    .filter(Boolean)
    .join("\n");
  const messages: TitleMessage[] = [{ role: "user", content: question }];
  if (answer) messages.push({ role: "assistant", content: answer });
  return messages;
}

type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

/** The agent's POST /title, next to its /agent (`agentUrl`), with the bearer key the chat runtime uses. */
export function agentTitler(agentUrl: string, key: string, f: Fetch = fetch, timeoutMs = TITLE_TIMEOUT_MS): Titler {
  const url = new URL("/title", agentUrl).toString();
  return async (threadId, messages) => {
    const response = await f(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId, messages }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (response.status !== 200) {
      await response.body?.cancel();
      throw new TitleUnavailable(response.status);
    }
    const body = (await response.json()) as { title?: unknown };
    if (typeof body?.title !== "string") throw new TitleUnavailable(response.status);
    return body.title;
  };
}
