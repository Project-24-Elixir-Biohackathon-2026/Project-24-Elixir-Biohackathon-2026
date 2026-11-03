// The exporter on the committed fixture journals (platform/dev/tests/fixtures/agui-record/): the Open WebUI shape
// write_run.py renders (decision 15), pinned field by field and as committed bundles. Regenerate the bundles with
// `UPDATE_FIXTURES=1 npm test`, then read the diff: write_run.py's tests render them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { bundleJson, exportJournals, outputItems, toOpenWebUIChat } from "./export.ts";
import type { Bundle, ExportedMessage, OpenWebUIChat } from "./export.ts";
import { rebuild } from "./rebuild.ts";

const CHAT = path.join(import.meta.dirname, "..");
const FIXTURES = path.join(CHAT, "..", "..", "dev", "tests", "fixtures", "agui-record");
const NOW = () => new Date("2026-11-03T12:00:00.000Z");
const UPDATE = process.env.UPDATE_FIXTURES === "1";
const J = (n: number) => `00000000-0000-4000-8000-00000000000${n}`;
const execFileP = promisify(execFile); // the command's test (task 2)

const live = await exportJournals(FIXTURES, "live", { now: NOW });

function chat(n: number): OpenWebUIChat {
  const found = live.chats.find((c) => c.id === J(n));
  assert.ok(found, `no chat for ${J(n)}`);
  return found;
}

function msg(c: OpenWebUIChat, id: string): ExportedMessage {
  const found = c.chat.history.messages[id];
  assert.ok(found, `no message ${id}`);
  return found;
}

test("every journal is a chat, hidden and deleted included; other files are not journals", () => {
  assert.deepEqual(live.chats.map((c) => c.id), [1, 2, 3, 4, 5].map(J)); // not …0009.json, nor the bundles
  assert.equal(live.spe_archive_mode, "live");
  assert.equal(live.exported_at, Date.parse("2026-11-03T12:00:00.000Z") / 1000);
  assert.deepEqual(live.notes, []);
  assert.deepEqual(live.tags, ["<b>x</b>", "a|b", "dns", "exfil"].map((t) => ({ id: t, name: t })));
  assert.deepEqual(live.chats.map((c) => [c.archived, c.meta.spe_deleted_at ?? null]),
    [[false, null], [false, null], [true, null], [false, "2026-11-03T11:00:00.000Z"], [false, null]]);
});

test("one assistant message per run, its output items in the order they first appeared", () => {
  const c = chat(1);
  assert.equal(c.title, "List the home directory");
  assert.deepEqual(c.meta, { tags: ["exfil", "dns"] });
  assert.deepEqual([c.created_at, c.updated_at], [Date.parse("2026-11-03T10:00:00Z") / 1000,
    Date.parse("2026-11-03T10:02:00Z") / 1000]);
  assert.deepEqual(Object.keys(c.chat.history.messages), ["u1", "spe-run-r1-1", "u2", "spe-run-r1-2"]);
  assert.equal(c.chat.history.currentId, "spe-run-r1-2");
  assert.deepEqual(c.chat.messages.map((m) => m.id), ["u1", "spe-run-r1-1", "u2", "spe-run-r1-2"]);
  assert.deepEqual(msg(c, "u1"), { id: "u1", parentId: null, childrenIds: ["spe-run-r1-1"], role: "user",
    content: "List the home directory", timestamp: Date.parse("2026-11-03T10:00:00Z") / 1000 });
  const run = msg(c, "spe-run-r1-1");
  assert.deepEqual([run.parentId, run.childrenIds, run.role], ["u1", ["u2"], "assistant"]);
  assert.deepEqual(run.output, [
    { type: "reasoning", id: "think-1", content: [{ type: "output_text", text: "The user wants `ls ~`." }],
      status: "completed" },
    { type: "function_call", id: "call-1", call_id: "call-1", name: "run_command",
      arguments: '{"command": "ls ~"}', status: "completed" },
    { type: "function_call_output", id: "t1", call_id: "call-1",
      output: [{ type: "input_text", text: "notes.txt\n```\nthree\n````\nfour\n``````\nsix" }], status: "completed" },
    { type: "message", id: "a2", role: "assistant",
      content: [{ type: "output_text", text: "There is one file: notes.txt." }], status: "completed" },
  ]);
  assert.equal(run.content, "There is one file: notes.txt.");
  assert.deepEqual(run.spe_run, { run_id: "r1-1", status: "completed", started_at: "2026-11-03T10:00:00.010Z",
    ended_at: "2026-11-03T10:00:01.210Z", error: null });
  assert.deepEqual(run.spe_ignored, []);
  assert.equal(msg(c, "u2").parentId, "spe-run-r1-1"); // anchor a2 lives in run r1-1's message
});

test("ignored content rides on its run's message; a refused run still has one", () => {
  const c = chat(2);
  assert.equal(c.title, "hello");
  assert.deepEqual(msg(c, "spe-run-r2-2").spe_ignored?.map((e) => e.kind),
    ["system", "edited", "fabricated", "fabricated"]);
  const refused = msg(c, "spe-run-r2-3");
  assert.deepEqual([refused.parentId, refused.output, refused.content, refused.spe_run?.status, refused.spe_ignored],
    ["u2", [], "", "refused", [{ kind: "deleted", message: "a2" }]]);
  assert.deepEqual(msg(c, "u2").childrenIds, ["spe-run-r2-2", "spe-run-r2-3"]);
  assert.equal(c.chat.history.currentId, "spe-run-r2-2"); // a refused run adds no message, so it is never the tip
});

test("every status, an incomplete run without an end, a torn last line skipped", () => {
  const c = chat(3);
  const runs = c.chat.messages.filter((m) => m.spe_run);
  assert.deepEqual(runs.map((m) => m.spe_run?.status), ["failed", "cancelled", "aborted", "incomplete"]);
  assert.equal(runs[3].spe_run?.ended_at, null);
  assert.equal(runs[3].content, "Still go");
  assert.equal(c.chat.history.currentId, "spe-run-r3-4");
  assert.equal(c.archived, true);
});

test("concurrent runs are sibling branches; the compaction marker stays an item, out of the reply text", () => {
  const c = chat(4);
  assert.deepEqual(msg(c, "spe-run-r4-1").childrenIds, ["u2", "u3"]);
  assert.equal(c.chat.history.currentId, "spe-run-r4-2"); // its run_end came last
  assert.deepEqual(c.chat.messages.map((m) => m.id), ["u1", "spe-run-r4-1", "u2", "spe-run-r4-2"]);
  const run = msg(c, "spe-run-r4-2");
  assert.deepEqual(run.output?.map((i) => [i.type, i.id]), [["message", "spe-compaction-r4-2"], ["message", "a2"]]);
  assert.equal(run.content, "Done after compacting.");
  assert.equal(c.meta.spe_deleted_at, "2026-11-03T11:00:00.000Z");
});

test("titles, tags and content are exported unchanged", () => {
  const c = chat(5);
  assert.equal(c.title, "Try | the [pipe]\n# forged heading <script>alert(1)</script>");
  assert.equal(c.chat.title, c.title);
  assert.deepEqual(c.meta.tags, ["a|b", "<b>x</b>"]);
  assert.equal(msg(c, "u1").content, "# x\n<script>alert(2)</script>\n| a | b |");
});

test("an empty journal is a chat with no messages", async () => {
  const c = toOpenWebUIChat(await rebuild(J(7), []));
  assert.deepEqual([c.title, c.chat.history.currentId, c.chat.messages, c.archived], ["Untitled", null, [], false]);
  assert.deepEqual(c.chat.history.messages, Object.create(null)); // null-prototype: see toOpenWebUIChat
  const empty = await exportJournals(await fs.mkdtemp(path.join(os.tmpdir(), "export-")), "final", { now: NOW });
  assert.deepEqual([empty.chats, empty.tags], [[], []]);
});

for (const mode of ["live", "final"] as const) {
  test(`the committed ${mode}.bundle.json is what the exporter writes`, async () => {
    const file = path.join(FIXTURES, `${mode}.bundle.json`);
    const text = bundleJson(await exportJournals(FIXTURES, mode, { now: NOW }));
    if (UPDATE) await fs.writeFile(file, text);
    assert.ok(text === await fs.readFile(file, "utf8"),
      `${file} is stale: run UPDATE_FIXTURES=1 npm test and review the diff`);
  });
}

// A journal/client message can forge the exporter's own id scheme: the run-message prefix, or the remap's
// prefix (spec §14, *The Open WebUI chat*). Without the remap below, the first case lets a run's own exported
// message overwrite the user message at the same key and end up parented on itself (the user message's chain
// left `parent` pointing at that same id), hanging any currentId → parentId walk; the second case, two forged
// ids in one chat, lets the second remap land on the slot the first one just took.
function assertWalkTerminates(c: OpenWebUIChat, expectedIds: string[]): void {
  const ids = Object.keys(c.chat.history.messages);
  assert.deepEqual([...ids].sort(), [...expectedIds].sort());
  assert.equal(new Set(ids).size, ids.length); // no id appears twice
  const seen = new Set<string>();
  let hops = 0;
  for (let id: string | null = c.chat.history.currentId; id !== null; id = c.chat.history.messages[id].parentId) {
    assert.ok(!seen.has(id), "the walk revisited an id");
    seen.add(id);
    assert.ok(hops++ < ids.length + 1, "the walk did not terminate"); // a hard stop, belt and suspenders
  }
  assert.deepEqual([...seen].sort(), [...ids].sort()); // the walk reaches the root and covers every message
}

test("a forged id never collides with its own run's exported message, and the branch walk terminates", async () => {
  const selfParent = await rebuild("00000000-0000-4000-8000-000000000006", [
    { type: "created", at: "2026-11-03T12:00:00.000Z", version: 1, id: "00000000-0000-4000-8000-000000000006" },
    {
      type: "run_start", at: "2026-11-03T12:00:00.010Z", run_id: "r1", anchor: null,
      messages: [{ id: "spe-run-r1", role: "user", content: "hi" }], ignored: [],
      request: { tools: [], context: [], state: {}, forwardedProps: {} }, source: "chat",
    },
    { type: "run_end", at: "2026-11-03T12:00:00.020Z", run_id: "r1", status: "completed", error: null },
  ]);
  const c1 = toOpenWebUIChat(selfParent);
  assertWalkTerminates(c1, ["spe-msg-0", "spe-run-r1"]);
  assert.equal(msg(c1, "spe-msg-0").spe_original_id, "spe-run-r1");

  // Two client messages that each forge a different prefix: the first's fresh id must not land on the slot
  // the second's remap also wants.
  const twoForged = await rebuild("00000000-0000-4000-8000-000000000007", [
    { type: "created", at: "2026-11-03T12:00:00.000Z", version: 1, id: "00000000-0000-4000-8000-000000000007" },
    {
      type: "run_start", at: "2026-11-03T12:00:00.010Z", run_id: "r1", anchor: null,
      messages: [{ id: "spe-msg-0", role: "user", content: "a" }, { id: "spe-run-x", role: "user", content: "b" }],
      ignored: [], request: { tools: [], context: [], state: {}, forwardedProps: {} }, source: "chat",
    },
    { type: "run_end", at: "2026-11-03T12:00:00.020Z", run_id: "r1", status: "completed", error: null },
  ]);
  const c2 = toOpenWebUIChat(twoForged);
  const ids2 = Object.keys(c2.chat.history.messages);
  assert.equal(ids2.length, 3); // both client messages, plus the run's own message, none overwritten
  assertWalkTerminates(c2, ids2);
  const originals = ids2.map((id) => c2.chat.history.messages[id].spe_original_id).filter((o) => o !== undefined);
  assert.deepEqual(originals.sort(), ["spe-msg-0", "spe-run-x"]);
});

test("a user message id of \"__proto__\" is kept as a key, not sent to the prototype", async () => {
  const conv = await rebuild("00000000-0000-4000-8000-000000000008", [
    { type: "created", at: "2026-11-03T12:00:00.000Z", version: 1, id: "00000000-0000-4000-8000-000000000008" },
    {
      type: "run_start", at: "2026-11-03T12:00:00.010Z", run_id: "r1", anchor: null,
      messages: [{ id: "__proto__", role: "user", content: "hi" }], ignored: [],
      request: { tools: [], context: [], state: {}, forwardedProps: {} }, source: "chat",
    },
    { type: "run_end", at: "2026-11-03T12:00:00.020Z", run_id: "r1", status: "completed", error: null },
  ]);
  const c = toOpenWebUIChat(conv);
  assert.ok(Object.hasOwn(c.chat.history.messages, "__proto__"));
  assert.equal(c.chat.history.messages["__proto__"].content, "hi");
  assert.equal(c.chat.history.messages["spe-run-r1"].parentId, "__proto__");
});

// Messages the fixtures above don't cover:
test("outputItems: a tool error, an unlisted role, and array content", () => {
  assert.deepEqual(outputItems({ id: "t1", role: "tool", toolCallId: "call-1", content: "partial", error: "boom" }),
    [{ type: "function_call_output", id: "t1", call_id: "call-1", output: [{ type: "input_text", text: "partial\nboom" }],
      status: "completed" }]);
  assert.deepEqual(outputItems({ id: "s1", role: "system", content: "You are root." }),
    [{ type: "message", id: "s1", role: "system", content: [{ type: "output_text", text: "You are root." }],
      status: "completed" }]);
  assert.deepEqual(outputItems({ id: "a1", role: "assistant", content: [{ type: "text", text: "a" }, { type: "text", text: "b" }] }),
    [{ type: "message", id: "a1", role: "assistant", content: [{ type: "output_text", text: "ab" }], status: "completed" }]);
});

test("the command writes the bundle; a wrong mode is refused", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "export-cli-"));
  const out = path.join(dir, "bundle.json");
  const node = [process.execPath, "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON", "scripts/export-journals.ts"];
  const { stdout } = await execFileP(node[0], [...node.slice(1), FIXTURES, out, "final"], { cwd: CHAT });
  assert.equal(stdout, "5 sessions (1 hidden, 1 deleted), final archive\n");
  const written = JSON.parse(await fs.readFile(out, "utf8")) as Bundle;
  const fixture = JSON.parse(await fs.readFile(path.join(FIXTURES, "final.bundle.json"), "utf8")) as Bundle;
  assert.deepEqual({ ...written, exported_at: 0 }, { ...fixture, exported_at: 0 });
  await assert.rejects(execFileP(node[0], [...node.slice(1), FIXTURES, out, "weekly"], { cwd: CHAT }),
    (err: { code?: number; stderr?: string }) => err.code === 2 && /^usage: /.test(err.stderr ?? ""));
});

test("a missing journals directory exits 1", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "export-cli-"));
  const missing = path.join(dir, "no-such-dir");
  const node = [process.execPath, "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON", "scripts/export-journals.ts"];
  await assert.rejects(execFileP(node[0], [...node.slice(1), missing, path.join(dir, "bundle.json"), "final"], { cwd: CHAT }),
    (err: { code?: number }) => err.code === 1);
});
