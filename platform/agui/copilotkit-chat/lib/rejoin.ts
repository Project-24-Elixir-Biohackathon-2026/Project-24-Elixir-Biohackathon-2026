// Opening a session whose run is still going (spec §6 *Opening a session*, decision 42): its holder sets the
// journal's history on its agent and then connects to the run (CopilotKit's connectAgent), which replays the
// thread's runs on the agent, past runs first and then the run in progress from its own RUN_STARTED. The
// replay's copies are matched by id against the history: the history stays, in order; a message of the run in
// progress is replaced in place by its live copy; what the history lacks is appended; every other replayed
// copy is dropped. Pure apart from the agent `rejoinAgent` is handed, so `node --test` covers it.
import { EventType } from "@ag-ui/client";
import type { BaseEvent, Message } from "@ag-ui/client";

/** `history`: the journal's branch. `current`: the agent's messages. `inProgress`: the ids of the run in
 *  progress (nextInProgress). */
export function rejoinedMessages(history: Message[], current: Message[], inProgress: ReadonlySet<string>): Message[] {
  const byId = new Map(current.map((m) => [m.id, m]));
  const known = new Set(history.map((m) => m.id));
  const kept = history.map((h) => (inProgress.has(h.id) ? (byId.get(h.id) ?? h) : h));
  return [...kept, ...current.filter((m) => !known.has(m.id))];
}

/** The ids the replay's events name since the last RUN_STARTED, that is the run in progress's: each event's
 *  `messageId` and `parentMessageId`, a TOOL_CALL_START's `toolCallId` (the assistant message @ag-ui/client
 *  creates when the event names no parent takes that id) and every message of a MESSAGES_SNAPSHOT (the
 *  recorder sends one right after RUN_STARTED: the run's own branch as the server holds it, never older than
 *  the history's copy). `ids` itself when the event adds none. */
export function nextInProgress(ids: ReadonlySet<string>, event: BaseEvent): ReadonlySet<string> {
  if (event.type === EventType.RUN_STARTED) return new Set();
  const e = event as { messageId?: unknown; parentMessageId?: unknown; toolCallId?: unknown; messages?: unknown };
  const named: string[] = [];
  if (typeof e.messageId === "string") named.push(e.messageId);
  if (typeof e.parentMessageId === "string") named.push(e.parentMessageId);
  if (event.type === EventType.TOOL_CALL_START && typeof e.toolCallId === "string") named.push(e.toolCallId);
  if (event.type === EventType.MESSAGES_SNAPSHOT && Array.isArray(e.messages)) {
    for (const m of e.messages as { id?: unknown }[]) if (typeof m?.id === "string") named.push(m.id);
  }
  if (named.every((id) => ids.has(id))) return ids;
  return new Set([...ids, ...named]);
}

/** The part of an AG-UI agent rejoinAgent needs. */
export type RejoinSource = {
  messages: Message[];
  setMessages(messages: Message[]): void;
  subscribe(s: {
    onEvent?: (p: { event: BaseEvent }) => void;
    onMessagesChanged?: () => void;
  }): { unsubscribe(): void };
};

/** Connects the agent (`connect`, the caller's `copilotkit.connectAgent({ agent })`) with its messages kept to
 *  rejoinedMessages(history, …), the history being the agent's messages as it starts. The merge runs on every
 *  message change while the connect lasts, from a subscriber made before `connect` is called, so it also
 *  catches connect's own clearing of the messages before React shows the empty list; and once after it ends,
 *  however it ends. It sets the messages only when the merge differs, or its own change would start it again.
 *
 *  Why every change: the event pipeline works on its own copy of the agent's messages, taken as it starts, and
 *  writes it back on every event, so a change made from outside lasts only to the next event. The race this
 *  rests on: the first merge (on connect's clear) must land after the pipeline has taken its copy, or the
 *  history's partial copy of the running message would sit in that copy and the replay would append its text
 *  to it a second time. CopilotKit 1.84.1 always took the copy first; what shows the race is the streamed
 *  text repeating. */
export async function rejoinAgent(agent: RejoinSource, connect: () => Promise<unknown>): Promise<void> {
  const history = agent.messages;
  let inProgress: ReadonlySet<string> = new Set();
  const merge = () => {
    const next = rejoinedMessages(history, agent.messages, inProgress);
    if (JSON.stringify(next) !== JSON.stringify(agent.messages)) agent.setMessages(next);
  };
  const sub = agent.subscribe({
    onEvent: ({ event }) => { inProgress = nextInProgress(inProgress, event); },
    onMessagesChanged: merge,
  });
  try {
    await connect();
  } finally {
    sub.unsubscribe();
    merge();
  }
}
