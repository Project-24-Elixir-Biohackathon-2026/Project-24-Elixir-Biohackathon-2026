import assert from "node:assert/strict";
import { test } from "node:test";
import { EventType } from "@ag-ui/client";
import type { BaseEvent, Message } from "@ag-ui/client";
import { nextInProgress, rejoinAgent, rejoinedMessages } from "./rejoin.ts";
import type { RejoinSource } from "./rejoin.ts";

const user = (id: string, content: string): Message => ({ id, role: "user", content });
const said = (id: string, content: string): Message => ({ id, role: "assistant", content });
const ids = (messages: Message[]) => messages.map((m) => m.id);
const once = (messages: Message[]) => new Set(ids(messages)).size === messages.length;

// The journal's branch: a past run (u1, a1) and the run in progress so far (u2, its partial answer a2).
const HISTORY: Message[] = [user("u1", "first"), said("a1", "one"), user("u2", "second"), said("a2", "tw")];

test("rejoinedMessages: a past run replayed is shown once", () => {
  const current = [user("u1", "first"), said("a1", "one")];
  const out = rejoinedMessages(HISTORY, current, new Set());
  assert.deepEqual(out, HISTORY);
});

test("rejoinedMessages: the current run's partial message is replaced by its live copy", () => {
  const current = [user("u1", "first"), said("a1", "one"), user("u2", "second"), said("a2", "two, whole")];
  const out = rejoinedMessages(HISTORY, current, new Set(["u2", "a2"]));
  assert.deepEqual(ids(out), ["u1", "a1", "u2", "a2"]);
  assert.equal((out[3] as { content: string }).content, "two, whole");
});

test("rejoinedMessages: a new message of the current run is appended", () => {
  const current = [user("u1", "first"), said("a1", "one"), said("a2", "two"), said("a3", "three")];
  const out = rejoinedMessages(HISTORY, current, new Set(["a2", "a3"]));
  assert.deepEqual(ids(out), ["u1", "a1", "u2", "a2", "a3"]);
});

test("rejoinedMessages: no replay: history unchanged", () => {
  assert.deepEqual(rejoinedMessages(HISTORY, [], new Set()), HISTORY);
  // connectAgent's own setMessages([]) mid-connect, with ids already collected: still the history.
  assert.deepEqual(rejoinedMessages(HISTORY, [], new Set(["u2", "a2"])), HISTORY);
});

test("rejoinedMessages: a tool call and its result of the current run keep each id once", () => {
  const call: Message = {
    id: "a2", role: "assistant", content: "tw",
    toolCalls: [{ id: "tc1", type: "function", function: { name: "run_command", arguments: "{}" } }],
  };
  const result: Message = { id: "t1", role: "tool", toolCallId: "tc1", content: "ok" };
  const current = [user("u1", "first"), said("a1", "one"), user("u2", "second"), call, result];
  const out = rejoinedMessages(HISTORY, current, new Set(["a2", "tc1", "t1"]));
  assert.deepEqual(ids(out), ["u1", "a1", "u2", "a2", "t1"]);
  assert.ok(once(out));
  assert.equal(out[3], call);
});

test("rejoinedMessages: a MESSAGES_SNAPSHOT during the replay keeps each id once", () => {
  // The snapshot is the run's branch as the server holds it: every id the history has, and newer copies.
  const snapshot = [user("u1", "first"), said("a1", "one, as the server holds it"), user("u2", "second")];
  const current = [...snapshot, said("a2", "two")];
  const out = rejoinedMessages(HISTORY, current, new Set([...ids(snapshot), "a2"]));
  assert.deepEqual(ids(out), ["u1", "a1", "u2", "a2"]);
  assert.equal((out[1] as { content: string }).content, "one, as the server holds it");
});

// A replay as connect sends it: a past run (compacted), then the run in progress from its RUN_STARTED.
const REPLAY: BaseEvent[] = [
  { type: EventType.RUN_STARTED, threadId: "s", runId: "r1" },
  { type: EventType.TEXT_MESSAGE_START, messageId: "a1", role: "assistant" },
  { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "a1", delta: "one" },
  { type: EventType.TEXT_MESSAGE_END, messageId: "a1" },
  { type: EventType.RUN_FINISHED, threadId: "s", runId: "r1" },
  { type: EventType.RUN_STARTED, threadId: "s", runId: "r2" },
  {
    type: EventType.MESSAGES_SNAPSHOT,
    messages: [user("u1", "first"), said("a1", "one, as the server holds it"), user("u2", "second")],
  },
  { type: EventType.TEXT_MESSAGE_START, messageId: "a2", role: "assistant" },
  { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "a2", delta: "two" },
  { type: EventType.TOOL_CALL_START, toolCallId: "tc1", toolCallName: "run_command", parentMessageId: "a2" },
  { type: EventType.TOOL_CALL_END, toolCallId: "tc1" },
  { type: EventType.TOOL_CALL_START, toolCallId: "tc2", toolCallName: "run_command" },
  { type: EventType.TOOL_CALL_RESULT, messageId: "t1", toolCallId: "tc1", content: "ok" },
] as BaseEvent[];

test("nextInProgress marks the current run's ids, a snapshot's included, and no past run's", () => {
  let marked: ReadonlySet<string> = new Set();
  for (const event of REPLAY) marked = nextInProgress(marked, event);
  assert.deepEqual([...marked].sort(), ["a1", "a2", "t1", "tc1", "tc2", "u1", "u2"]);
  // Before the second RUN_STARTED only the past run's ids; it empties the set.
  let past: ReadonlySet<string> = new Set();
  for (const event of REPLAY.slice(0, 5)) past = nextInProgress(past, event);
  assert.deepEqual([...past], ["a1"]);
  assert.deepEqual([...nextInProgress(past, REPLAY[5])], []);

  // rejoinedMessages over the collector's result: the snapshot's copy, each id once.
  const current = [
    user("u1", "first"), said("a1", "one, as the server holds it"), user("u2", "second"), said("a2", "two"),
    { id: "t1", role: "tool", toolCallId: "tc1", content: "ok" } as Message,
  ];
  const out = rejoinedMessages(HISTORY, current, marked);
  assert.deepEqual(ids(out), ["u1", "a1", "u2", "a2", "t1"]);
  assert.equal((out[1] as { content: string }).content, "one, as the server holds it");
  assert.equal((out[3] as { content: string }).content, "two");
});

test("nextInProgress: an event naming no id leaves the set as it is", () => {
  const marked = new Set(["a2"]);
  assert.equal(nextInProgress(marked, { type: EventType.STEP_STARTED, stepName: "x" } as BaseEvent), marked);
});

// A fake agent with CopilotKit's connect shape: it clears the messages, then streams the replay's events, each
// followed by the pipeline writing back its own copy (as @ag-ui/client does on every event).
function fakeAgent(initial: Message[]) {
  let subs: Parameters<RejoinSource["subscribe"]>[0][] = [];
  const agent: RejoinSource & { sets: number } = {
    messages: initial,
    sets: 0,
    setMessages(m) {
      agent.sets += 1;
      agent.messages = m;
      for (const s of [...subs]) s.onMessagesChanged?.();
    },
    subscribe(s) {
      subs.push(s);
      return { unsubscribe: () => { subs = subs.filter((x) => x !== s); } };
    },
  };
  const emit = (event: BaseEvent, pipeline: Message[]) => {
    for (const s of [...subs]) s.onEvent?.({ event });
    agent.messages = pipeline;
    for (const s of [...subs]) s.onMessagesChanged?.();
  };
  return { agent, emit, subscribers: () => subs.length };
}

test("rejoinAgent: merges from connect's own clear on, and once after it resolves", async () => {
  const { agent, emit, subscribers } = fakeAgent(HISTORY);
  // What a render would see: the agent's messages once each change's subscribers have all run.
  const shown: string[][] = [];
  const step = (change: () => void) => { change(); shown.push(ids(agent.messages)); };
  await rejoinAgent(agent, async () => {
    step(() => agent.setMessages([])); // CopilotKitCore.connectAgent's fresh restore
    await Promise.resolve();
    step(() => emit(REPLAY[0], []));
    step(() => emit(REPLAY[1], [said("a1", "")]));
    step(() => emit(REPLAY[5], [said("a1", "one")]));
    step(() => emit(REPLAY[6], [user("u1", "first"), said("a1", "one, as the server holds it"), user("u2", "second")]));
    step(() => emit(REPLAY[7], [user("u1", "first"), said("a1", "one, as the server holds it"), user("u2", "second"), said("a2", "")]));
    step(() => emit(REPLAY[8], [user("u1", "first"), said("a1", "one, as the server holds it"), user("u2", "second"), said("a2", "two")]));
  });
  // Every list holds the history's ids, in order, each once: the empty list is never seen.
  for (const list of shown) assert.deepEqual(list, ["u1", "a1", "u2", "a2"]);
  assert.deepEqual(ids(agent.messages), ["u1", "a1", "u2", "a2"]);
  assert.equal((agent.messages[1] as { content: string }).content, "one, as the server holds it");
  assert.equal((agent.messages[3] as { content: string }).content, "two");
  assert.equal(subscribers(), 0, "its own subscriber is gone once the connect has resolved");
});

test("rejoinAgent: sets the messages only when the merge differs", async () => {
  const { agent } = fakeAgent(HISTORY);
  await rejoinAgent(agent, async () => {});
  assert.equal(agent.sets, 0);
});

test("rejoinAgent: a connect that throws leaves the history, unsubscribes, and the error reaches the caller", async () => {
  const { agent, subscribers } = fakeAgent(HISTORY);
  const failing = async () => {
    agent.setMessages([]);
    throw new Error("no connect");
  };
  await assert.rejects(rejoinAgent(agent, failing), /no connect/);
  assert.deepEqual(agent.messages, HISTORY);
  assert.equal(subscribers(), 0);
});
