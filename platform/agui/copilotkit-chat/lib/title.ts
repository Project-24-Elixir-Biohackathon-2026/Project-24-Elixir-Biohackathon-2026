// A session's model-written title (POST /api/sessions/{id}/title, lib/api.ts): what the agent's POST /title
// is sent, read from the journal (never from the browser), and the call itself. Node-only: the browser asks
// for a title through lib/client.ts, never the agent.
import type { Conversation } from "./rebuild.ts";
import { messageText } from "./sessions.ts";

export type TitleMessage = { role: "user" | "assistant"; content: string };
/** Asks for a title for the session `threadId` from its first question; throws when there is none. */
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

/** The session's first question: the user message of the first run that added one with text, whatever that
 *  run's status (still running, finished, failed or stopped), so a title can be asked for as soon as the run
 *  starts. Only the question: the answer may not exist yet. null when no run added a user message with text. */
export function firstQuestion(conv: Conversation): TitleMessage[] | null {
  for (const run of conv.runs) {
    const user = run.added.map((id) => conv.nodes.get(id)!.message).find((m) => m.role === "user");
    const question = user ? messageText(user).trim() : "";
    if (question) return [{ role: "user", content: question }];
  }
  return null;
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
