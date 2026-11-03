// The session API on journals: id checks, metadata-only PATCH (one meta line), body limits, soft delete,
// the tip's branch, generic errors. Decisions 10, 13, 20, 21.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { deleteSession, getSession, listSessions, patchSession } from "./api.ts";
import { Journals } from "./sessions.ts";
import { seedRun } from "./test-journals.ts";

async function tmpJournals(): Promise<Journals> {
  return new Journals(await fs.mkdtemp(path.join(os.tmpdir(), "api-")));
}

const file = (j: Journals, id: string) => path.join(j.dir, `${id}.jsonl`);

function patchRequest(body: string): Request {
  return new Request("http://chat-ui/api/sessions/x", {
    method: "PATCH", headers: { "content-type": "application/json" }, body,
  });
}

const BAD_IDS = ["../x", "a/b", "6F1C0D2E-1234-4ABC-8DEF-0123456789AB", "6f1c0d2e-1234-1abc-8def-0123456789ab", "x"];

test("ids that are not canonical UUID v4 get 400 from every route, no file created", async () => {
  const journals = await tmpJournals();
  for (const id of BAD_IDS) {
    for (const response of [
      await getSession(journals, id),
      await patchSession(journals, id, patchRequest('{"pinned":true}')),
      await deleteSession(journals, id),
    ]) {
      assert.equal(response.status, 400, id);
      assert.deepEqual(await response.json(), { error: "invalid session id" });
    }
  }
  assert.deepEqual(await fs.readdir(journals.dir), []);
});

test("GET one: the metadata and the tip's branch, without version and title_source; 404 when missing", async () => {
  const journals = await tmpJournals();
  const first = await seedRun(journals, "hello");
  await seedRun(journals, "again", { id: first.id, anchor: first.replyId });
  const response = await getSession(journals, first.id);
  assert.equal(response.status, 200);
  const view = await response.json();
  assert.deepEqual(Object.keys(view).sort(),
    ["created_at", "hidden", "id", "messages", "pinned", "tags", "title", "updated_at"]);
  assert.deepEqual(view.messages.map((m: { content: string }) => m.content),
    ["hello", "echo: hello", "again", "echo: again"]);
  assert.equal((await getSession(journals, randomUUID())).status, 404);
});

test("PATCH with messages, runs, id, deleted_at or an unknown key: 400, the journal unchanged", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const before = await fs.readFile(file(journals, id), "utf8");
  for (const body of [
    { messages: [] }, { runs: [] }, { id: randomUUID() }, { deleted_at: null }, { colour: "red" },
    { title: "ok", messages: [] }, { tags: ["bad tag"] }, { pinned: "true" }, { title: "x".repeat(201) }, {},
  ]) {
    const response = await patchSession(journals, id, patchRequest(JSON.stringify(body)));
    assert.equal(response.status, 400, JSON.stringify(body));
    assert.deepEqual(await response.json(), { error: "invalid session metadata" });
  }
  for (const body of ["{not json", "", "[]", "null", '"title"', "42", "true", '[{"title":"x"}]']) {
    assert.equal((await patchSession(journals, id, patchRequest(body))).status, 400, body);
  }
  assert.equal(await fs.readFile(file(journals, id), "utf8"), before);
});

test("PATCH over 16 KB: 413, the journal unchanged", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const before = await fs.readFile(file(journals, id), "utf8");
  const big = JSON.stringify({ title: "x".repeat(16 * 1024) });
  const response = await patchSession(journals, id, patchRequest(big));
  assert.equal(response.status, 413);
  assert.deepEqual(await response.json(), { error: "the request body is too large" });
  const declared = new Request("http://chat-ui/api/sessions/x", {
    method: "PATCH", headers: { "content-type": "application/json", "content-length": "17000" },
    body: '{"pinned":true}',
  });
  assert.equal((await patchSession(journals, id, declared)).status, 413);
  const streamed = new Request("http://chat-ui/api/sessions/x", {
    method: "PATCH", body: new Blob([big]).stream(), duplex: "half",
  } as RequestInit);
  assert.equal((await patchSession(journals, id, streamed)).status, 413);
  assert.equal(await fs.readFile(file(journals, id), "utf8"), before);
});

test("PATCH: 200 with the new metadata, exactly one meta line added; 404 when missing", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const before = await fs.readFile(file(journals, id), "utf8");
  const response = await patchSession(journals, id, patchRequest('{"title":"Mine","tags":[" DNS "],"pinned":true}'));
  assert.equal(response.status, 200);
  const meta = await response.json();
  assert.deepEqual([meta.id, meta.title, meta.tags, meta.pinned, meta.hidden], [id, "Mine", ["dns"], true, false]);
  assert.deepEqual(Object.keys(meta).sort(),
    ["created_at", "hidden", "id", "last_run_at", "pinned", "tags", "title", "updated_at"]);
  const after = await fs.readFile(file(journals, id), "utf8");
  assert.ok(after.startsWith(before));
  const added = after.slice(before.length).trimEnd().split("\n").map((l) => JSON.parse(l));
  assert.equal(added.length, 1);
  assert.deepEqual({ ...added[0], at: "" }, { type: "meta", at: "", title: "Mine", tags: ["dns"], pinned: true });
  assert.equal((await patchSession(journals, randomUUID(), patchRequest('{"pinned":true}'))).status, 404);
});

test("DELETE: 204, then gone from list, GET, PATCH and DELETE (404); the journal kept with deleted_at", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const other = (await seedRun(journals, "other")).id;
  assert.equal((await deleteSession(journals, id)).status, 204);
  assert.deepEqual((await (await listSessions(journals)).json()).map((m: { id: string }) => m.id), [other]);
  assert.equal((await getSession(journals, id)).status, 404);
  assert.equal((await patchSession(journals, id, patchRequest('{"pinned":true}'))).status, 404);
  assert.equal((await deleteSession(journals, id)).status, 404);
  const last = JSON.parse((await fs.readFile(file(journals, id), "utf8")).trimEnd().split("\n").at(-1)!);
  assert.equal(typeof last.deleted_at, "string");
});

test("a new session is absent from the list until its first run_start (decision 20)", async () => {
  const journals = await tmpJournals();
  const id = randomUUID();
  assert.deepEqual(await (await listSessions(journals)).json(), []);
  assert.equal((await getSession(journals, id)).status, 404);
  await seedRun(journals, "new chat");
  assert.equal((await (await listSessions(journals)).json()).length, 1);
});

test("store failures give the generic 500, no path in the body, logged without message content", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "canary-123 in a message");
  class Broken extends Journals {
    async load(): Promise<never> {
      throw Object.assign(new Error(`EIO: i/o error, read '${journals.dir}'`), { code: "EIO" });
    }
  }
  const notADir = new Journals(file(journals, id)); // readdir: ENOTDIR
  const logged = mock.method(console, "error", () => {});
  try {
    for (const [what, response] of [
      ["GET", await getSession(new Broken(journals.dir), id)],
      ["list", await listSessions(notADir)],
      ["PATCH", await patchSession(notADir, id, patchRequest('{"title":"x"}'))],
      ["DELETE", await deleteSession(notADir, id)],
    ] as const) {
      assert.equal(response.status, 500, what);
      const text = await response.text();
      assert.deepEqual(JSON.parse(text), { error: "the session store failed; see the chat-ui logs" }, what);
      assert.doesNotMatch(text, new RegExp(journals.dir), what);
    }
    assert.ok(logged.mock.callCount() >= 4);
    assert.doesNotMatch(JSON.stringify(logged.mock.calls.map((c) => c.arguments)), /canary-123/);
  } finally {
    logged.mock.restore();
  }
});
