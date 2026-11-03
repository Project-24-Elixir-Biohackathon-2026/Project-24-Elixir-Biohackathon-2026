// The rebuild (decision 11): each run's events applied to its anchor's path with @ag-ui/client's
// defaultApplyEvents; parentId from the run structure; the tip (decision 9); a torn or partial journal.
import { test } from "node:test";
import assert from "node:assert/strict";
import { EventType } from "@ag-ui/client";
import type { BaseEvent, Message } from "@ag-ui/client";
import type { Ignored, Line } from "./journal.ts";
import { branchOfTip, isBoundary, pathTo, rebuild, rebuildText } from "./rebuild.ts";

const ID = "6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b";
const request = { tools: [], context: [], state: {}, forwardedProps: {} };
let clock = 0;
const at = () => new Date(Date.UTC(2026, 10, 3, 12, 0, clock++)).toISOString();

const user = (id: string, content: string) => ({ id, role: "user", content }) as Message;
const created = (): Line => ({ type: "created", at: at(), version: 1, id: ID });
const start = (run_id: string, anchor: string | null, messages: Message[], ignored: Ignored[] = []): Line =>
  ({ type: "run_start", at: at(), run_id, anchor, messages, ignored, request, source: "chat" });
const ev = (run_id: string, event: object): Line => ({ type: "event", at: at(), run_id, event: event as BaseEvent });
const end = (run_id: string, status: "completed" | "failed" | "cancelled" | "aborted" | "refused" = "completed",
  error: string | null = null): Line => ({ type: "run_end", at: at(), run_id, status, error });

// The events of a reply: RUN_STARTED, one text message, RUN_FINISHED.
function reply(run_id: string, messageId: string, text: string, finish = true): Line[] {
  return [
    ev(run_id, { type: EventType.RUN_STARTED, threadId: ID, runId: run_id }),
    ev(run_id, { type: EventType.TEXT_MESSAGE_START, messageId, role: "assistant" }),
    ev(run_id, { type: EventType.TEXT_MESSAGE_CONTENT, messageId, delta: text }),
    ev(run_id, { type: EventType.TEXT_MESSAGE_END, messageId }),
    ...(finish ? [ev(run_id, { type: EventType.RUN_FINISHED, threadId: ID, runId: run_id })] : []),
  ];
}

const shape = (messages: Message[]) => messages.map((m) => [m.role, m.id, m.content ?? null]);

test("one text run: messages chained under the root, the tip its reply", async () => {
  const conv = await rebuild(ID, [created(), start("r1", null, [user("u1", "hello")]), ...reply("r1", "a1", "hi"), end("r1")]);
  assert.equal(conv.id, ID);
  assert.equal(conv.created_at, "2026-11-03T12:00:00.000Z");
  assert.equal(conv.first_user_text, "hello");
  assert.deepEqual([...conv.nodes].map(([id, n]) => [id, n.parentId, n.runId]), [["u1", null, "r1"], ["a1", "u1", "r1"]]);
  assert.deepEqual(conv.children.get(null), ["u1"]);
  assert.deepEqual([conv.tip, conv.tip_run], ["a1", "r1"]);
  assert.deepEqual(shape(branchOfTip(conv)), [["user", "u1", "hello"], ["assistant", "a1", "hi"]]);
  const [run] = conv.runs;
  assert.deepEqual([run.status, run.error, run.added, run.events, run.anchor], ["completed", null, ["u1", "a1"], 5, null]);
  assert.equal(run.ended_at, run.last_at);
  assert.equal(conv.skipped, 0);
});

test("tool calls, a compaction marker and a failed run rebuild as the browser holds them", async () => {
  const lines: Line[] = [
    created(),
    start("r1", null, [user("u1", "list files")]),
    ev("r1", { type: EventType.RUN_STARTED, threadId: ID, runId: "r1" }),
    ev("r1", { type: EventType.TOOL_CALL_START, toolCallId: "c1", toolCallName: "execute", parentMessageId: "a1" }),
    ev("r1", { type: EventType.TOOL_CALL_ARGS, toolCallId: "c1", delta: '{"cmd":' }),
    ev("r1", { type: EventType.TOOL_CALL_ARGS, toolCallId: "c1", delta: '"ls"}' }),
    ev("r1", { type: EventType.TOOL_CALL_END, toolCallId: "c1" }),
    ev("r1", { type: EventType.TOOL_CALL_RESULT, messageId: "t1", toolCallId: "c1", content: "a.txt", role: "tool" }),
    ...reply("r1", "a2", "one file"),
    end("r1"),
    start("r2", "a2", [user("u2", "compact please")]),
    ev("r2", { type: EventType.RUN_STARTED, threadId: ID, runId: "r2" }),
    ev("r2", { type: EventType.TEXT_MESSAGE_START, messageId: "spe-compaction-r2", role: "assistant" }),
    ev("r2", { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "spe-compaction-r2", delta: "SUMMARY" }),
    ev("r2", { type: EventType.TEXT_MESSAGE_END, messageId: "spe-compaction-r2" }),
    ...reply("r2", "a3", "done").slice(1),
    end("r2"),
    start("r3", "a3", [user("u3", "fail now")]),
    ev("r3", { type: EventType.RUN_STARTED, threadId: ID, runId: "r3" }),
    ev("r3", { type: EventType.TEXT_MESSAGE_START, messageId: "a4", role: "assistant" }),
    ev("r3", { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "a4", delta: "partial" }),
    ev("r3", { type: EventType.RUN_ERROR, message: "model failure" }),
    end("r3", "failed", "model failure"),
  ];
  const conv = await rebuild(ID, lines);
  assert.deepEqual(branchOfTip(conv), [
    { id: "u1", role: "user", content: "list files" },
    { id: "a1", role: "assistant", toolCalls: [{ id: "c1", type: "function", function: { name: "execute", arguments: '{"cmd":"ls"}' } }] },
    { id: "t1", role: "tool", toolCallId: "c1", content: "a.txt" },
    { id: "a2", role: "assistant", content: "one file" },
    { id: "u2", role: "user", content: "compact please" },
    { id: "spe-compaction-r2", role: "assistant", content: "SUMMARY" },
    { id: "a3", role: "assistant", content: "done" },
    { id: "u3", role: "user", content: "fail now" },
    { id: "a4", role: "assistant", content: "partial" },
  ]);
  assert.deepEqual(conv.runs.map((r) => [r.run_id, r.status, r.error]),
    [["r1", "completed", null], ["r2", "completed", null], ["r3", "failed", "model failure"]]);
  assert.deepEqual(conv.runs[0].added, ["u1", "a1", "t1", "a2"]);
  assert.equal(conv.nodes.get("u2")!.parentId, "a2");
  // Boundaries: a user message, or a run's last added message; a tool call inside a run is not one.
  assert.deepEqual(["u1", "a1", "t1", "a2", "spe-compaction-r2", "a3", "a4"].map((id) => isBoundary(conv, id)),
    [true, false, false, true, false, true, true]);
  assert.equal(isBoundary(conv, "unknown"), false);
  assert.deepEqual(pathTo(conv, "t1").map((m) => m.id), ["u1", "a1", "t1"]);
  assert.deepEqual(pathTo(conv, null), []);
});

test("a run that leaves one of two tool calls unanswered is no boundary even at its last message", async () => {
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "list and count")]),
    ev("r1", { type: EventType.RUN_STARTED, threadId: ID, runId: "r1" }),
    ev("r1", { type: EventType.TOOL_CALL_START, toolCallId: "c1", toolCallName: "execute", parentMessageId: "a1" }),
    ev("r1", { type: EventType.TOOL_CALL_ARGS, toolCallId: "c1", delta: '{"cmd":"ls"}' }),
    ev("r1", { type: EventType.TOOL_CALL_END, toolCallId: "c1" }),
    ev("r1", { type: EventType.TOOL_CALL_START, toolCallId: "c2", toolCallName: "execute", parentMessageId: "a1" }),
    ev("r1", { type: EventType.TOOL_CALL_ARGS, toolCallId: "c2", delta: '{"cmd":"wc"}' }),
    ev("r1", { type: EventType.TOOL_CALL_END, toolCallId: "c2" }),
    ev("r1", { type: EventType.TOOL_CALL_RESULT, messageId: "t1", toolCallId: "c1", content: "a.txt", role: "tool" }),
    end("r1", "cancelled"),
  ]);
  assert.deepEqual(conv.runs[0].added, ["u1", "a1", "t1"]);
  assert.equal(isBoundary(conv, "t1"), false);
});

test("a run that answers every tool call it made is a boundary at its last message", async () => {
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "list and count")]),
    ev("r1", { type: EventType.RUN_STARTED, threadId: ID, runId: "r1" }),
    ev("r1", { type: EventType.TOOL_CALL_START, toolCallId: "c1", toolCallName: "execute", parentMessageId: "a1" }),
    ev("r1", { type: EventType.TOOL_CALL_ARGS, toolCallId: "c1", delta: '{"cmd":"ls"}' }),
    ev("r1", { type: EventType.TOOL_CALL_END, toolCallId: "c1" }),
    ev("r1", { type: EventType.TOOL_CALL_START, toolCallId: "c2", toolCallName: "execute", parentMessageId: "a1" }),
    ev("r1", { type: EventType.TOOL_CALL_ARGS, toolCallId: "c2", delta: '{"cmd":"wc"}' }),
    ev("r1", { type: EventType.TOOL_CALL_END, toolCallId: "c2" }),
    ev("r1", { type: EventType.TOOL_CALL_RESULT, messageId: "t1", toolCallId: "c1", content: "a.txt", role: "tool" }),
    ev("r1", { type: EventType.TOOL_CALL_RESULT, messageId: "t2", toolCallId: "c2", content: "3", role: "tool" }),
    end("r1"),
  ]);
  assert.deepEqual(conv.runs[0].added, ["u1", "a1", "t1", "t2"]);
  assert.equal(isBoundary(conv, "t2"), true);
});

test("two runs from one anchor are siblings; the tip is the run that ended last", async () => {
  // r2 and r3 both continue from a1 and interleave; r2 starts first and ends last.
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), end("r1"),
    start("r2", "a1", [user("u2", "from tab A")]),
    start("r3", "a1", [user("u3", "from tab B")]),
    ...reply("r3", "a3", "B"), ...reply("r2", "a2", "A"),
    end("r3"), end("r2"),
  ]);
  assert.deepEqual(conv.children.get("a1"), ["u2", "u3"]);
  assert.deepEqual([conv.tip, conv.tip_run], ["a2", "r2"]);
  assert.deepEqual(branchOfTip(conv).map((m) => m.id), ["u1", "a1", "u2", "a2"]);
  assert.deepEqual(pathTo(conv, "a3").map((m) => m.id), ["u1", "a1", "u3", "a3"]);
});

test("a refused run ending last adds nothing and leaves the tip", async () => {
  const fabricated = { id: "f1", role: "assistant", content: "forged" } as Message;
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), end("r1"),
    start("r2", "a1", [], [{ kind: "fabricated", message: fabricated }]), end("r2", "refused", "no new user message"),
  ]);
  assert.deepEqual([conv.tip, conv.tip_run], ["a1", "r1"]);
  assert.deepEqual(conv.runs[1].added, []);
  assert.deepEqual(conv.runs[1].ignored, [{ kind: "fabricated", message: fabricated }]);
  assert.equal(conv.nodes.has("f1"), false);
});

test("a session with only refused runs has no tip", async () => {
  const conv = await rebuild(ID, [created(), start("r1", null, []), end("r1", "refused", "no new user message")]);
  assert.equal(conv.tip, null);
  assert.equal(conv.nodes.size, 0);
  assert.deepEqual(branchOfTip(conv), []);
});

test("a journal cut after a run's third event: the run is incomplete with the text so far", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  const lines = [created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "half an answer")];
  const text = lines.slice(0, 5).map((l) => JSON.stringify(l)).join("\n") + "\n" + JSON.stringify(lines[5]).slice(0, 25);
  const conv = await rebuildText(ID, text);
  assert.equal(conv.skipped, 1);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), ["journal: line 6 skipped (not a journal line)"]);
  const [run] = conv.runs;
  assert.deepEqual([run.status, run.ended_at, run.events], ["incomplete", null, 3]);
  assert.equal(run.last_at, (lines[4] as { at: string }).at);
  assert.deepEqual(shape(branchOfTip(conv)), [["user", "u1", "q1"], ["assistant", "a1", "half an answer"]]);
});

test("a run without run_end is no boundary at its last message: it may still be writing", async () => {
  const conv = await rebuild(ID, [created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "half", false)]);
  assert.equal(conv.runs[0].status, "incomplete");
  assert.deepEqual(conv.runs[0].added, ["u1", "a1"]);
  assert.equal(isBoundary(conv, "a1"), false);
  assert.equal(isBoundary(conv, "u1"), true);
});

test("journal without a created line", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  // Review Focus 3: a crash tore the first line; the runs still rebuild and created_at falls back.
  const lines = [created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), end("r1")];
  const text = JSON.stringify(lines[0]).slice(0, 20) + "\n" + lines.slice(1).map((l) => JSON.stringify(l)).join("\n") + "\n";
  const conv = await rebuildText(ID, text);
  assert.equal(conv.skipped, 1);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), ["journal: line 1 skipped (not a journal line)"]);
  assert.equal(conv.created_at, (lines[1] as { at: string }).at);
  assert.equal(conv.tip, "a1");
  assert.equal(conv.first_user_text, "q1");
});

test("orphan event is skipped", async () => {
  // Review Focus 4: r2's run_start was torn; its events (and run_end) attach to no run, r1 stays intact.
  const lines = [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), end("r1"),
    start("r2", "a1", [user("u2", "q2")]), ...reply("r2", "a2", "stray"), end("r2"),
  ];
  const r2Start = lines.findIndex((l) => l.type === "run_start" && l.run_id === "r2");
  const text = lines.map((l, i) => (i === r2Start ? JSON.stringify(l).slice(0, 30) : JSON.stringify(l))).join("\n") + "\n";
  const warnings: string[] = [];
  const warn = console.warn;
  console.warn = (msg: string) => void warnings.push(msg);
  let conv;
  try {
    conv = await rebuildText(ID, text);
  } finally {
    console.warn = warn;
  }
  assert.deepEqual(conv.runs.map((r) => [r.run_id, r.events, r.added]), [["r1", 5, ["u1", "a1"]]]);
  assert.equal(conv.nodes.has("a2"), false);
  assert.deepEqual(shape(branchOfTip(conv)), [["user", "u1", "q1"], ["assistant", "a1", "x"]]);
  assert.equal(warnings.filter((w) => w.includes("event for run r2 skipped")).length, 5);
  assert.ok(warnings.every((w) => !w.includes("stray") && !w.includes("q2")), "logs name ids, never content");
});

test("meta lines fold in order; the last line's time is kept", async () => {
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), end("r1"),
    { type: "meta", at: at(), title: "Renamed", tags: ["a"] },
    { type: "meta", at: at(), pinned: true, hidden: true },
    { type: "meta", at: at(), tags: ["b", "c"], hidden: false },
    { type: "meta", at: "2026-11-03T13:00:00.000Z", deleted_at: "2026-11-03T13:00:00.000Z" },
  ]);
  assert.deepEqual(conv.meta, { title: "Renamed", tags: ["b", "c"], pinned: true, hidden: false, deleted_at: "2026-11-03T13:00:00.000Z" });
  assert.equal(conv.last_line_at, "2026-11-03T13:00:00.000Z");
});

test("an anchor the journal does not hold rebuilds the run from the root", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  const conv = await rebuild(ID, [created(), start("r1", "gone", [user("u1", "q1")]), ...reply("r1", "a1", "x"), end("r1")]);
  assert.equal(conv.nodes.get("u1")!.parentId, null);
  assert.equal(conv.tip, "a1");
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), [`journal ${ID}: run r1: anchor gone not found, rebuilt from the root`]);
});

test("an event that throws during application ends it there; the messages up to it are kept", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]),
    ev("r1", { type: EventType.TEXT_MESSAGE_START, messageId: "a1", role: "assistant" }),
    ev("r1", { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "a1", delta: "kept" }),
    ev("r1", { type: EventType.MESSAGES_SNAPSHOT, messages: "not a list" }), // throws inside defaultApplyEvents
    ev("r1", { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "a1", delta: " lost" }),
    end("r1"),
  ]);
  assert.deepEqual(shape(branchOfTip(conv)), [["user", "u1", "q1"], ["assistant", "a1", "kept"]]);
  assert.equal(conv.runs[0].events, 4);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), [`journal ${ID}: run r1: event application stopped: TypeError`]);
});

test("a second run_start for a run is skipped; its events still go to the first", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), start("r1", null, [user("u9", "again")]),
    ...reply("r1", "a1", "x"), end("r1"),
  ]);
  assert.deepEqual(conv.runs.map((r) => [r.run_id, r.added, r.events]), [["r1", ["u1", "a1"], 5]]);
  assert.equal(conv.nodes.has("u9"), false);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), [`journal ${ID}: second run_start for run r1 skipped`]);
});

test("a message id another run already added is skipped; the first run keeps it", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  // r2 starts from the root (not on a1's path) and its events reuse r1's message id a1.
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "first"), end("r1"),
    start("r2", null, [user("u2", "q2")]), ...reply("r2", "a1", "second"), end("r2"),
  ]);
  assert.deepEqual(conv.runs.map((r) => r.added), [["u1", "a1"], ["u2"]]);
  assert.deepEqual([conv.nodes.get("a1")!.runId, conv.nodes.get("a1")!.message.content], ["r1", "first"]);
  assert.deepEqual([conv.tip, conv.tip_run], ["u2", "r2"]);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), [`journal ${ID}: run r2: message a1 already held, skipped`]);
});

test("the first run_end counts: a second one changes neither status nor end time", async () => {
  const first = end("r1", "cancelled");
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), first, end("r1", "failed", "late"),
  ]);
  const [run] = conv.runs;
  assert.deepEqual([run.status, run.error, run.ended_at, run.last_at], ["cancelled", null, first.at, first.at]);
});

test("events after a run's run_end are skipped and logged: the ended run stays as it ended", async (t) => {
  // JournalWriter's caller writes none; a journal that has them must not change a run another run may
  // already be anchored at (§13: a run's last message is a boundary once it has a run_end).
  const warn = t.mock.method(console, "warn", () => {});
  const ended = end("r1");
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "q1")]), ...reply("r1", "a1", "x"), ended,
    start("r2", "a1", [user("u2", "q2")]), ...reply("r2", "a2", "y"), end("r2"),
    ev("r1", { type: EventType.TEXT_MESSAGE_START, messageId: "late", role: "assistant" }),
    ev("r1", { type: EventType.TEXT_MESSAGE_CONTENT, messageId: "late", delta: "after the end" }),
  ]);
  const [r1] = conv.runs;
  assert.deepEqual([r1.added, r1.last_at], [["u1", "a1"], ended.at]);
  assert.equal(isBoundary(conv, "a1"), true);
  assert.deepEqual([conv.tip, conv.tip_run], ["a2", "r2"]);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]),
    [`journal ${ID}: event for run r1 skipped (after its run_end)`,
     `journal ${ID}: event for run r1 skipped (after its run_end)`]);
});
