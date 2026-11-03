// The journal's format, its parser and its only writer: lines stamped and appended whole, a torn end
// repaired before the first append, fsync now or within a second, failures sticky.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { FSYNC_INTERVAL_MS, JOURNAL_SUFFIX, JournalWriter, idOfJournal, journalPath, parseJournal } from "./journal.ts";
import type { Clock, JournalFs, NewLine } from "./journal.ts";
import { ValidationError } from "./sessions.ts";

const tmp = () => fs.mkdtemp(path.join(os.tmpdir(), "journal-"));
const fixed = () => new Date("2026-11-03T12:00:00.000Z");

// A clock whose timers run only when the test calls tick().
function fakeClock() {
  let next = 1;
  const timers = new Map<number, { fn: () => void; at: number }>();
  let now = 0;
  const clock: Clock = {
    now: () => now,
    setTimeout: (fn, ms) => {
      const id = next++;
      timers.set(id, { fn, at: now + ms });
      return id;
    },
    clearTimeout: (id) => void timers.delete(id as number),
  };
  const tick = async (ms: number) => {
    now += ms;
    for (const [id, timer] of [...timers]) {
      if (timer.at <= now) {
        timers.delete(id);
        timer.fn();
      }
    }
    await new Promise((r) => setImmediate(r));
  };
  return { clock, tick, pending: () => timers.size };
}

// The real filesystem, with sync() counted and appends or syncs made to fail on demand.
function countingFs() {
  const counts = { sync: 0, opens: [] as string[], dirSyncs: [] as string[] };
  let failAppend = false;
  let failSync = false;
  const fsys: JournalFs = {
    open: async (file, flags) => {
      counts.opens.push(flags);
      const handle = await fs.open(file, flags);
      return {
        appendFile: async (data: string) => {
          if (failAppend) throw new Error("ENOSPC: no space left on device");
          await handle.appendFile(data);
        },
        sync: async () => {
          counts.sync++;
          if (failSync) throw new Error("EIO: i/o error, fsync");
          await handle.sync();
        },
        close: () => handle.close(),
        stat: () => handle.stat(),
        read: (buf: Buffer, off: number, len: number, pos: number) => handle.read(buf, off, len, pos),
      };
    },
    syncDir: async (dir) => {
      counts.dirSyncs.push(dir);
      const handle = await fs.open(dir, "r");
      try {
        await handle.sync();
      } finally {
        await handle.close();
      }
    },
  };
  return { fsys, counts, failNext: () => (failAppend = true), failSyncs: () => (failSync = true) };
}

const created = (id: string): NewLine => ({ type: "created", version: 1, id });
const event = (n: number): NewLine =>
  ({ type: "event", run_id: "r1", event: { type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: `${n}` } }) as NewLine;

test("journalPath and idOfJournal accept canonical v4 ids only", () => {
  const id = randomUUID();
  assert.equal(JOURNAL_SUFFIX, ".jsonl");
  assert.equal(journalPath("/data/sessions", id), `/data/sessions/${id}.jsonl`);
  for (const bad of ["../x", "a/b", id.toUpperCase(), "00000000-0000-1000-8000-000000000000", ""]) {
    assert.throws(() => journalPath("/data/sessions", bad), ValidationError, bad);
  }
  assert.equal(idOfJournal(`${id}.jsonl`), id);
  for (const name of [`${id}.json`, `${id}.jsonl.tmp`, "x.jsonl", `${id.toUpperCase()}.jsonl`]) {
    assert.equal(idOfJournal(name), null, name);
  }
});

test("append stamps at after type, writes one line each, and the file parses back", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const writer = new JournalWriter(file, { now: fixed });
  const line = await writer.append(created("s1"), "now");
  assert.deepEqual(line, { type: "created", at: "2026-11-03T12:00:00.000Z", version: 1, id: "s1" });
  await writer.append({ type: "meta", title: "a\nb" }, "now");
  await writer.close();
  const text = await fs.readFile(file, "utf8");
  assert.equal(text, '{"type":"created","at":"2026-11-03T12:00:00.000Z","version":1,"id":"s1"}\n'
    + '{"type":"meta","at":"2026-11-03T12:00:00.000Z","title":"a\\nb"}\n');
  assert.deepEqual(parseJournal(text), {
    lines: [line, { type: "meta", at: "2026-11-03T12:00:00.000Z", title: "a\nb" }], skipped: 0,
  });
});

test("the writer's at wins over one the caller passes", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const writer = new JournalWriter(file, { now: fixed });
  const line = await writer.append({ type: "meta", at: "1999-01-01T00:00:00.000Z", pinned: true } as unknown as NewLine, "now");
  await writer.close();
  assert.deepEqual(line, { type: "meta", at: "2026-11-03T12:00:00.000Z", pinned: true });
  assert.equal(await fs.readFile(file, "utf8"), '{"type":"meta","at":"2026-11-03T12:00:00.000Z","pinned":true}\n');
});

test("parseJournal skips torn, foreign and incomplete lines and logs only their numbers", () => {
  const good = '{"type":"meta","at":"t","hidden":true}';
  const warnings: string[] = [];
  const warn = console.warn;
  console.warn = (msg: string) => void warnings.push(msg);
  try {
    const text = [
      good,
      '{"type":"event","at":"t","run_id":"r1","event":{"type":"TEXT_MESS', // torn: secret content
      '{"type":"surprise","at":"t"}',
      '{"type":"run_end","at":"t"}', // no run_id
      "[1,2]",
      "",
      good,
    ].join("\n") + "\n";
    const { lines, skipped } = parseJournal(text);
    assert.equal(lines.length, 2);
    assert.equal(skipped, 4);
    assert.deepEqual(warnings, [2, 3, 4, 5].map((n) => `journal: line ${n} skipped (not a journal line)`));
  } finally {
    console.warn = warn;
  }
});

test("a run_start whose messages are not objects with a string id is skipped", (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  const runStart = (messages: unknown) => JSON.stringify({ type: "run_start", at: "t", run_id: "r1", anchor: null, messages,
    ignored: [], request: {}, source: "chat" });
  const text = [
    runStart([{ id: "u1", role: "user", content: "q" }]),
    runStart([null]), runStart(["u1"]), runStart([{ role: "user" }]), runStart([{ id: 7 }]), runStart([[]]),
  ].join("\n") + "\n";
  const { lines, skipped } = parseJournal(text);
  assert.equal(lines.length, 1);
  assert.equal(skipped, 5);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), [2, 3, 4, 5, 6].map((n) => `journal: line ${n} skipped (not a journal line)`));
});

test("a torn last line gets a newline before the next append, and parsing skips only it", async (t) => {
  const warn = t.mock.method(console, "warn", () => {});
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const head = '{"type":"created","at":"t","version":1,"id":"s1"}\n{"type":"event","at":"t","run_id":"r1","ev';
  await fs.writeFile(file, head);
  const writer = new JournalWriter(file, { now: fixed });
  await writer.append({ type: "meta", pinned: true }, "now");
  await writer.append({ type: "meta", hidden: true }, "now");
  await writer.close();
  const text = await fs.readFile(file, "utf8");
  assert.ok(text.startsWith(`${head}\n{"type":"meta"`), "earlier bytes unchanged, one newline added");
  const { lines, skipped } = parseJournal(text);
  assert.deepEqual(lines.map((l) => l.type), ["created", "meta", "meta"]);
  assert.equal(skipped, 1);
  assert.deepEqual(warn.mock.calls.map((c) => c.arguments[0]), ["journal: line 2 skipped (not a journal line)"]);
});

test("a journal that ends in a newline gets nothing added", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const head = '{"type":"created","at":"t","version":1,"id":"s1"}\n';
  await fs.writeFile(file, head);
  const writer = new JournalWriter(file, { now: fixed });
  await writer.append({ type: "meta", pinned: true }, "now");
  await writer.close();
  assert.equal(await fs.readFile(file, "utf8"), `${head}{"type":"meta","at":"2026-11-03T12:00:00.000Z","pinned":true}\n`);
});

test("the writer opens files only to append or to read", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  await fs.writeFile(file, '{"type":"created","at":"t","version":1,"id":"s1"}\n');
  const { fsys, counts } = countingFs();
  const writer = new JournalWriter(file, { fs: fsys, now: fixed });
  await writer.append({ type: "meta", pinned: true }, "now");
  await writer.append({ type: "meta", pinned: false }, "soon");
  await writer.close();
  assert.deepEqual(counts.opens, ["a", "r"]);
});

test("a new journal's directory is fsynced once, when the writer creates the file", async () => {
  const dir = await tmp();
  const file = path.join(dir, `${randomUUID()}.jsonl`);
  const { fsys, counts } = countingFs();
  const writer = new JournalWriter(file, { fs: fsys, now: fixed });
  await writer.append(created("s1"), "now");
  await writer.append({ type: "meta", pinned: true }, "now");
  await writer.close();
  assert.deepEqual(counts.dirSyncs, [dir], "the new file's directory entry is made durable");
  const again = new JournalWriter(file, { fs: fsys, now: fixed });
  await again.append({ type: "meta", hidden: true }, "now");
  await again.close();
  assert.deepEqual(counts.dirSyncs, [dir], "an existing journal's directory is not fsynced again");
});

test("1000 events within a second fsync at most three times: run_start, one interval, run_end", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const { clock, tick, pending } = fakeClock();
  const { fsys, counts } = countingFs();
  const writer = new JournalWriter(file, { clock, fs: fsys, now: fixed });
  await writer.append({ type: "run_start", run_id: "r1", anchor: null, messages: [], ignored: [],
    request: { tools: [], context: [], state: {}, forwardedProps: {} }, source: "chat" }, "now");
  assert.equal(counts.sync, 1);
  for (let n = 0; n < 1000; n++) {
    await writer.append(event(n), "soon");
    if (n === 500) await tick(FSYNC_INTERVAL_MS); // the interval passes once, mid-run
  }
  assert.equal(counts.sync, 2, "one interval fsync for the first 501 events");
  assert.equal(pending(), 1, "the later events wait for the next interval");
  await writer.append({ type: "run_end", run_id: "r1", status: "completed", error: null }, "now");
  assert.equal(counts.sync, 3);
  assert.equal(pending(), 0, "run_end's fsync covers the pending interval");
  await writer.close();
  assert.equal(counts.sync, 3, "nothing pending at close");
  assert.equal(parseJournal(await fs.readFile(file, "utf8")).lines.length, 1002);
});

test("close flushes a pending soon fsync", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const { clock } = fakeClock();
  const { fsys, counts } = countingFs();
  const writer = new JournalWriter(file, { clock, fs: fsys, now: fixed });
  await writer.append(event(1), "soon");
  assert.equal(counts.sync, 0);
  await writer.close();
  assert.equal(counts.sync, 1);
  await assert.rejects(writer.append(event(2), "soon"), /closed/);
});

test("a failed append fails it and every later one", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const { fsys, failNext } = countingFs();
  const writer = new JournalWriter(file, { fs: fsys, now: fixed });
  await writer.append(created("s1"), "now");
  failNext();
  await assert.rejects(writer.append(event(1), "soon"), /ENOSPC/);
  await assert.rejects(writer.append({ type: "run_end", run_id: "r1", status: "aborted", error: null }, "now"), /ENOSPC/);
  await writer.close();
  assert.equal(parseJournal(await fs.readFile(file, "utf8")).lines.length, 1);
});

test("appends made without awaiting land whole and in call order", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const writer = new JournalWriter(file, { now: fixed });
  await Promise.all(Array.from({ length: 200 }, (_, n) => writer.append(event(n), "soon")));
  await writer.close();
  const { lines, skipped } = parseJournal(await fs.readFile(file, "utf8"));
  assert.equal(skipped, 0);
  assert.deepEqual(lines.map((l) => (l as unknown as { event: { delta: string } }).event.delta), Array.from({ length: 200 }, (_, n) => `${n}`));
});

test("a failed now fsync fails that append and every later one", async () => {
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const { fsys, failSyncs } = countingFs();
  const writer = new JournalWriter(file, { fs: fsys, now: fixed });
  await writer.append(created("s1"), "now");
  failSyncs();
  await assert.rejects(writer.append({ type: "meta", pinned: true }, "now"), /EIO/);
  await assert.rejects(writer.append({ type: "meta", hidden: true }, "soon"), /EIO/);
  await writer.close();
});

test("a failed interval fsync is logged once, not thrown, and fails every later append", async (t) => {
  const error = t.mock.method(console, "error", () => {});
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const { clock, tick } = fakeClock();
  const { fsys, counts, failSyncs } = countingFs();
  const writer = new JournalWriter(file, { clock, fs: fsys, now: fixed });
  await writer.append(event(1), "soon");
  failSyncs();
  await tick(FSYNC_INTERVAL_MS); // the soon timer's fsync fails; nothing rejects unhandled
  assert.equal(counts.sync, 1);
  assert.equal(error.mock.callCount(), 1);
  assert.match(String(error.mock.calls[0].arguments[0]), /^journal .*: interval fsync failed: EIO/);
  await assert.rejects(writer.append(event(2), "soon"), /EIO/);
  await writer.close();
  assert.equal(error.mock.callCount(), 1);
});

test("an interval fsync after a failed append neither syncs nor logs", async (t) => {
  const error = t.mock.method(console, "error", () => {});
  const file = path.join(await tmp(), `${randomUUID()}.jsonl`);
  const { clock, tick } = fakeClock();
  const { fsys, counts, failNext } = countingFs();
  const writer = new JournalWriter(file, { clock, fs: fsys, now: fixed });
  await writer.append(event(1), "soon");
  failNext();
  await assert.rejects(writer.append(event(2), "soon"), /ENOSPC/);
  await tick(FSYNC_INTERVAL_MS);
  assert.equal(counts.sync, 0);
  assert.equal(error.mock.callCount(), 0);
  await writer.close();
});

test("without a syncDir, a new journal's directory is fsynced with the real filesystem", async () => {
  // The file opens (a fake handle, empty), but its directory does not exist: the real directory fsync fails.
  const dir = path.join(await tmp(), "missing");
  const handle = { appendFile: async () => {}, sync: async () => {}, close: async () => {}, stat: async () => ({ size: 0 }),
    read: async () => ({ bytesRead: 0 }) };
  const writer = new JournalWriter(path.join(dir, `${randomUUID()}.jsonl`), { fs: { open: async () => handle }, now: fixed });
  await assert.rejects(writer.append(created("s1"), "now"), { code: "ENOENT" });
  await writer.close();
});
