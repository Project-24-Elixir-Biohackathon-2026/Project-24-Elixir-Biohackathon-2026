// The session store: the record, id and tag validation, atomic writes, the per-session queue,
// unreadable and leftover files, titles cut by code point.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { Message } from "@ag-ui/client";
import {
  SessionStore, ValidationError, autoTitle, isDeleted, isSessionId, normaliseTags, parsePatch, shared,
} from "./sessions.ts";
import type { RunEntry, SessionRecord } from "./sessions.ts";

const T0 = new Date("2026-10-29T10:00:00.000Z");
const at = (seconds: number) => new Date(T0.getTime() + seconds * 1000);

async function tmpStore(): Promise<SessionStore> {
  return new SessionStore(await fs.mkdtemp(path.join(os.tmpdir(), "sessions-")));
}

function user(content: unknown): Message {
  return { id: randomUUID(), role: "user", content } as Message;
}

function run(status: RunEntry["status"] = "completed"): RunEntry {
  return { run_id: randomUUID(), started_at: T0.toISOString(), ended_at: at(1).toISOString(), status };
}

async function seeded(store: SessionStore, text = "hello"): Promise<string> {
  const id = randomUUID();
  await store.recordRun(id, [user(text)], run(), at(1));
  return id;
}

test("isSessionId accepts only canonical lower-case UUID v4", () => {
  assert.equal(isSessionId(randomUUID()), true);
  for (const bad of [
    "../x", "a/b", "", "6F1C0D2E-1234-4ABC-8DEF-0123456789AB", "6f1c0d2e-1234-1abc-8def-0123456789ab",
    "6f1c0d2e-1234-4abc-cdef-0123456789ab", "6f1c0d2e12344abc8def0123456789ab",
    `${randomUUID()}\n`, `${randomUUID()}.json`, 42, null, undefined,
  ]) {
    assert.equal(isSessionId(bad), false, String(bad));
  }
});

test("the store refuses an invalid id before building a path", async () => {
  const store = await tmpStore();
  await assert.rejects(store.read("../x"), ValidationError);
  await assert.rejects(store.patch("a/b", { pinned: true }, T0), ValidationError);
  await assert.rejects(store.recordRun("../../etc/x", [], run(), T0), ValidationError);
  assert.deepEqual(await fs.readdir(store.dir), []);
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

test("recordRun creates a version-1 file, then merges into the latest record", async () => {
  const store = await tmpStore();
  const id = randomUUID();
  const first = run();
  await store.recordRun(id, [user("first question")], first, at(1));
  let record = (await store.read(id)) as SessionRecord;
  assert.deepEqual(Object.keys(record).sort(), [
    "created_at", "deleted_at", "hidden", "id", "messages", "pinned", "runs", "tags", "title",
    "title_source", "updated_at", "version",
  ]);
  assert.equal(record.version, 1);
  assert.equal(record.title, "first question");
  assert.equal(record.title_source, "auto");
  assert.equal(record.created_at, first.started_at);
  assert.deepEqual(record.runs, [first]);
  assert.equal((await fs.stat(path.join(store.dir, `${id}.json`))).mode & 0o777, 0o600);

  await store.patch(id, { title: "Mine", tags: ["x"] }, at(2));
  await store.recordRun(id, [user("other text")], run("failed"), at(3));
  record = (await store.read(id)) as SessionRecord;
  assert.equal(record.title, "Mine");
  assert.equal(record.title_source, "user");
  assert.deepEqual(record.tags, ["x"]);
  assert.equal(record.runs.length, 2);
  assert.equal(record.updated_at, at(3).toISOString());
});

test("a write interrupted before the rename leaves the previous file intact", async () => {
  const store = await tmpStore();
  const id = await seeded(store, "kept");
  const before = await fs.readFile(path.join(store.dir, `${id}.json`), "utf8");
  const rename = mock.method(fs, "rename", async () => {
    throw new Error("crash before rename");
  });
  try {
    await assert.rejects(store.patch(id, { title: "lost" }, at(5)), /crash before rename/);
  } finally {
    rename.mock.restore();
  }
  assert.equal(await fs.readFile(path.join(store.dir, `${id}.json`), "utf8"), before);
  assert.deepEqual(await fs.readdir(store.dir), [`${id}.json`]); // the temp file is removed
});

test("a write syncs the directory after the rename, so the rename survives a power loss", async () => {
  const store = await tmpStore();
  const realOpen = fs.open;
  const synced: string[] = [];
  const open = mock.method(fs, "open", async (...args: Parameters<typeof fs.open>) => {
    const handle = await realOpen(...args);
    const sync = handle.sync.bind(handle);
    handle.sync = async () => { synced.push(String(args[0])); return sync(); };
    return handle;
  });
  try {
    await seeded(store);
  } finally {
    open.mock.restore();
  }
  assert.equal(synced.at(-1), store.dir);
});

test("a directory that cannot be synced (EINVAL, as on some network mounts) is not a failed save", async () => {
  const store = await tmpStore();
  const realOpen = fs.open;
  const open = mock.method(fs, "open", async (...args: Parameters<typeof fs.open>) => {
    const handle = await realOpen(...args);
    if (args[0] === store.dir) {
      handle.sync = async () => { throw Object.assign(new Error("EINVAL: invalid argument, fsync"), { code: "EINVAL" }); };
    }
    return handle;
  });
  try {
    await seeded(store);
  } finally {
    open.mock.restore();
  }
  assert.equal((await fs.readdir(store.dir)).length, 1);
});

test("last_run_at is the last run's end; a metadata change moves updated_at, not last_run_at", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  assert.equal((await store.list())[0].last_run_at, at(1).toISOString());
  const meta = await store.patch(id, { pinned: true }, at(9));
  assert.deepEqual([meta?.updated_at, meta?.last_run_at], [at(9).toISOString(), at(1).toISOString()]);
});

test("20 concurrent metadata updates to one session all land", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  // Each update reads the file, changes one field and writes it back. Unserialised, a writer
  // that read before another's write puts the other field back: one field's update is lost.
  const patches = Array.from({ length: 20 }, (_, i) =>
    [{ title: `t${i}` }, { tags: [`g${i}`] }, { pinned: i % 8 === 2 }, { hidden: i % 8 === 3 }][i % 4],
  );
  const results = await Promise.all(patches.map((p, i) => store.patch(id, p, at(10 + i))));
  assert.equal(results.every((m) => m !== null), true);
  const record = (await store.read(id)) as SessionRecord;
  assert.deepEqual(
    [record.title, record.tags, record.pinned, record.hidden, record.updated_at],
    ["t16", ["g17"], true, true, at(29).toISOString()],
  );
  assert.equal(record.messages.length, 1); // the run recorded before is still there
  assert.equal(shared().queue.has(id), false); // the chain is dropped once drained
});

test("list: newest updated_at first, deleted left out, hidden kept, capped at 1000", async () => {
  const store = await tmpStore();
  const a = await seeded(store, "a");
  const b = await seeded(store, "b");
  const c = await seeded(store, "c");
  await store.patch(a, { hidden: true }, at(30));
  await store.patch(c, { pinned: true }, at(20));
  await store.softDelete(b, at(40));
  const list = await store.list();
  assert.deepEqual(list.map((m) => m.id), [a, c]);
  assert.deepEqual(Object.keys(list[0]).sort(), ["created_at", "hidden", "id", "last_run_at", "pinned", "tags", "title", "updated_at"]);
  assert.equal(list[0].hidden, true);

  const many = await tmpStore();
  for (let i = 0; i < 1005; i++) {
    const id = randomUUID();
    await fs.writeFile(path.join(many.dir, `${id}.json`), JSON.stringify({
      version: 1, id, title: `s${i}`, title_source: "auto", tags: [], pinned: false, hidden: false,
      created_at: T0.toISOString(), updated_at: at(i).toISOString(), deleted_at: null, messages: [], runs: [],
    }));
  }
  const capped = await many.list();
  assert.equal(capped.length, 1000);
  assert.equal(capped[0].title, "s1004");
});

test("an unparsable session file is skipped and logged; read throws", async () => {
  const store = await tmpStore();
  const good = await seeded(store, "good");
  const broken = randomUUID();
  const future = randomUUID();
  const quoted = randomUUID();
  await fs.writeFile(path.join(store.dir, `${broken}.json`), "{ not json");
  await fs.writeFile(path.join(store.dir, `${future}.json`), JSON.stringify({ version: 2, id: future }));
  // Node's parser error for this quotes the text ("…canary-SECRET-ABC… is not valid JSON")
  await fs.writeFile(path.join(store.dir, `${quoted}.json`), '{"version":1,"title":canary-SECRET-ABC}');
  const logged = mock.method(console, "error", () => {});
  try {
    assert.deepEqual((await store.list()).map((m) => m.id), [good]);
    assert.equal(logged.mock.callCount(), 3);
    const logs = JSON.stringify(logged.mock.calls.map((c) => c.arguments));
    assert.doesNotMatch(logs, /canary-SECRET-ABC/);
    assert.match(logs, new RegExp(`${quoted}\\.json does not parse`));
  } finally {
    logged.mock.restore();
  }
  await assert.rejects(store.read(broken), /does not parse/);
  await assert.rejects(store.read(quoted), (error: Error) => !error.message.includes("canary-SECRET-ABC"));
  await assert.rejects(store.read(future), /not a version-1 session/);
});

test("leftover .tmp- files are never listed or read as sessions", async () => {
  const store = await tmpStore();
  const id = await seeded(store, "real");
  const record = await fs.readFile(path.join(store.dir, `${id}.json`), "utf8");
  await fs.writeFile(path.join(store.dir, `${id}.json.tmp-${randomUUID()}`), record.replace("real", "stale"));
  await fs.writeFile(path.join(store.dir, `${randomUUID()}.json.tmp-x`), record);
  await fs.writeFile(path.join(store.dir, "notes.txt"), "x");
  const list = await store.list();
  assert.deepEqual(list.map((m) => [m.id, m.title]), [[id, "real"]]);
});

test("softDelete keeps the file with deleted_at; patch and delete then find nothing", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  assert.equal(await store.softDelete(id, at(5)), true);
  assert.equal(await store.softDelete(id, at(6)), false);
  assert.equal(await store.patch(id, { pinned: true }, at(7)), null);
  const record = (await store.read(id)) as SessionRecord;
  assert.equal(record.deleted_at, at(5).toISOString());
  assert.equal(record.pinned, false);
  assert.equal(await store.softDelete(randomUUID(), at(8)), false);
  assert.equal(await store.patch(randomUUID(), { pinned: true }, at(8)), null);
});

test("a missing sessions directory lists as empty", async () => {
  const store = new SessionStore(path.join(os.tmpdir(), `absent-${randomUUID()}`));
  assert.deepEqual(await store.list(), []);
});

test("read refuses a record whose pinned, hidden or deleted_at has the wrong type", async () => {
  const store = await tmpStore();
  for (const [key, value] of [
    ["pinned", "yes"], ["pinned", undefined], ["hidden", 1], ["hidden", undefined],
    ["deleted_at", false], ["deleted_at", 0], ["deleted_at", undefined],
  ] as const) {
    const id = await seeded(store);
    const file = path.join(store.dir, `${id}.json`);
    const record = JSON.parse(await fs.readFile(file, "utf8"));
    if (value === undefined) delete record[key];
    else record[key] = value;
    await fs.writeFile(file, JSON.stringify(record));
    await assert.rejects(store.read(id), /not a version-1 session/, `${key}: ${String(value)}`);
  }
});

test("isDeleted: a deleted_at string is deleted, null is not", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const record = (await store.read(id)) as SessionRecord;
  assert.equal(isDeleted(record), false);
  await store.softDelete(id, at(2));
  assert.equal(isDeleted((await store.read(id)) as SessionRecord), true);
});
