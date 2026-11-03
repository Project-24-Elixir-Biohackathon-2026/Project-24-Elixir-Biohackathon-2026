// The journal store: ids, tags, titles, the index (one pass, updated on append, on globalThis), the list
// rules, metadata as meta lines, append-only journals, the earlier JSON format ignored.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { Message } from "@ag-ui/client";
import type { Clock, JournalFs } from "./journal.ts";
import {
  Journals, ValidationError, autoTitle, isSessionId, normaliseTags, parsePatch, shared,
} from "./sessions.ts";
import { seedRun } from "./test-journals.ts";

const T0 = new Date("2026-10-29T10:00:00.000Z");
const at = (seconds: number) => new Date(T0.getTime() + seconds * 1000);
const INDEX = Symbol.for("spe.sessions.index");

// A store whose clock the test moves: every line it writes is stamped `clock.t`.
async function tmpJournals(opts: { fs?: JournalFs } = {}) {
  const clock = { t: at(0) };
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "journals-"));
  return { journals: new Journals(dir, { ...opts, now: () => clock.t }), clock, dir };
}

const file = (dir: string, id: string) => path.join(dir, `${id}.jsonl`);
const restart = () => delete (globalThis as Record<symbol, unknown>)[INDEX];

function user(content: unknown): Message {
  return { id: randomUUID(), role: "user", content } as Message;
}

// A journal written as raw text: an earlier state, a torn line, or one the index never saw.
function raw(id: string, lines: object[]): string {
  return lines.map((l) => JSON.stringify(l)).join("\n") + "\n";
}

function runLines(id: string, when: string, text: string, added = true) {
  const run = randomUUID();
  return [
    { type: "run_start", at: when, run_id: run, anchor: null, messages: added ? [user(text)] : [], ignored: [],
      request: { tools: [], context: [], state: {}, forwardedProps: {} }, source: "chat" },
    { type: "run_end", at: when, run_id: run, status: added ? "completed" : "refused", error: null },
  ];
}

test("isSessionId accepts only canonical lower-case UUID v4", () => {
  assert.equal(isSessionId(randomUUID()), true);
  for (const bad of [
    "../x", "a/b", "", "6F1C0D2E-1234-4ABC-8DEF-0123456789AB", "6f1c0d2e-1234-1abc-8def-0123456789ab",
    "6f1c0d2e-1234-4abc-cdef-0123456789ab", "6f1c0d2e12344abc8def0123456789ab",
    `${randomUUID()}\n`, `${randomUUID()}.jsonl`, 42, null, undefined,
  ]) {
    assert.equal(isSessionId(bad), false, String(bad));
  }
});

test("the store refuses an invalid id before building a path", async () => {
  const { journals, dir } = await tmpJournals();
  await assert.rejects(journals.load("../x"), ValidationError);
  await assert.rejects(journals.append("a/b", { type: "meta", pinned: true }, "now"), ValidationError);
  await assert.rejects(journals.patch("../../etc/x", { pinned: true }), ValidationError);
  await assert.rejects(journals.softDelete("6F1C0D2E-1234-4ABC-8DEF-0123456789AB"), ValidationError);
  assert.deepEqual(await fs.readdir(dir), []);
});

test("tags are normalised or refused", () => {
  const cases: [unknown, string[]][] = [
    [[" Exfil ", "DNS", "exfil"], ["exfil", "dns"]],
    [["a.b_c-1"], ["a.b_c-1"]],
    [["x".repeat(32)], ["x".repeat(32)]],
    [Array.from({ length: 20 }, (_, i) => `t${i}`), Array.from({ length: 20 }, (_, i) => `t${i}`)],
    [[...Array.from({ length: 20 }, (_, i) => `t${i}`), "T0"], Array.from({ length: 20 }, (_, i) => `t${i}`)],
    [[], []],
  ];
  for (const [input, expected] of cases) assert.deepEqual(normaliseTags(input), expected);
  for (const bad of [
    "exfil", [""], ["   "], ["x".repeat(33)], ["has space"], ["ümlaut"], ["a/b"], [1], [null],
    Array.from({ length: 21 }, (_, i) => `t${i}`),
  ]) {
    assert.throws(() => normaliseTags(bad), ValidationError, JSON.stringify(bad));
  }
});

test("parsePatch takes title, tags, pinned and hidden only", () => {
  assert.deepEqual(parsePatch({ title: "  New\n title ", tags: ["A"], pinned: true, hidden: false }), {
    title: "New title", tags: ["a"], pinned: true, hidden: false,
  });
  for (const bad of [
    {}, { messages: [] }, { runs: [] }, { id: randomUUID() }, { deleted_at: null }, { title: 5 },
    { title: "" }, { title: "x".repeat(201) }, { pinned: "yes" }, { hidden: 1 }, { tags: "a" },
    null, [], "title", 3,
  ]) {
    assert.throws(() => parsePatch(bad), ValidationError, JSON.stringify(bad));
  }
  assert.equal(parsePatch({ title: "😀".repeat(200) }).title, "😀".repeat(200)); // 200 code points
});

test("autoTitle: first user text, whitespace collapsed, 60 code points, Untitled", () => {
  assert.equal(autoTitle([user("  List\n\tthe   home directory ")]), "List the home directory");
  assert.equal(autoTitle([user("x".repeat(80))]), "x".repeat(60));
  assert.equal(autoTitle([user([{ type: "text", text: "from parts" }])]), "from parts");
  assert.equal(autoTitle([]), "Untitled");
  assert.equal(autoTitle([user("   ")]), "Untitled");
});

test("autoTitle keeps an astral character at the cut whole", () => {
  const title = autoTitle([user("a".repeat(59) + "😀" + "tail")]);
  assert.equal(title, "a".repeat(59) + "😀");
  assert.equal(Array.from(title).length, 60);
  assert.equal(title.isWellFormed(), true);
});

test("a run makes a listed session: auto title, created_at, updated_at and last_run_at from its lines", async () => {
  const { journals, clock } = await tmpJournals();
  clock.t = at(1);
  const { id } = await seedRun(journals, "  List the\nhome directory ");
  const [meta] = await journals.list();
  assert.deepEqual(Object.keys(meta).sort(),
    ["created_at", "hidden", "id", "last_run_at", "pinned", "tags", "title", "updated_at"]);
  assert.deepEqual(meta, {
    id, title: "List the home directory", tags: [], pinned: false, hidden: false,
    created_at: at(1).toISOString(), updated_at: at(1).toISOString(), last_run_at: at(1).toISOString(),
  });
});

test("get(): the tip's branch and the metadata without last_run_at; null when missing", async () => {
  const { journals } = await tmpJournals();
  const first = await seedRun(journals, "first question");
  await seedRun(journals, "second question", { id: first.id, anchor: first.replyId });
  const view = await journals.get(first.id);
  assert.ok(view);
  assert.deepEqual(Object.keys(view).sort(),
    ["created_at", "hidden", "id", "messages", "pinned", "tags", "title", "updated_at"]);
  assert.deepEqual(view.messages.map((m) => [m.role, m.content]), [
    ["user", "first question"], ["assistant", "echo: first question"],
    ["user", "second question"], ["assistant", "echo: second question"],
  ]);
  assert.equal(await journals.get(randomUUID()), null);
});

test("a title the user set survives later runs (decision 22)", async () => {
  const { journals } = await tmpJournals();
  const first = await seedRun(journals, "first question");
  await journals.patch(first.id, { title: "Mine" });
  await seedRun(journals, "a later question", { id: first.id, anchor: first.replyId });
  assert.equal((await journals.list())[0].title, "Mine");
  assert.equal((await journals.get(first.id))?.title, "Mine");
});

test("last_run_at is the last run_end's time; a metadata change moves updated_at only", async () => {
  const { journals, clock } = await tmpJournals();
  clock.t = at(1);
  const { id } = await seedRun(journals, "hello");
  clock.t = at(9);
  const meta = await journals.patch(id, { pinned: true });
  assert.deepEqual([meta?.updated_at, meta?.last_run_at], [at(9).toISOString(), at(1).toISOString()]);
});

test("list: newest updated_at first, deleted left out, hidden kept", async () => {
  const { journals, clock } = await tmpJournals();
  const a = (await seedRun(journals, "a")).id;
  const b = (await seedRun(journals, "b")).id;
  const c = (await seedRun(journals, "c")).id;
  clock.t = at(30);
  await journals.patch(a, { hidden: true });
  clock.t = at(20);
  await journals.patch(c, { pinned: true });
  clock.t = at(40);
  await journals.softDelete(b);
  const list = await journals.list();
  assert.deepEqual(list.map((m) => m.id), [a, c]);
  assert.equal(list[0].hidden, true);
});

test("list: capped at 1000, built by one pass over journals the index never saw", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "journals-"));
  for (let i = 0; i < 1005; i++) {
    const id = randomUUID();
    const when = at(i).toISOString();
    await fs.writeFile(file(dir, id), raw(id, [
      { type: "created", at: when, version: 1, id }, ...runLines(id, when, `s${i}`),
    ]));
  }
  const capped = await new Journals(dir).list();
  assert.equal(capped.length, 1000);
  assert.equal(capped[0].title, "s1004");
});

test("the index: one read per journal to build it; a rename shows without reading a journal again", async () => {
  let reads = 0;
  const counting: JournalFs = {
    open: async (p, flags) => {
      if (flags === "r") reads++;
      return fs.open(p, flags);
    },
  };
  const { dir } = await tmpJournals();
  const ids = [randomUUID(), randomUUID()];
  for (const id of ids) {
    await fs.writeFile(file(dir, id), raw(id, [{ type: "created", at: T0.toISOString(), version: 1, id },
      ...runLines(id, T0.toISOString(), id)]));
  }
  const journals = new Journals(dir, { fs: counting });
  assert.equal((await journals.list()).length, 2);
  assert.equal(reads, 2);
  await journals.patch(ids[0], { title: "Renamed" }); // the writer may read the journal's end once
  const afterPatch = reads;
  assert.equal((await journals.list()).find((m) => m.id === ids[0])?.title, "Renamed");
  assert.equal(reads, afterPatch, "the list came from the index");
});

test("the index lives on globalThis under Symbol.for('spe.sessions.index'); a restart lists the same", async () => {
  const { journals, dir } = await tmpJournals();
  const a = await seedRun(journals, "a");
  await seedRun(journals, "b");
  await journals.patch(a.id, { title: "Renamed", tags: ["dns"], pinned: true });
  const before = await journals.list();
  assert.ok((globalThis as Record<symbol, unknown>)[INDEX] instanceof Map);
  restart();
  assert.deepEqual(await new Journals(dir).list(), before);
});

test("a <uuid>.json file of the earlier format is neither listed nor read, and nothing fails (decision 14)", async () => {
  const { journals, dir } = await tmpJournals();
  const old = randomUUID();
  await fs.writeFile(path.join(dir, `${old}.json`), JSON.stringify({ version: 1, id: old, title: "old", messages: [] }));
  await fs.writeFile(path.join(dir, "notes.txt"), "x");
  assert.deepEqual(await journals.list(), []);
  assert.equal(await journals.get(old), null);
  assert.equal(await journals.load(old), null);
});

test("a session whose only run was refused is journaled but not listed, and get() is null (decision 9)", async () => {
  const { journals, dir } = await tmpJournals();
  const id = randomUUID();
  await fs.writeFile(file(dir, id), raw(id, [{ type: "created", at: T0.toISOString(), version: 1, id },
    ...runLines(id, T0.toISOString(), "", false)]));
  restart();
  const fresh = new Journals(dir);
  assert.deepEqual(await fresh.list(), []);
  assert.equal(await fresh.get(id), null);
  assert.equal(await fresh.patch(id, { pinned: true }), null);
  assert.ok((await fresh.load(id))?.runs.length === 1);
});

test("append-only: runs, a rename, a tag, a hide and a delete each add lines, earlier bytes unchanged (decision 10)", async () => {
  const { journals, dir } = await tmpJournals();
  const first = await seedRun(journals, "first");
  const states = [await fs.readFile(file(dir, first.id), "utf8")];
  const steps: (() => Promise<unknown>)[] = [
    () => seedRun(journals, "second", { id: first.id, anchor: first.replyId }),
    () => journals.patch(first.id, { title: "Renamed" }),
    () => journals.patch(first.id, { tags: ["dns"] }),
    () => journals.patch(first.id, { hidden: true }),
    () => journals.softDelete(first.id),
  ];
  for (const step of steps) {
    await step();
    const now = await fs.readFile(file(dir, first.id), "utf8");
    assert.ok(now.startsWith(states.at(-1)!) && now.length > states.at(-1)!.length);
    states.push(now);
  }
  const metas = states.at(-1)!.trimEnd().split("\n").map((l) => JSON.parse(l)).filter((l) => l.type === "meta");
  assert.deepEqual(metas.map(({ at: _at, ...rest }) => Object.keys(rest).sort()),
    [["title", "type"], ["tags", "type"], ["hidden", "type"], ["deleted_at", "type"]]);
});

test("a PATCH adds exactly one meta line", async () => {
  const { journals, dir } = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const count = async () => (await fs.readFile(file(dir, id), "utf8")).trimEnd().split("\n").length;
  const before = await count();
  await journals.patch(id, { title: "x", tags: ["a"], pinned: true, hidden: false });
  assert.equal(await count(), before + 1);
});

test("20 concurrent metadata updates to one session all land", async () => {
  const { journals, clock } = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const patches = Array.from({ length: 20 }, (_, i) =>
    [{ title: `t${i}` }, { tags: [`g${i}`] }, { pinned: i % 8 === 2 }, { hidden: i % 8 === 3 }][i % 4],
  );
  clock.t = at(30);
  const results = await Promise.all(patches.map((p) => journals.patch(id, p)));
  assert.equal(results.every((m) => m !== null), true);
  const [meta] = await journals.list();
  assert.deepEqual([meta.title, meta.tags, meta.pinned, meta.hidden], ["t16", ["g17"], true, true]);
  assert.equal(shared().queue.has(id), false);
});

test("a torn last line gets \\n before the next append, and the rebuild skips it", async () => {
  const { dir } = await tmpJournals();
  const id = randomUUID();
  const whole = raw(id, [{ type: "created", at: T0.toISOString(), version: 1, id }, ...runLines(id, T0.toISOString(), "kept")]);
  await fs.writeFile(file(dir, id), whole + '{"type":"event","at":"2026-10-29T10:00:0');
  // parseJournal (lib/journal.ts) logs a skipped line with console.warn, not console.error.
  const logged = mock.method(console, "warn", () => {});
  try {
    const journals = new Journals(dir);
    assert.equal((await journals.list())[0].title, "kept");
    await journals.patch(id, { title: "after the tear" });
    const text = await fs.readFile(file(dir, id), "utf8");
    assert.ok(text.startsWith(whole + '{"type":"event","at":"2026-10-29T10:00:0\n'), text);
    assert.equal(JSON.parse(text.trimEnd().split("\n").at(-1)!).title, "after the tear");
    const conv = await journals.load(id);
    assert.equal(conv?.skipped, 1);
    assert.equal((await journals.get(id))?.title, "after the tear");
  } finally {
    logged.mock.restore();
  }
});

test("a failed interval fsync does not fail the session's next append: it is written with a fresh writer", async () => {
  // Every sync fails until the test heals the disk; the interval timer fires only when the test fires it.
  let healthy = true;
  const syncs = { failed: 0 };
  const flaky: JournalFs = {
    open: async (p, flags) => {
      const handle = await fs.open(p, flags);
      return {
        appendFile: (data: string) => handle.appendFile(data),
        sync: async () => {
          if (!healthy) {
            syncs.failed++;
            throw Object.assign(new Error("EIO: i/o error, fsync"), { code: "EIO" });
          }
          await handle.sync();
        },
        close: () => handle.close(),
        stat: () => handle.stat(),
        read: (buf: Buffer, off: number, len: number, pos: number) => handle.read(buf, off, len, pos),
      };
    },
    syncDir: async () => {},
  };
  const timers: (() => void)[] = [];
  const clock: Clock = { now: () => 0, setTimeout: (fn) => timers.push(fn), clearTimeout: () => {} };
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "journals-"));
  const journals = new Journals(dir, { fs: flaky, clock });
  const { id } = await seedRun(journals, "before the fault");
  await journals.append(id, { type: "meta", pinned: true }, "soon"); // arms the interval fsync
  const logged = mock.method(console, "error", () => {});
  try {
    healthy = false;
    for (const fire of timers.splice(0)) fire();
    for (let i = 0; i < 100 && syncs.failed === 0; i++) await new Promise((r) => setTimeout(r, 5));
    assert.equal(syncs.failed, 1, "the interval fsync ran and failed");
    await new Promise((r) => setTimeout(r, 5));
    healthy = true;
    await journals.patch(id, { title: "after the fault" });
    const last = JSON.parse((await fs.readFile(file(dir, id), "utf8")).trimEnd().split("\n").at(-1)!);
    assert.equal(last.title, "after the fault");
    assert.equal((await journals.get(id))?.title, "after the fault");
  } finally {
    logged.mock.restore();
  }
});

test("get() during an append: an unterminated last segment is dropped without a warning", async () => {
  const { journals, dir } = await tmpJournals();
  const { id } = await seedRun(journals, "kept");
  const whole = await fs.readFile(file(dir, id), "utf8");
  // As a reader outside the session's queue sees a line still being appended.
  await fs.appendFile(file(dir, id), '{"type":"meta","at":"2026-10-29T10:00:00.000Z","title":"half');
  const warned = mock.method(console, "warn", () => {});
  try {
    const view = await journals.get(id);
    assert.equal(view?.title, "kept");
    assert.equal(view?.messages.length, 2);
    assert.equal(warned.mock.callCount(), 0, JSON.stringify(warned.mock.calls.map((c) => c.arguments)));
  } finally {
    warned.mock.restore();
  }
  assert.ok((await fs.readFile(file(dir, id), "utf8")).startsWith(whole));
});

test("a journal without a created line lists with its first line's time", async () => {
  const { dir } = await tmpJournals();
  const id = randomUUID();
  await fs.writeFile(file(dir, id), raw(id, runLines(id, at(5).toISOString(), "no created line")));
  restart();
  const [meta] = await new Journals(dir).list();
  assert.equal(meta.created_at, at(5).toISOString());
});

test("softDelete appends deleted_at; patch, delete and get then find nothing; the journal stays", async () => {
  const { journals, clock, dir } = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  clock.t = at(5);
  assert.equal(await journals.softDelete(id), true);
  assert.equal(await journals.isDeleted(id), true);
  assert.equal(await journals.softDelete(id), false);
  assert.equal(await journals.patch(id, { pinned: true }), null);
  assert.equal(await journals.get(id), null);
  const last = JSON.parse((await fs.readFile(file(dir, id), "utf8")).trimEnd().split("\n").at(-1)!);
  assert.deepEqual(last, { type: "meta", at: at(5).toISOString(), deleted_at: at(5).toISOString() });
  assert.equal(await journals.softDelete(randomUUID()), false);
  assert.equal(await journals.isDeleted(randomUUID()), false);
});

test("a hand-edited meta line with the wrong type for a key is folded without that key; list and get agree", async () => {
  const { journals, dir } = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const before = await fs.readFile(file(dir, id), "utf8");
  await fs.writeFile(file(dir, id), before + raw(id, [{ type: "meta", at: at(2).toISOString(), pinned: "yes" }]));
  restart();
  const fresh = new Journals(dir);
  const [meta] = await fresh.list();
  assert.equal(meta.pinned, false);
  assert.equal((await fresh.get(id))?.pinned, false);
});

test("a missing sessions directory lists as empty", async () => {
  assert.deepEqual(await new Journals(path.join(os.tmpdir(), `absent-${randomUUID()}`)).list(), []);
});

test("SPE_SESSIONS_TEST_SAVE_DELAY_MS holds a run_end append, nothing else", async () => {
  const { journals } = await tmpJournals();
  const id = randomUUID();
  process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS = "200";
  try {
    let t = Date.now();
    await journals.append(id, { type: "created", version: 1, id }, "now");
    assert.ok(Date.now() - t < 150);
    t = Date.now();
    await journals.append(id, { type: "run_end", run_id: "r", status: "refused", error: null }, "now");
    assert.ok(Date.now() - t >= 180);
  } finally {
    delete process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS;
  }
});
