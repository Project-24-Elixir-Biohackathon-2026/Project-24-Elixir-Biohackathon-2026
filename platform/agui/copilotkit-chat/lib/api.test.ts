// The session API: id checks, metadata-only PATCH, body limits, soft delete, generic errors.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/client";
import { deleteSession, getSession, listSessions, patchSession } from "./api.ts";
import { SessionRecorder } from "./recorder.ts";
import { SessionStore } from "./sessions.ts";
import type { SessionRecord } from "./sessions.ts";
import { startTestAgent } from "./test-agent.ts";

async function tmpStore(): Promise<SessionStore> {
  return new SessionStore(await fs.mkdtemp(path.join(os.tmpdir(), "api-")));
}

async function seeded(store: SessionStore, text = "hello"): Promise<string> {
  const id = randomUUID();
  const now = new Date();
  await store.recordRun(id, [{ id: randomUUID(), role: "user", content: text } as Message],
    { run_id: randomUUID(), started_at: now.toISOString(), ended_at: now.toISOString(), status: "completed" }, now);
  return id;
}

function patchRequest(body: string): Request {
  return new Request("http://chat-ui/api/sessions/x", {
    method: "PATCH", headers: { "content-type": "application/json" }, body,
  });
}

const BAD_IDS = ["../x", "a/b", "6F1C0D2E-1234-4ABC-8DEF-0123456789AB", "6f1c0d2e-1234-1abc-8def-0123456789ab", "x"];

test("ids that are not canonical UUID v4 get 400 from every route, no file created", async () => {
  const store = await tmpStore();
  for (const id of BAD_IDS) {
    for (const response of [
      await getSession(store, id),
      await patchSession(store, id, patchRequest('{"pinned":true}')),
      await deleteSession(store, id),
    ]) {
      assert.equal(response.status, 400, id);
      assert.deepEqual(await response.json(), { error: "invalid session id" });
    }
  }
  assert.deepEqual(await fs.readdir(store.dir), []);
});

test("GET one: the record without deleted_at and runs; 404 when missing", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const response = await getSession(store, id);
  assert.equal(response.status, 200);
  const view = await response.json();
  assert.deepEqual(Object.keys(view).sort(), [
    "created_at", "hidden", "id", "messages", "pinned", "tags", "title", "title_source", "updated_at", "version",
  ]);
  assert.equal((await getSession(store, randomUUID())).status, 404);
});

test("PATCH with messages, runs, id, deleted_at or an unknown key: 400, nothing changed", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const file = path.join(store.dir, `${id}.json`);
  const before = await fs.readFile(file, "utf8");
  for (const body of [
    { messages: [] }, { runs: [] }, { id: randomUUID() }, { deleted_at: null }, { colour: "red" },
    { title: "ok", messages: [] }, { tags: ["bad tag"] }, { pinned: "true" }, { title: "x".repeat(201) }, {},
  ]) {
    const response = await patchSession(store, id, patchRequest(JSON.stringify(body)));
    assert.equal(response.status, 400, JSON.stringify(body));
    assert.deepEqual(await response.json(), { error: "invalid session metadata" });
  }
  assert.equal(await fs.readFile(file, "utf8"), before);
});

test("PATCH bodies that are not a JSON object: 400, nothing changed", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const file = path.join(store.dir, `${id}.json`);
  const before = await fs.readFile(file, "utf8");
  for (const body of ["{not json", "", "[]", "null", '"title"', "42", "true", '[{"title":"x"}]']) {
    const response = await patchSession(store, id, patchRequest(body));
    assert.equal(response.status, 400, body);
    assert.deepEqual(await response.json(), { error: "invalid session metadata" });
  }
  assert.equal(await fs.readFile(file, "utf8"), before);
});

test("PATCH over 16 KB: 413, nothing changed", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const file = path.join(store.dir, `${id}.json`);
  const before = await fs.readFile(file, "utf8");
  const big = JSON.stringify({ title: "x".repeat(16 * 1024) });
  const response = await patchSession(store, id, patchRequest(big));
  assert.equal(response.status, 413);
  assert.deepEqual(await response.json(), { error: "the request body is too large" });
  // a declared content-length over the limit is refused before the body is read
  const declared = new Request("http://chat-ui/api/sessions/x", {
    method: "PATCH", headers: { "content-type": "application/json", "content-length": "17000" },
    body: '{"pinned":true}',
  });
  assert.equal(declared.headers.get("content-length"), "17000");
  assert.equal((await patchSession(store, id, declared)).status, 413);
  // the same body streamed without a content-length is cut off as it is read
  const streamed = new Request("http://chat-ui/api/sessions/x", {
    method: "PATCH", body: new Blob([big]).stream(), duplex: "half",
  } as RequestInit);
  assert.equal((await patchSession(store, id, streamed)).status, 413);
  assert.equal(await fs.readFile(file, "utf8"), before);
});

test("PATCH: 200 with the new metadata; title_source becomes user", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const response = await patchSession(store, id, patchRequest('{"title":"Mine","tags":[" DNS "],"pinned":true}'));
  assert.equal(response.status, 200);
  const meta = await response.json();
  assert.deepEqual([meta.id, meta.title, meta.tags, meta.pinned, meta.hidden], [id, "Mine", ["dns"], true, false]);
  assert.deepEqual(Object.keys(meta).sort(), ["created_at", "hidden", "id", "last_run_at", "pinned", "tags", "title", "updated_at"]);
  assert.equal(((await store.read(id)) as SessionRecord).title_source, "user");
  assert.equal((await patchSession(store, randomUUID(), patchRequest('{"pinned":true}'))).status, 404);
});

test("DELETE: 204, then gone from list, GET, PATCH and DELETE (404); the file kept", async () => {
  const store = await tmpStore();
  const id = await seeded(store);
  const other = await seeded(store, "other");
  assert.equal((await deleteSession(store, id)).status, 204);
  assert.deepEqual((await (await listSessions(store)).json()).map((m: { id: string }) => m.id), [other]);
  assert.equal((await getSession(store, id)).status, 404);
  assert.equal((await patchSession(store, id, patchRequest('{"pinned":true}'))).status, 404);
  assert.equal((await deleteSession(store, id)).status, 404);
  assert.notEqual(((await store.read(id)) as SessionRecord).deleted_at, null);
});

test("a new session is absent from the list until a run on it ends", async () => {
  const store = await tmpStore();
  const server = await startTestAgent(300);
  try {
    const id = randomUUID();
    const agent = new HttpAgent({ url: server.url });
    agent.use(new SessionRecorder(() => store));
    agent.threadId = id;
    agent.setMessages([{ id: randomUUID(), role: "user", content: "new chat" } as Message]);
    const run = agent.runAgent({ runId: randomUUID() });
    // A deadline, so a stuck case fails clearly instead of hanging.
    const deadline = Date.now() + 5000;
    while (server.requests.length === 0 && Date.now() < deadline) await new Promise((r) => setTimeout(r, 5));
    assert.ok(server.requests.length > 0, "the agent got no request within 5 s");
    assert.deepEqual(await (await listSessions(store)).json(), []);
    assert.equal((await getSession(store, id)).status, 404);
    await run;
    assert.deepEqual((await (await listSessions(store)).json()).map((m: { id: string }) => m.id), [id]);
  } finally {
    await server.close();
  }
});

test("store failures give the generic 500 and log no message content", async () => {
  const store = await tmpStore();
  const broken = randomUUID();
  await fs.writeFile(path.join(store.dir, `${broken}.json`), '{"version":1,"secret":canary-123}');
  const logged = mock.method(console, "error", () => {});
  try {
    const response = await getSession(store, broken);
    assert.equal(response.status, 500);
    const text = await response.text();
    assert.deepEqual(JSON.parse(text), { error: "the session store failed; see the chat-ui logs" });
    assert.doesNotMatch(text, new RegExp(store.dir));
    assert.doesNotMatch(JSON.stringify(logged.mock.calls.map((c) => c.arguments)), /canary-123/);
    assert.equal((await listSessions(store)).status, 200); // the list skips it
  } finally {
    logged.mock.restore();
  }
});

test("list, PATCH and DELETE: a store failure is the generic 500, logged without content", async () => {
  const store = await tmpStore();
  const broken = randomUUID();
  await fs.writeFile(path.join(store.dir, `${broken}.json`), '{"version":1,"secret":canary-123}');
  const notADir = new SessionStore(path.join(store.dir, `${broken}.json`)); // readdir: ENOTDIR
  const logged = mock.method(console, "error", () => {});
  try {
    for (const [what, response] of [
      ["list", await listSessions(notADir)],
      ["PATCH", await patchSession(store, broken, patchRequest('{"title":"x"}'))],
      ["DELETE", await deleteSession(store, broken)],
    ] as const) {
      assert.equal(response.status, 500, what);
      const text = await response.text();
      assert.deepEqual(JSON.parse(text), { error: "the session store failed; see the chat-ui logs" }, what);
      assert.doesNotMatch(text, new RegExp(store.dir), what);
    }
    assert.equal(logged.mock.callCount(), 3);
    assert.doesNotMatch(JSON.stringify(logged.mock.calls.map((c) => c.arguments)), /canary-123/);
  } finally {
    logged.mock.restore();
  }
  assert.equal(await fs.readFile(path.join(store.dir, `${broken}.json`), "utf8"), '{"version":1,"secret":canary-123}');
});
