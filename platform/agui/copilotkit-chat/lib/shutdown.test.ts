import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/client";
import { mock, test } from "node:test";
import { SessionRecorder } from "./recorder.ts";
import { Journals, shared } from "./sessions.ts";
import { startTestAgent } from "./test-agent.ts";
import { drain, installShutdown, shutdown } from "./shutdown.ts";
import type { RunHandle, Shared } from "./sessions.ts";

function state(): Shared {
  return { queue: new Map(), running: new Map(), closing: false };
}

function later<T>(ms: number, value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

test("shutdown sets closing, cancels every run and exits 0 once the finalising writes land", async () => {
  const s = state();
  const cancelled: string[] = [];
  for (const id of ["a", "b"]) {
    const handle: RunHandle = {
      cancel: () => {
        cancelled.push(id);
        // Unlike the recorder, which removes the id from the running set synchronously right
        // after queuing the write: this stub removes it only once the write's promise settles,
        // so the test still exercises shutdown() waiting on a write that outlives cancel().
        const write = later(30, undefined).then(() => {
          s.running.delete(id);
          if (s.queue.get(id) === write) s.queue.delete(id);
        });
        s.queue.set(id, write);
      },
    };
    s.running.set(id, handle);
  }
  const codes: number[] = [];
  await shutdown(s, (code) => codes.push(code), 2000);
  assert.equal(s.closing, true);
  assert.deepEqual(cancelled, ["a", "b"]);
  assert.equal(s.running.size, 0);
  assert.deepEqual(codes, [0]);
});

test("drain waits for a write queued while it waits", async () => {
  const s = state();
  let second = false;
  s.queue.set("a", later(20, undefined).then(() => {
    s.queue.set("b", later(40, undefined).then(() => { second = true; }));
  }));
  assert.equal(await drain(s, 2000, 5), true);
  assert.equal(second, true);
});

test("drain waits until the running set is empty", async () => {
  const s = state();
  s.running.set("a", { cancel: () => {} });
  setTimeout(() => s.running.delete("a"), 60);
  const started = Date.now();
  assert.equal(await drain(s, 2000, 10), true);
  assert.ok(Date.now() - started >= 55);
});

test("a write that never settles: shutdown gives up at the deadline and exits 1", async () => {
  const s = state();
  s.queue.set("a", new Promise(() => {}));
  const codes: number[] = [];
  const started = Date.now();
  await shutdown(s, (code) => codes.push(code), 100);
  assert.deepEqual(codes, [1]);
  assert.ok(Date.now() - started < 1000);
});

test("a cancel that throws does not stop the others", async () => {
  const s = state();
  let second = false;
  s.running.set("a", { cancel: () => { s.running.delete("a"); throw new Error("boom"); } });
  s.running.set("b", { cancel: () => { second = true; s.running.delete("b"); } });
  const codes: number[] = [];
  await shutdown(s, (code) => codes.push(code), 1000);
  assert.equal(second, true);
  assert.deepEqual(codes, [0]);
});

test("installShutdown adds one SIGTERM listener however often it is called", () => {
  const before = process.listenerCount("SIGTERM");
  installShutdown();
  installShutdown();
  assert.equal(process.listenerCount("SIGTERM"), before + 1);
});

test("SIGTERM's shutdown against the recorder: a hanging run ends cancelled in its journal, exit 0", async () => {
  const journals = new Journals(await fs.mkdtemp(path.join(os.tmpdir(), "shutdown-")));
  const server = await startTestAgent();
  const recorder = new SessionRecorder(() => journals);
  const id = randomUUID();
  const logged = mock.method(console, "log", () => {});
  try {
    const sub = recorder.run({
      threadId: id, runId: randomUUID(), state: {}, tools: [], context: [], forwardedProps: {},
      messages: [{ id: randomUUID(), role: "user", content: "hang until shutdown" } as Message],
    }, new HttpAgent({ url: server.url, fetch: recorder.fetch })).subscribe({ error: () => {} });
    for (let i = 0; i < 500 && server.requests.length === 0; i++) await new Promise((r) => setTimeout(r, 5));
    const codes: number[] = [];
    await shutdown(shared(), (code) => codes.push(code), 5000);
    sub.unsubscribe();
    assert.deepEqual(codes, [0]);
    const text = await fs.readFile(path.join(journals.dir, `${id}.jsonl`), "utf8");
    const ends = text.trimEnd().split("\n").map((l) => JSON.parse(l)).filter((l) => l.type === "run_end");
    assert.deepEqual(ends.map((e) => e.status), ["cancelled"]);
    assert.match(JSON.stringify(logged.mock.calls.map((c) => c.arguments)), /1 run\(s\) cancelled, journals written/);
  } finally {
    logged.mock.restore();
    shared().closing = false;
    await server.close();
  }
});
