# Slice 2/2: `chat-ui` and the archive carry `/compact`

Delivers `chat-ui`'s and the archive's half of §15: a typed `/compact` or `/compact <focus>` is journaled as a
command (`run_start.command`, empty `messages`), the agent is sent the path with `forwardedProps.spe_command`,
the browser gets a snapshot of the path right after `RUN_STARTED` (the bubble goes, the divider lands), the two
refusals, a kept command bubble that stays known, a marker cut short that never counts, and the archive's
"Requested by the participant" line. The early output (Playwright screenshots and the journal's `run_start`)
comes first, in task 3; the paid de.NBI check last, in task 5.

**Implements:** the living AG-UI spec, [§15](../../../specs/2026-10-15-agui-frontend-design/15-compact-command.md):
decisions **31** and **33** (tasks 1 and 3), **32** (task 2), **34** and **37** (task 4), **38** and **39** (task
5); *Early output*, `/compact` (task 3); the plan README's rulings 3, 4, 6 and the proposed clarification *Slice
2* (tasks 2, 1, 4, 5); Review Focus 2 and 4 (task 2), 3 (task 4) and the archive half of 1 (task 5).

**Branch:** `impl/agui-compact-command-2-chat`, from `main` after slice 1 **and** the conversation record's slice
4/4 (#25) merged. Global Constraints: [plan README](README.md). Paths are relative to
`platform/agui/copilotkit-chat/` unless they start with `platform/` or `docs/`.

**Mid-slice handoffs** (at the budget, or by plan): after task 3, once the early output is posted on the PR; and
before task 5's de.NBI step, which waits on the user's OK for the paid run.

**Before step 1 of each task, re-read the functions it names on the branch's `main`:** #25 changes
`platform/dev/e2e/sessions.py`, this README and possibly `lib/recorder.ts` and `lib/export.ts` (the live
archive). Where it moved a line this file quotes, apply the change to the new shape and record a ruling only
if the behaviour differs.

**Verified facts this slice builds on** (read 2026-11-03 on `main` `3bdc37b`):

- `lib/recorder.ts`: `admit(input, handle)` classifies (`classify(conv, input.messages)`), writes `created` and
  `run_start` (`messages: classification.newMessages`, `request: { tools, context, state, forwardedProps }`),
  then refuses with `endHere("refused", NO_NEW_MESSAGE)` when `newMessages` is empty; `Admission` is
  `{ refused: string } | { refused: null; classification }`. `run` builds `messages = [...path, ...newMessages]`,
  `snapshotDue = ignored.length > 0` (decision 6), calls `this.runNext({ ...input, messages }, next)` and passes
  a `MESSAGES_SNAPSHOT` of `messages` right after `RUN_STARTED` when due. `REFUSAL_MESSAGES` lists six texts;
  `lib/reconcile.ts`'s `REFUSED_RUN_MESSAGES` is a browser-side copy that `reconcile.test.ts` pins to it.
- `lib/journal.ts`: `RunStartLine` has no `command`; `isLine`'s `run_start` case checks `run_id`, `anchor`,
  `messages`, `ignored`, `request`.
- `lib/anchor.ts`: `classify(conv, client)` knows an id only through `conv.nodes`; a known id is `seen`, never
  new, and `edited` when `canonical()` differs; an unknown user message after the anchor is new, anything else
  unknown `fabricated`.
- `lib/rebuild.ts`: `rebuild` replays each run with `applyEvents` and adds every message of `[...start.messages,
  ...after]` not on the path; `RunView` and `Conversation` have no command fields; `Pending.events` holds the
  run's events.
- `lib/sessions.ts`: `fold` sets `entry.added` only for a `run_start` with `messages.length > 0`; `listed` needs
  `added`; `get` returns null for an unlisted session, so `GET /api/sessions/{id}` (`lib/api.ts` `getSession`)
  gives 404.
- `lib/test-agent.ts`: scripted by the last user message's text with substring checks (`compact` sends a marker
  `spe-compaction-<runId>`); it reads nothing from `forwardedProps`.
- `lib/export.ts`: `toOpenWebUIChat` `put`s one message per run with `spe_run` and `spe_ignored`;
  `ExportedMessage` lists the `spe_` fields. The fixtures in `platform/dev/tests/fixtures/agui-record/` are five
  journals plus `live.bundle.json` and `final.bundle.json`, regenerated with `UPDATE_FIXTURES=1 npm test`.
- `platform/ansible/roles/run_archive/files/write_run.py`: `render_output(m)` renders a marker item as `## Compacted`
  plus `fence(summary)`; `render_agui_message` renders `render_status(m.get("spe_run"))` before it; the index's
  `compactions` counts `is_compaction` items (the prefix `spe-compaction-`, so manual markers count).
  `platform/dev/tests/test_write_run_agui.py`'s `rendered` fixture asserts "5 sessions (1 hidden, 1 deleted)".
- `platform/dev/e2e/sessions.py`: `LOCAL = ("all", "stop", "compaction")`; `check_compaction(r)` is the model
  for a scenario; `Run` has `shot`, `send(text, turn)`, `url_session`, `wait_runs`; the `else` branch of `main`
  runs `check_compaction` for the `compaction` scenario.
- Slice 1's contract (its task 2, *Interfaces*): `spe_command: {name: "compact", focus}` →`RUN_STARTED`, the
  marker's three events with id `spe-compaction-manual-…`, `RUN_FINISHED`; `fake_agent.py` answers a command
  with "Scripted summary on request of … Focus: <focus>".

---

### Task 1: the command run in the route

**Decisions:** 31; 33's `npm test` half; ruling 4.

**Files:**
- Create: `lib/command.ts`, `lib/command.test.ts`
- Modify: `lib/journal.ts`, `lib/recorder.ts`, `lib/test-agent.ts`
- Test: `lib/recorder.test.ts` (a `// --- /compact ---` section at the end)

**Interfaces:**
- Produces (tasks 2, 4 and 5 rely on these):
  ```ts
  // lib/command.ts
  export type Command = { name: "compact"; focus: string | null };
  export type CommandField = Command & { message_id: string };   // run_start.command
  export function parseCommand(content: unknown): Command | null;
  export function commandOf(newMessages: Message[]): CommandField | null;
  export function sameCommand(a: Command, b: Command): boolean;
  // lib/journal.ts
  RunStartLine.command?: CommandField;
  ```

- [ ] **Step 1: Write the failing tests.** `lib/command.test.ts`:

```ts
// What counts as a command (spec §15): one user message whose string content, trimmed, is /compact or
// /compact followed by whitespace and a focus. Case matters.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { Message } from "@ag-ui/client";
import { commandOf, parseCommand, sameCommand } from "./command.ts";

const user = (id: string, content: unknown) => ({ id, role: "user", content }) as Message;

test("parseCommand: the table of decision 31", () => {
  const cases: [unknown, ReturnType<typeof parseCommand>][] = [
    ["/compact", { name: "compact", focus: null }],
    ["  /compact  keep x ", { name: "compact", focus: "keep x" }],
    ["/compact\nkeep x\n\nand y\n", { name: "compact", focus: "keep x\n\nand y" }],
    ["/compact   ", { name: "compact", focus: null }],
    ["/compacted", null],
    ["/compact:", null],
    ["/COMPACT", null],
    ["please /compact", null],
    [[{ type: "text", text: "/compact" }], null],
    [undefined, null],
  ];
  for (const [content, expected] of cases) assert.deepEqual(parseCommand(content), expected, JSON.stringify(content));
});

test("commandOf: exactly one new message, a user message that parses", () => {
  assert.deepEqual(commandOf([user("k", "/compact keep x")]), { name: "compact", focus: "keep x", message_id: "k" });
  assert.equal(commandOf([user("k", "/compact"), user("m", "more")]), null);
  assert.equal(commandOf([{ id: "k", role: "assistant", content: "/compact" } as Message]), null);
  assert.equal(commandOf([]), null);
});

test("sameCommand compares name and focus", () => {
  assert.ok(sameCommand({ name: "compact", focus: null }, { name: "compact", focus: null }));
  assert.ok(!sameCommand({ name: "compact", focus: "a" }, { name: "compact", focus: null }));
});
```

In `lib/recorder.test.ts`, a section at the end:

```ts
// --- /compact (spec §15) ------------------------------------------------------------------------

const finish: Script = (sub, i) => {
  sub.next({ type: EventType.RUN_STARTED, threadId: i.threadId, runId: i.runId } as BaseEvent);
  sub.next({ type: EventType.RUN_FINISHED, threadId: i.threadId, runId: i.runId } as BaseEvent);
  sub.complete();
};

// A session of two tool turns, then one run whose last message has this content and these forwardedProps.
async function commandCase(content: unknown, forwardedProps: unknown = {}, extra: Message[] = []) {
  const journals = await tmpJournals();
  const id = randomUUID();
  const branch = await twoToolTurns(journals, id);
  const scripted = new Scripted(() => journals);
  scripted.script = finish;
  const runInput = { ...input(id, "", branch), forwardedProps };
  (runInput.messages.at(-1) as { content: unknown }).content = content;
  runInput.messages.push(...extra);
  const out = await drive(scripted, runInput, new HttpAgent({ url: UNUSED }));
  const start = ofType(await lines(journals, id), "run_start").at(-1)!;
  return { journals, id, branch, runInput, out, start, sent: scripted.received[0] };
}

test("decision 31: a command run is journaled as a command and sent the path plus spe_command", async () => {
  for (const [content, focus] of [["/compact", null], ["  /compact  keep x ", "keep x"]] as const) {
    const { branch, runInput, start, sent } = await commandCase(content);
    assert.deepEqual(start.command, { name: "compact", focus, message_id: runInput.messages.at(-1)!.id });
    assert.deepEqual(start.messages, []);
    assert.deepEqual(start.request.forwardedProps, {});
    assert.deepEqual(sent.messages.map(view), branch.map(view));
    assert.deepEqual(sent.forwardedProps, { spe_command: { name: "compact", focus } });
  }
});

test("decision 31: anything else is an ordinary message", async () => {
  for (const content of ["/compacted", "/compact:", "/COMPACT", [{ type: "text", text: "/compact" }]]) {
    const { start, sent } = await commandCase(content);
    assert.equal(start.command, undefined, JSON.stringify(content));
    assert.equal(start.messages.length, 1, JSON.stringify(content));
    assert.equal(sent.messages.length, 9, JSON.stringify(content)); // the path, then the message
  }
  const two = await commandCase("/compact", {}, [{ id: randomUUID(), role: "user", content: "more" } as Message]);
  assert.equal(two.start.command, undefined);
  assert.equal(two.start.messages.length, 2);
});

test("decision 31: a client's spe_command is removed on every run and kept in run_start.request", async () => {
  const forged = { spe_command: { name: "compact", focus: "forged" }, other: 1 };
  const plain = await commandCase("hello", forged);
  assert.deepEqual(plain.sent.forwardedProps, { other: 1 });
  assert.deepEqual(plain.start.request.forwardedProps, forged);
  const command = await commandCase("/compact mine", forged);
  assert.deepEqual(command.sent.forwardedProps, { other: 1, spe_command: { name: "compact", focus: "mine" } });
});

test("ruling 4: forwardedProps that is not an object: {} plus the command on a command run, as sent otherwise", async () => {
  for (const props of [null, [1], "x"]) {
    assert.deepEqual((await commandCase("/compact", props)).sent.forwardedProps,
      { spe_command: { name: "compact", focus: null } }, JSON.stringify(props));
    assert.deepEqual((await commandCase("hello", props)).sent.forwardedProps, props, JSON.stringify(props));
  }
});

test("decision 33: a command run sends the client a snapshot of the path right after RUN_STARTED", async () => {
  const { out, branch } = await commandCase("/compact");
  assert.deepEqual(types(out), [EventType.RUN_STARTED, EventType.MESSAGES_SNAPSHOT, EventType.RUN_FINISHED]);
  assert.deepEqual((out.events[1] as unknown as { messages: Message[] }).messages.map(view), branch.map(view));
});

test("the test agent answers a command with a manual marker carrying the focus", async () => {
  const { journals, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "hello"), agent());
    const branch = branchOfTip((await journals.load(id))!);
    const out = await drive(recorder, input(id, "/compact keep the canary paths", branch), agent());
    assert.equal(types(out).at(-1), EventType.RUN_FINISHED);
    assert.deepEqual(server.requests[1].body.forwardedProps, { spe_command: { name: "compact", focus: "keep the canary paths" } });
    const marker = branchOfTip((await journals.load(id))!).at(-1)!;
    assert.ok(marker.id.startsWith("spe-compaction-manual-"));
    assert.match(String(marker.content), /keep the canary paths/);
  } finally {
    await server.close();
  }
});
```

Run: `npm test`. Expected: FAIL (`command.ts` missing).

- [ ] **Step 2: Write `lib/command.ts`.**

```ts
// The chat's one command (spec §15, *What counts as a command*): a run whose only new message is a user message
// whose string content, trimmed, is /compact or /compact followed by whitespace and a focus. Case matters; there
// is no escape. Browser-safe: no Node imports.
import type { Message } from "@ag-ui/client";

export type Command = { name: "compact"; focus: string | null };
export type CommandField = Command & { message_id: string };

const COMPACT = /^\/compact(?:\s+([\s\S]*))?$/;

export function parseCommand(content: unknown): Command | null {
  if (typeof content !== "string") return null;
  const match = COMPACT.exec(content.trim());
  if (!match) return null;
  const focus = (match[1] ?? "").trim();
  return { name: "compact", focus: focus === "" ? null : focus };
}

export function commandOf(newMessages: Message[]): CommandField | null {
  if (newMessages.length !== 1 || newMessages[0].role !== "user") return null;
  const command = parseCommand(newMessages[0].content);
  return command && { ...command, message_id: newMessages[0].id };
}

export function sameCommand(a: Command, b: Command): boolean {
  return a.name === b.name && a.focus === b.focus;
}
```

- [ ] **Step 3: `lib/journal.ts`.** `RunStartLine` gains `command?: CommandField` (import the type from
`./command.ts`); `isLine`'s `run_start` case also requires `v.command === undefined || (isObject(v.command) &&
v.command.name === "compact" && (v.command.focus === null || isString(v.command.focus)) &&
isString(v.command.message_id))`. Add a `journal.test.ts` case: a `run_start` with a malformed `command` is
skipped, a well-formed one parses with it.

- [ ] **Step 4: `lib/recorder.ts`.** `Admission`'s admitted case gains `command: CommandField | null`. In
`admit`, right after `classify`: `const command = commandOf(classification.newMessages);`. `run_start` gets
`messages: command ? [] : classification.newMessages` and `...(command ? { command } : {})`; the
`NO_NEW_MESSAGE` refusal becomes `if (!command && classification.newMessages.length === 0)` (task 4 adds the
command's own refusals in this place). Return `{ refused: null, classification, command }`. In `run`:

```ts
const { classification: { path, newMessages, ignored }, command } = admission;
const messages: Message[] = command ? path : [...path, ...newMessages];
let snapshotDue = ignored.length > 0 || command !== null; // decisions 6 and 33
...
inner = this.runNext({ ...input, messages, forwardedProps: forwardedFor(input.forwardedProps, command) }, next)
```

and, at module level:

```ts
// spe_command is chat-ui's to set (spec §15, *The run route*, step 5): a client's is removed on every run, so
// only a typed /compact makes a command run. forwardedProps that is not a plain object is sent as sent on a
// plain run, and replaced by one holding only the command on a command run (plan ruling 4).
function forwardedFor(sent: unknown, command: Command | null): unknown {
  const spe_command = command && { name: command.name, focus: command.focus };
  if (typeof sent !== "object" || sent === null || Array.isArray(sent)) return spe_command ? { spe_command } : sent;
  const { spe_command: _client, ...rest } = sent as Record<string, unknown>;
  return spe_command ? { ...rest, spe_command } : rest;
}
```

Update the file's header comment: a command run is sent the path and `spe_command`, and always gets a snapshot.

- [ ] **Step 5: `lib/test-agent.ts`.** Add to the header's list: "`forwardedProps.spe_command`: RUN_STARTED, a
manual marker (id `spe-compaction-manual-<runId>`, its text naming the focus), RUN_FINISHED; a focus containing
`hang` stops after RUN_STARTED until the client goes away, one containing `error` sends RUN_ERROR". Right after
`res.writeHead(200, …)` and `send`/`ids` are defined:

```ts
const command = body.forwardedProps?.spe_command;
if (command) {
  send({ type: "RUN_STARTED", ...ids });
  const focus = String(command.focus ?? "");
  if (focus.includes("hang")) return; // the client's abort or close ends it
  if (focus.includes("error")) {
    send({ type: "RUN_ERROR", message: "scripted failure" });
    res.end();
    return;
  }
  const markerId = `spe-compaction-manual-${body.runId}`;
  send({ type: "TEXT_MESSAGE_START", messageId: markerId, role: "assistant" });
  send({ type: "TEXT_MESSAGE_CONTENT", messageId: markerId, delta: `SUMMARY on request. Focus: ${command.focus ?? "(none)"}` });
  send({ type: "TEXT_MESSAGE_END", messageId: markerId });
  send({ type: "RUN_FINISHED", ...ids });
  res.end();
  return;
}
```

Note: the `compact` keyword stays a substring match on the last user message, so a plain message such as
`/compacted` also makes the test agent send an automatic marker; a test of such a text through the test agent
expects that marker (the tests above use `Scripted` instead).

- [ ] **Step 6: Run the tests.** `npm test && npm run build`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add lib/command.ts lib/command.test.ts lib/journal.ts lib/journal.test.ts lib/recorder.ts lib/recorder.test.ts lib/test-agent.ts
git commit -s -m "chat-ui: journal /compact as a command and send the agent spe_command"
```

---

### Task 2: a command's message is known, never on the path

**Decisions:** 32; ruling 3; Review Focus 2 and 4.

**Files:**
- Modify: `lib/rebuild.ts`, `lib/anchor.ts`
- Test: `lib/rebuild.test.ts`, `lib/anchor.test.ts`

**Interfaces:**
- Consumes: task 1's `CommandField`, `parseCommand`, `sameCommand`.
- Produces: `Conversation.commands: Map<string, { run_id: string } & Command>` (by the command message's id);
  `RunView.command: CommandField | null`.

- [ ] **Step 1: Write the failing tests.** In `lib/anchor.test.ts`:

```ts
// A command run (spec §15): run_start with no message and a command; completed with a manual marker, or refused.
const compactRun = (id: string, anchor: string, messageId: string, focus: string | null = null): Line[] => [
  { type: "run_start", at: AT, run_id: id, anchor, messages: [], ignored: [], request, source: "chat",
    command: { name: "compact", focus, message_id: messageId } },
  ev(id, { type: EventType.RUN_STARTED, threadId: ID, runId: id }),
  ...text(id, `spe-compaction-manual-${id}`, "SUMMARY"),
  ev(id, { type: EventType.RUN_FINISHED, threadId: ID, runId: id }),
  { type: "run_end", at: AT, run_id: id, status: "completed", error: null },
];
const refusedCompact = (id: string, anchor: string, messageId: string, focus: string | null = null): Line[] => [
  { type: "run_start", at: AT, run_id: id, anchor, messages: [], ignored: [], request, source: "chat",
    command: { name: "compact", focus, message_id: messageId } },
  { type: "run_end", at: AT, run_id: id, status: "refused", error: "Nothing to compact yet." },
];

test("decision 32: a command message sent back unchanged ignores nothing and is never the anchor", async () => {
  const conv = await journal(r1(), r2(), r3(), refusedCompact("k1", "a3", "cmd1", "keep x"));
  for (const content of ["/compact keep x", "  /compact   keep x "]) { // ruling 3: parsed, not raw, text
    const c = classify(conv, [...branch(conv), user("cmd1", content), user("u4", "next")]);
    assert.equal(c.anchor, "a3", content);
    assert.deepEqual(ids(c.newMessages), ["u4"], content);
    assert.deepEqual(c.ignored, [], content);
    assert.ok(!ids(c.path).includes("cmd1"), content);
  }
});

test("decision 32: a command message sent back changed is edited", async () => {
  const conv = await journal(r1(), r2(), r3(), refusedCompact("k1", "a3", "cmd1", "keep x"));
  for (const changed of [user("cmd1", "/compact keep y"), user("cmd1", "/compact"), user("cmd1", "hello"),
                         assistant("cmd1", "/compact keep x")]) {
    const c = classify(conv, [...branch(conv), changed, user("u4", "next")]);
    assert.deepEqual(kinds(c), ["edited"], JSON.stringify(changed));
    assert.deepEqual(ids(c.newMessages), ["u4"]);
  }
});

test("decision 32: after a completed command the path ends in its marker, without the command", async () => {
  const conv = await journal(r1(), r2(), r3(), compactRun("k1", "a3", "cmd1"));
  const c = classify(conv, [...branch(conv), conv.nodes.get("spe-compaction-manual-k1")!.message, user("u4", "next")]);
  assert.equal(c.anchor, "spe-compaction-manual-k1");
  assert.deepEqual(ids(c.path).slice(-2), ["a3", "spe-compaction-manual-k1"]);
  assert.deepEqual(c.ignored, []);
});

test("Review Focus 2: kept command bubbles are known, not new", async () => {
  const conv = await journal(r1(), r2(), r3(), refusedCompact("k1", "a3", "cmd1"), refusedCompact("k2", "a3", "cmd2"));
  const kept = [...branch(conv), user("cmd1", "/compact"), user("cmd2", "/compact")];
  const third = classify(conv, [...kept, user("cmd3", "/compact")]);
  assert.deepEqual([third.anchor, ids(third.newMessages), third.ignored], ["a3", ["cmd3"], []]);
  const plain = classify(conv, [...kept, user("u4", "next")]);
  assert.deepEqual([plain.anchor, ids(plain.newMessages), plain.ignored], ["a3", ["u4"], []]);
});

test("Review Focus 4: compact after a stopped run moves the anchor back; no dangling call on the path", async () => {
  const stopped: Line[] = [
    { type: "run_start", at: AT, run_id: "r4", anchor: "a3", messages: [user("u4", "list more")], ignored: [], request, source: "chat" },
    ev("r4", { type: EventType.RUN_STARTED, threadId: ID, runId: "r4" }),
    ev("r4", { type: EventType.TOOL_CALL_START, toolCallId: "call-4", toolCallName: "execute", parentMessageId: "c4" }),
    ev("r4", { type: EventType.TOOL_CALL_ARGS, toolCallId: "call-4", delta: '{"cmd":"ls"}' }),
    ev("r4", { type: EventType.TOOL_CALL_END, toolCallId: "call-4" }),
    { type: "run_end", at: AT, run_id: "r4", status: "cancelled", error: null },
  ];
  const conv = await journal(r1(), r2(), r3(), stopped);
  const client = [...branch(conv), conv.nodes.get("u4")!.message, conv.nodes.get("c4")!.message, user("cmd", "/compact")];
  const c = classify(conv, client);
  assert.equal(c.anchor, "u4");
  assert.deepEqual(ids(c.newMessages), ["cmd"]);
  assert.equal(ids(c.path).at(-1), "u4");
  assert.deepEqual(kinds(c), ["deleted"]); // c4, cut back as for any run
});
```

(Adapt `kinds` to the file's helper; the `stopped` run reuses the existing case at "a run cancelled or cut mid
tool call" if its shape fits.) In `lib/rebuild.test.ts`:

```ts
test("decision 32: a command run adds only its marker; its message id is a known command, never a node", async () => {
  const conv = await rebuild(ID, [
    created(), start("r1", null, [user("u1", "hello")]), ...reply("r1", "a1", "hi"), end("r1"),
    { ...start("k1", "a1", []), command: { name: "compact", focus: "keep x", message_id: "cmd1" } } as Line,
    ...reply("k1", "spe-compaction-manual-k1", "SUMMARY"), end("k1"),
  ]);
  assert.deepEqual(shape(branchOfTip(conv)), [["user", "u1", "hello"], ["assistant", "a1", "hi"],
    ["assistant", "spe-compaction-manual-k1", "SUMMARY"]]);
  assert.equal(conv.nodes.has("cmd1"), false);
  assert.deepEqual(conv.commands.get("cmd1"), { run_id: "k1", name: "compact", focus: "keep x" });
  assert.deepEqual(conv.runs[1].command, { name: "compact", focus: "keep x", message_id: "cmd1" });
  assert.equal(conv.runs[0].command, null);
  assert.equal(conv.first_user_text, "hello");
});
```

and in `lib/sessions.test.ts` (or `api.test.ts`, whichever holds `get`'s tests): after a command run journaled
through the recorder's helpers, `journals.get(id)!.messages` holds no message with the command's id.

Run: `npm test`. Expected: FAIL.

- [ ] **Step 2: `lib/rebuild.ts`.** `RunView` gains `command: CommandField | null`; `Conversation` gains
`commands: Map<string, { run_id: string } & Command>`, initialised empty. In the per-run loop: `command:
run.start.command ?? null` on the `RunView`, and `if (run.start.command) conv.commands.set(run.start.command.message_id,
{ run_id: run.start.run_id, name: run.start.command.name, focus: run.start.command.focus })` (the first run with
an id wins, as for nodes). A command run's `messages` is empty, so the loop already adds only what its events
add.

- [ ] **Step 3: `lib/anchor.ts`.** Before the `known(id)` branch of the client loop:

```ts
const command = id !== null && !known(id) ? conv?.commands.get(id) : undefined;
if (command) {
  // A command's message (spec §15, step 2): known for this purpose only, never the anchor, new or on the path.
  // Unchanged means a user message that parses to the same command (plan ruling 3).
  const parsed = message.role === "user" ? parseCommand(message.content) : null;
  if (!parsed || !sameCommand(parsed, command)) ignored.push({ kind: "edited", message });
  seen.add(id);
  continue;
}
```

The anchor loop needs no change (it looks only at `nodes`). Update the header comment: a command's message is
known, never the anchor.

- [ ] **Step 4: Run the tests.** `npm test && npm run build`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/rebuild.ts lib/anchor.ts lib/rebuild.test.ts lib/anchor.test.ts lib/sessions.test.ts
git commit -s -m "chat-ui: a /compact message is a known command, never on the path"
```

---

### Task 3: Playwright and the early output

**Decisions:** 33's Playwright half; *Early output*, `/compact`.

**Files:**
- Modify: `platform/dev/e2e/sessions.py`
- Create: `docs/superpowers/plans/2026-11-03-agui-compact-command/evidence/slice-2/` (screenshots, `run_start.json`)

- [ ] **Step 1: Write the scenario.** In `platform/dev/e2e/sessions.py`, a `check_compact_command(r)` beside
`check_compaction`, a `compact-command` entry in `LOCAL`, run by the `all` scenario after `check_compaction`
and on its own by `--scenario compact-command` (the `else` branch of `main` dispatches on the name):

```python
def check_compact_command(r: Run) -> None:
    """/compact with a focus (spec §15): the bubble is replaced by the divider, live and after a reload; the
    journal's run_start carries the command and no message."""
    page = r.page
    page.get_by_role("button", name="New chat").click()
    expect(page.locator(".spe-header-title")).to_have_text("New chat")
    r.send("first question", 1)
    r.send("second question", 2)
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill("/compact keep the canary paths")
    box.press("Enter")
    divider = page.locator(".spe-compaction")
    expect(divider).to_have_count(1, timeout=20_000)
    expect(page.get_by_text("/compact keep the canary paths", exact=True)).to_have_count(0)
    r.shot("compact-command")
    sid = r.url_session()
    rec = r.wait_runs(sid, 3)
    starts = [x for x in read_journal((r.sessions / f"{sid}.jsonl").read_text()) if x["type"] == "run_start"]
    assert starts[-1]["messages"] == [] and starts[-1]["command"]["focus"] == "keep the canary paths", starts[-1]
    markers = [m for m in rec["messages"] if str(m.get("id") or "").startswith("spe-compaction-manual-")]
    assert len(markers) == 1 and "keep the canary paths" in markers[0]["content"], rec
    if r.shots:
        (r.shots / "run_start.json").write_text(json.dumps(starts[-1], indent=2) + "\n")
    page.reload()
    expect(page.locator(".spe-compaction")).to_have_count(1, timeout=10_000)
    expect(page.get_by_text("/compact keep the canary paths", exact=True)).to_have_count(0)
    r.shot("compact-command-reload")
    # Turn numbering restarts after a compaction (see check_compaction), so this answer is "Turn 1" again, as the
    # first question's still on the page is: r.send would hit a strict-mode double match. Count the answers.
    turn1 = page.get_by_text(re.compile(r"Turn 1: the command ran\."))
    before = turn1.count()
    box.fill("third question")
    box.press("Enter")
    expect(turn1).to_have_count(before + 1, timeout=20_000)
    expect(page.locator(".spe-compaction")).to_have_count(1)
    r.wait_runs(sid, 4)
    r.ok("compact-command: bubble gone, divider in place live and after a reload, run_start holds the command")
```

(`box` is still the textarea's locator after the reload: Playwright locators resolve lazily. Check `summary()`'s keys and `send`'s turn text against #25's version of the file; the reply text after a
compaction comes from slice 1's `fake_agent.py`.)

- [ ] **Step 2: Run it.** `(npm ci && npm run build)` here, then from the repository root
`uv run --with playwright python platform/dev/e2e/sessions.py --scenario compact-command --shots docs/superpowers/plans/2026-11-03-agui-compact-command/evidence/slice-2`
and `--scenario all` once. Expected: `ok - compact-command: …`, and every other scenario still ok.

- [ ] **Step 3: Commit and post the early output.**

```bash
git add platform/dev/e2e/sessions.py docs/superpowers/plans/2026-11-03-agui-compact-command/evidence/slice-2/
git commit -s -m "e2e: /compact replaces its bubble with the divider, live and after a reload"
git push
```

On the PR, one comment: the two screenshots (linked from the pushed branch), the `run_start` line, and the
question "Does a `/compact` that leaves no bubble, only the divider, read clearly (decision 33)? A no turns it
into a 'Compaction requested' line." Continue with task 4 without waiting; a "no" before the merge is a
clarification and the change in this PR.

---

### Task 4: the two refusals and a marker cut short

**Decisions:** 34, 37; ruling 6; Review Focus 3.

**Files:**
- Modify: `lib/recorder.ts`, `lib/reconcile.ts`, `lib/rebuild.ts`
- Test: `lib/recorder.test.ts`, `lib/reconcile.test.ts`, `lib/rebuild.test.ts`

- [ ] **Step 1: Write the failing tests.** In `lib/recorder.test.ts`'s `/compact` section:

```ts
const NOTHING = "Nothing to compact yet.";
const TOO_LONG = "The focus after /compact is too long (1000 characters at most).";

test("decision 34: /compact as a new session's first run is refused, journaled, and leaves no session", async () => {
  const { journals, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    const out = await drive(recorder, input(id, "/compact"), agent());
    assert.deepEqual([types(out), message(out, 1)], [[EventType.RUN_STARTED, EventType.RUN_ERROR], NOTHING]);
    assert.equal(server.requests.length, 0);
    const all = await lines(journals, id);
    assert.deepEqual(all.map((l) => l.type), ["created", "run_start", "run_end"]);
    assert.deepEqual([(all[2] as RunEndLine).status, (all[2] as RunEndLine).error], ["refused", NOTHING]);
    assert.equal((await journals.list()).some((s) => s.id === id), false);
    assert.equal(await journals.get(id), null); // GET /api/sessions/{id}: 404
  } finally {
    await server.close();
  }
});

test("decision 34: a session ending in a marker refuses /compact; one more message and it compacts again", async () => {
  const { journals, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "hello"), agent());
    const history = async () => branchOfTip((await journals.load(id))!);
    await drive(recorder, input(id, "/compact", await history()), agent());
    const again = await drive(recorder, input(id, "/compact", await history()), agent());
    assert.equal(message(again, 1), NOTHING);
    assert.equal(server.requests.length, 2);
    await drive(recorder, input(id, "more", await history()), agent());
    assert.equal(types(await drive(recorder, input(id, "/compact", await history()), agent())).at(-1), EventType.RUN_FINISHED);
  } finally {
    await server.close();
  }
});

test("Review Focus 3: the focus length is counted in code points", async () => {
  const cases: [string, boolean][] = [["x".repeat(1000), true], ["x".repeat(1001), false], ["🧪".repeat(1000), true]];
  for (const [focus, admitted] of cases) {
    const { start, out, sent } = await commandCase(`/compact ${focus}`);
    assert.equal(start.command?.focus, focus);
    assert.equal(sent !== undefined, admitted, `${[...focus].length} code points`);
    if (!admitted) assert.equal(message(out, 1), TOO_LONG);
  }
});

test("decision 37: a command run stopped during its summary request: cancelled, no marker", async () => {
  const { journals, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "hello"), agent());
    const branch = branchOfTip((await journals.load(id))!);
    await drive(recorder, input(id, "/compact hang", branch), agent(), (e) => e.type === EventType.MESSAGES_SNAPSHOT);
    await settled(id);
    assert.equal(ofType(await lines(journals, id), "run_end").at(-1)!.status, "cancelled");
    assert.equal(ofType(await lines(journals, id), "event").some((l) => String((l.event as { messageId?: string }).messageId).startsWith("spe-compaction-")), false);
    assert.deepEqual(branchOfTip((await journals.load(id))!).map(view), branch.map(view));
  } finally {
    await server.close();
  }
});
```

Update the `REFUSAL_MESSAGES` test to the eight messages. In `lib/rebuild.test.ts`:

```ts
// A marker whose TEXT_MESSAGE_END never came (spec §15, *A marker cut short*): automatic or manual, any status.
for (const [name, tail] of [["run_end cancelled", [end("r2", "cancelled")]], ["no run_end", []]] as const) {
  for (const markerId of ["spe-compaction-r2", "spe-compaction-manual-r2"]) {
    test(`decision 37: a marker cut short (${name}, ${markerId}) is not on the path`, async () => {
      const conv = await rebuild(ID, [
        created(), start("r1", null, [user("u1", "hello")]), ...reply("r1", "a1", "hi"), end("r1"),
        start("r2", "a1", [user("u2", "go on")]),
        ev("r2", { type: EventType.RUN_STARTED, threadId: ID, runId: "r2" }),
        ev("r2", { type: EventType.TEXT_MESSAGE_START, messageId: markerId, role: "assistant" }),
        ev("r2", { type: EventType.TEXT_MESSAGE_CONTENT, messageId: markerId, delta: "SUMMARY so f" }),
        ...tail,
      ]);
      assert.equal(conv.nodes.has(markerId), false);
      assert.deepEqual(conv.runs[1].added, ["u2"]);
    });
  }
}
```

Run: `npm test`. Expected: FAIL.

- [ ] **Step 2: Refusals in `lib/recorder.ts`.** Constants beside the others, added to `REFUSAL_MESSAGES` and
copied into `lib/reconcile.ts`'s `REFUSED_RUN_MESSAGES` (same order):

```ts
const NOTHING_TO_COMPACT = "Nothing to compact yet.";
const FOCUS_TOO_LONG = "The focus after /compact is too long (1000 characters at most).";
const MAX_FOCUS = 1000; // code points (plan ruling 6)
```

In `admit`, in place of task 1's guarded `NO_NEW_MESSAGE` check:

```ts
if (command) {
  // Spec §15, step 4: nothing after the path's latest marker, or a focus too long. The agent backstops the first.
  const last = classification.path.at(-1);
  if (!last || isCompactionMarker(last)) return endHere("refused", NOTHING_TO_COMPACT); // import from ./compaction.ts
  if (command.focus !== null && [...command.focus].length > MAX_FOCUS) return endHere("refused", FOCUS_TOO_LONG);
} else if (classification.newMessages.length === 0) {
  return endHere("refused", NO_NEW_MESSAGE);
}
```

(`path` excludes activity messages, so a path ending in one is judged by the message before it.) Note: the agent
sends "Nothing to compact yet." itself as a backstop; `isRefusal` then matches a journaled `failed` run too, and
the browser fetches the list once instead of reconciling. Accepted: the run's `run_end` is written before the
`RUN_ERROR` is passed on.

- [ ] **Step 3: A marker cut short in `lib/rebuild.ts`.** In the per-run loop, before `added` is built:

```ts
// Spec §15, *A marker cut short*: a marker counts only once its TEXT_MESSAGE_END is journaled, so the agent is
// never sent a truncated summary as its cut point, whatever the run's status.
const ended = new Set(run.events.filter((e) => e.type === EventType.TEXT_MESSAGE_END)
  .map((e) => (e as { messageId?: string }).messageId));
const cutShort = new Set(run.events.filter((e) => e.type === EventType.TEXT_MESSAGE_START)
  .map((e) => (e as { messageId?: string }).messageId)
  .filter((mid): mid is string => typeof mid === "string" && mid.startsWith(MARKER_PREFIX) && !ended.has(mid)));
```

and skip a candidate whose id is in `cutShort` (beside the `pathIds` check). Import `EventType` from
`@ag-ui/client` and `MARKER_PREFIX` from `./compaction.ts`.

- [ ] **Step 4: Run the tests.** `npm test && npm run build`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/recorder.ts lib/reconcile.ts lib/rebuild.ts lib/recorder.test.ts lib/reconcile.test.ts lib/rebuild.test.ts
git commit -s -m "chat-ui: refuse /compact with nothing to compact or a long focus; drop a marker cut short"
```

---

### Task 5: the archive, the docs, de.NBI and the spec built

**Decisions:** 38, 39; the archive half of Review Focus 1; the proposed clarification *Slice 2*.

**Files:**
- Modify: `lib/export.ts`, `lib/export.test.ts`
- Create: `platform/dev/tests/fixtures/agui-record/00000000-0000-4000-8000-000000000006.jsonl`
- Regenerate: `platform/dev/tests/fixtures/agui-record/live.bundle.json`, `final.bundle.json`
- Modify: `platform/ansible/roles/run_archive/files/write_run.py`, `platform/dev/tests/test_write_run_agui.py`
- Modify: `README.md` (this package's), `docs/getting-started.md`
- Modify: `docs/specs/2026-10-15-agui-frontend-design/README.md` (status), `15-compact-command.md`, `clarifications.md`

- [ ] **Step 1: The fixture journal.** `…0006.jsonl`, hand-written in the other fixtures' style (`at` ten
milliseconds apart, a date after fixture 5's): run `r6-1` a user question and its reply, completed; run `r6-2`
`/compact` (no focus) anchored on that reply, its agent answering `RUN_STARTED` then `RUN_ERROR` "Compaction
is turned off on this instance.", `run_end` failed; run `r6-3` `/compact keep the ```` canary paths` anchored on
the reply, a manual marker `spe-compaction-manual-r6-3`, completed; run `r6-4` with anchor `null` and command
`/compact` (no focus), `run_end` refused "Nothing to compact yet." (a client that held no known id); run `r6-5`
a question anchored on the marker, completed. Title by its first user message.

- [ ] **Step 2: Write the failing tests.** In `lib/export.test.ts`:

```ts
test("decision 38: every command run's message carries spe_command, refused and failed ones too", () => {
  const c = chat(6);
  assert.deepEqual(msg(c, "spe-run-r6-2").spe_command, { name: "compact", focus: null });
  assert.deepEqual(msg(c, "spe-run-r6-3").spe_command, { name: "compact", focus: "keep the ```` canary paths" });
  assert.deepEqual(msg(c, "spe-run-r6-4").spe_command, { name: "compact", focus: null });
  assert.equal(msg(c, "spe-run-r6-1").spe_command, undefined);
  assert.equal(msg(c, "spe-run-r6-3").spe_run?.status, "completed");
  assert.deepEqual(msg(c, "spe-run-r6-3").output?.map((i) => i.id), ["spe-compaction-manual-r6-3"]);
});
```

(`chat(n)` and `msg` are the file's helpers.) In `platform/dev/tests/test_write_run_agui.py`: add session 6 to
`NAMES`, change the `rendered` fixture's line to "6 sessions (1 hidden, 1 deleted)" (and the index test's rows).
In `lib/export.test.ts`, the same count moves too: the live chats' `[1, 2, 3, 4, 5].map(J)` becomes
`[1, 2, 3, 4, 5, 6].map(J)`, and the CLI's `"5 sessions (1 hidden, 1 deleted), final archive\n"` becomes
`"6 sessions …"`. Then:

```python
def test_a_manual_compaction_says_the_participant_asked(rendered):
    md = chat(rendered, MANUAL)
    section = md[md.index("## Compacted"):]
    assert section.startswith("## Compacted\n\n*Requested by the participant (`/compact`)*\n\n")
    assert "`````\nkeep the ```` canary paths\n`````" in section  # Review Focus 1: the fence outlasts four
    assert md.count("## Compacted") == 1


def test_a_failed_or_refused_command_shows_the_command_beside_its_status(rendered):
    md = chat(rendered, MANUAL)
    # one line per command run: r6-2 (failed), r6-3 (its "Compacted" section), r6-4 (refused)
    assert md.count("*Requested by the participant (`/compact`)*") == 3
    failed = md.index("Compaction is turned off on this instance.")
    assert "*Requested by the participant (`/compact`)*" in md[failed:md.index("## Compacted")]  # r6-2's own


def test_the_index_counts_manual_compactions(rendered):
    row = next(l for l in (rendered / "index.md").read_text().splitlines() if NAMES[MANUAL] in l)
    assert "| 1 |" in row  # this session's compactions column
```

(Adapt the asserts to how `render_status` prints a status; `MANUAL` is the new session's id constant.)

Run: `npm test` and `uv run --with pytest pytest platform/dev/tests -q`. Expected: FAIL.

- [ ] **Step 3: `lib/export.ts`.** `ExportedMessage` gains `spe_command?: Command`; the run message `put` in
`toOpenWebUIChat` gains `...(run.command ? { spe_command: { name: run.command.name, focus: run.command.focus } } : {})`.
Update the header comment's list of `spe_` fields. Regenerate: `UPDATE_FIXTURES=1 npm test`, then read the
diff of the two bundles: only session 6 and the `tags` list (if it changed) may differ.

- [ ] **Step 4: `write_run.py`.**

```python
def render_command(cmd):
    """A command run's line (spec §15, *The archive*): who asked, and the focus fenced."""
    if not isinstance(cmd, dict) or cmd.get("name") != "compact":
        return ""
    out = "*Requested by the participant (`/compact`)*"
    focus = cmd.get("focus")
    if isinstance(focus, str) and focus:
        out += "\n\n" + fence(focus)
    return out
```

In `render_output(m)`: `cmd = render_command(m.get("spe_command"))`; the marker's section becomes
`"## Compacted\n\n" + (cmd + "\n\n" if cmd else "") + "From here the model saw …" + fence(...)`, then `cmd = ""`;
after the loop, a `cmd` still set (a refused, failed or cancelled command run, no marker) goes first:
`out.insert(0, cmd)`, so it follows the status line `render_agui_message` prints. Update the module docstring's
list of what an AG-UI bundle renders.

- [ ] **Step 5: Run the tests.** `npm test && npm run build` and `uv run --with pytest pytest platform/dev/tests -q`.
Expected: PASS.

- [ ] **Step 6: Docs.** This package's `README.md`, *Sessions*: the `lib/recorder.ts` bullet gains "A run whose
only new message is `/compact` or `/compact <focus>` is a command (`lib/command.ts`): journaled as
`run_start.command` with no message, sent the history with `forwardedProps.spe_command`, refused when there is
nothing to compact or the focus is over 1000 characters; the browser always gets the snapshot." The journal
paragraph names `run_start`'s `command`. `docs/getting-started.md`, where it describes using the chat: "Type
`/compact`, or `/compact <what to keep>`, to compact the conversation now; the divider replaces it." No link to
a fork-only file in either (upstream-clean).

- [ ] **Step 7: Commit**

```bash
git add lib/export.ts lib/export.test.ts platform/dev/tests/fixtures/agui-record/ \
  platform/ansible/roles/run_archive/files/write_run.py platform/dev/tests/test_write_run_agui.py \
  README.md docs/getting-started.md
git commit -s -m "Archive: a manual compaction says the participant asked; /compact documented"
```

(Run `git add` from the repository root with the full paths.)

- [ ] **Step 8: Decision 39 (paid: ask first).** One PR comment: "Decision 39 needs a de.NBI instance on
`qwen3.8-27b`, deployed from this worktree (model calls on de.NBI and an instance created and destroyed). OK to
run it?" Then `next-session.sh --end --blocked <PR>` (*Global Constraints*, *Model calls*); the session that
resumes on the answer runs it. The check: create the instance from the main checkout with `-e
spe_agui_source_dir=<worktree>/platform/agui` (`AGENTS.md`, *Worktrees and deploying*); in a session of several
turns with tool output, `/compact keep the canary paths` shows the divider with a summary that names them; a
question that needs no tool, asked just before the command and again just after, has fewer
`usage.input_tokens` in the run log after it; the journal has the command and the archive the manual compaction.
Destroy the instance. Put the run log lines, the archive's section and a screenshot in `evidence/slice-2/`.

- [ ] **Step 9: The spec built.** The spec README's status line: `/compact` (§15, decisions 31–39) built.
Clarification (the next free number, status `folded`): ruling 3 into §15 *The run route*, step 2 (a resent
command is unchanged when it parses to the same command and focus), ruling 4 into step 5 (non-object
`forwardedProps`), and anything tasks 1–5 changed. Commit:

```bash
git add docs/specs/2026-10-15-agui-frontend-design/ docs/superpowers/plans/2026-11-03-agui-compact-command/evidence/slice-2/
git commit -s -m "Spec: /compact built (clarification N: rulings 3 and 4)"
```

Then the slice's PR (`… (2/2)`), the local review round, the merge, the README's slice row `merged #<n>`,
`AGENTS.md`'s `/compact` track line removed, and `next-session.sh --end`.
