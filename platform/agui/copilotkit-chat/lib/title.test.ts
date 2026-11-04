// The model-written title: POST /api/sessions/{id}/title on journals, with a fake titler (no model), and the
// agent call against a local server. The user's title wins; the agent failing leaves the metadata unchanged.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import type { IncomingHttpHeaders } from "node:http";
import type { AddressInfo } from "node:net";
import { titleSession } from "./api.ts";
import { Journals } from "./sessions.ts";
import { seedRun } from "./test-journals.ts";
import { TitleUnavailable, agentTitler } from "./title.ts";
import type { TitleMessage, Titler } from "./title.ts";

async function tmpJournals(): Promise<Journals> {
  return new Journals(await fs.mkdtemp(path.join(os.tmpdir(), "title-")));
}

const file = (j: Journals, id: string) => path.join(j.dir, `${id}.jsonl`);
const metaLines = async (j: Journals, id: string) =>
  (await fs.readFile(file(j, id), "utf8")).trim().split("\n").map((l) => JSON.parse(l)).filter((l) => l.type === "meta");

// A POST /title request: a JSON Content-Type by default, so the route's own check (below) does not get
// in the way of tests that are about something else.
function titleRequest(contentType: string | null = "application/json"): Request {
  return new Request("http://chat-ui/api/sessions/x/title", {
    method: "POST", headers: contentType === null ? {} : { "content-type": contentType }, body: "{}",
  });
}

// A titler that answers `title` and keeps what it was asked.
function fakeTitler(title = "Greeting the agent", before?: () => Promise<void>) {
  const calls: { threadId: string; messages: TitleMessage[] }[] = [];
  const titler: Titler = async (threadId, messages) => {
    calls.push({ threadId, messages });
    await before?.();
    return title;
  };
  return { titler, calls };
}

test("no title yet: the agent is asked with the journal's first message and answer, its title is written", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello there");
  const { titler, calls } = fakeTitler("  Greeting   the agent ");
  const response = await titleSession(journals, id, titler, titleRequest());
  assert.equal(response.status, 200);
  assert.equal((await response.json()).title, "Greeting the agent");
  assert.deepEqual(calls, [{ threadId: id, messages: [
    { role: "user", content: "hello there" }, { role: "assistant", content: "echo: hello there" },
  ] }]);
  assert.deepEqual((await metaLines(journals, id)).map((l) => l.title), ["Greeting the agent"]);
  assert.equal((await journals.list())[0].title, "Greeting the agent");
});

test("the first message and answer are the first completed run's, from the journal, not later runs'", async () => {
  const journals = await tmpJournals();
  const failed = await seedRun(journals, "first try", { status: "failed" });
  const done = await seedRun(journals, "second try", { id: failed.id, anchor: null });
  await seedRun(journals, "a later question", { id: failed.id, anchor: done.replyId });
  const { titler, calls } = fakeTitler();
  await titleSession(journals, failed.id, titler, titleRequest());
  assert.deepEqual(calls[0].messages, [
    { role: "user", content: "second try" }, { role: "assistant", content: "echo: second try" },
  ]);
});

test("a retry after a failed first run: the messages are the retry's, not the failed run's", async () => {
  const journals = await tmpJournals();
  const failed = await seedRun(journals, "first try", { status: "failed" });
  await seedRun(journals, "second try", { id: failed.id, anchor: failed.replyId });
  const { titler, calls } = fakeTitler();
  await titleSession(journals, failed.id, titler, titleRequest());
  assert.deepEqual(calls[0].messages, [
    { role: "user", content: "second try" }, { role: "assistant", content: "echo: second try" },
  ]);
});

test("renamed while the agent was writing: the rename is kept, no model title appended", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const { titler, calls } = fakeTitler("Model title", async () => {
    await journals.patch(id, { title: "Mine" });
  });
  const response = await titleSession(journals, id, titler, titleRequest());
  assert.equal(calls.length, 1);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).title, "Mine");
  assert.deepEqual((await metaLines(journals, id)).map((l) => l.title), ["Mine"]);
});

test("already titled (a rename or an earlier model title): no agent call, the metadata unchanged", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  await journals.patch(id, { title: "Mine" });
  const before = await fs.readFile(file(journals, id), "utf8");
  const { titler, calls } = fakeTitler();
  const response = await titleSession(journals, id, titler, titleRequest());
  assert.equal(response.status, 200);
  assert.equal((await response.json()).title, "Mine");
  assert.equal(calls.length, 0);
  assert.equal(await fs.readFile(file(journals, id), "utf8"), before);
  // A second call after a model title: no second agent call either.
  const other = await seedRun(journals, "again");
  await titleSession(journals, other.id, fakeTitler().titler, titleRequest());
  const second = fakeTitler();
  await titleSession(journals, other.id, second.titler, titleRequest());
  assert.equal(second.calls.length, 0);
});

test("no completed run: no agent call, the metadata unchanged", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello", { status: "cancelled" });
  const before = await fs.readFile(file(journals, id), "utf8");
  const { titler, calls } = fakeTitler();
  const response = await titleSession(journals, id, titler, titleRequest());
  assert.equal(response.status, 200);
  assert.equal((await response.json()).title, "hello");
  assert.equal(calls.length, 0);
  assert.equal(await fs.readFile(file(journals, id), "utf8"), before);
});

test("the agent failing (an error status, a throw, an unusable title): 200, unchanged, logged by status only", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const before = await fs.readFile(file(journals, id), "utf8");
  const warn = mock.method(console, "warn", () => {});
  try {
    for (const titler of [
      () => Promise.reject(new TitleUnavailable(422)),
      () => Promise.reject(new Error("canary-in-the-message")),
      () => Promise.resolve("   "),
    ] as Titler[]) {
      const response = await titleSession(journals, id, titler, titleRequest());
      assert.equal(response.status, 200);
      assert.equal((await response.json()).title, "hello");
    }
    const logged = warn.mock.calls.map((c) => c.arguments.join(" "));
    assert.equal(logged.length, 3);
    assert.match(logged[0], /the agent answered 422/);
    assert.ok(logged.every((l) => !l.includes("canary")));
  } finally {
    warn.mock.restore();
  }
  assert.equal(await fs.readFile(file(journals, id), "utf8"), before);
});

test("a bad id: 400; a session not recorded: 404; neither asks the agent", async () => {
  const journals = await tmpJournals();
  const { titler, calls } = fakeTitler();
  assert.equal((await titleSession(journals, "../x", titler, titleRequest())).status, 400);
  assert.equal((await titleSession(journals, randomUUID(), titler, titleRequest())).status, 404);
  assert.equal(calls.length, 0);
});

// No body is needed, so a cross-site POST with no custom header is a CORS simple request (no preflight);
// requiring a JSON Content-Type forces a preflight instead, without which every call would retry the
// (paid) model request while the agent keeps failing.
test("not application/json: 415, no agent call", async () => {
  const journals = await tmpJournals();
  const { id } = await seedRun(journals, "hello");
  const { titler, calls } = fakeTitler();
  for (const contentType of [null, "text/plain", "application/x-www-form-urlencoded"]) {
    const response = await titleSession(journals, id, titler, titleRequest(contentType));
    assert.equal(response.status, 415);
  }
  assert.equal(calls.length, 0);
});

// A local stand-in for the agent's POST /title: answers `status` and `body`, or nothing for `hang`.
async function startTitleServer(status: number, body: string, hang = false) {
  const requests: { url: string; method: string; headers: IncomingHttpHeaders; body: unknown }[] = [];
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      requests.push({ url: req.url ?? "", method: req.method ?? "", headers: req.headers, body: JSON.parse(raw) });
      if (!hang) res.writeHead(status, { "content-type": "application/json" }).end(body);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    agentUrl: `http://127.0.0.1:${port}/agent`, requests,
    close: () => new Promise<void>((resolve) => { server.closeAllConnections(); server.close(() => resolve()); }),
  };
}

test("agentTitler: POST /title next to /agent, the bearer key, thread_id and messages; the title back", async () => {
  const agent = await startTitleServer(200, '{"title":"Greeting the agent"}');
  try {
    const messages: TitleMessage[] = [{ role: "user", content: "hi" }];
    assert.equal(await agentTitler(agent.agentUrl, "k3y")("t-1", messages), "Greeting the agent");
    assert.equal(agent.requests[0].url, "/title");
    assert.equal(agent.requests[0].method, "POST");
    assert.equal(agent.requests[0].headers.authorization, "Bearer k3y");
    assert.deepEqual(agent.requests[0].body, { thread_id: "t-1", messages });
  } finally {
    await agent.close();
  }
});

test("agentTitler: 404 (disabled) and 422 (no usable title) reject with the status; a hung agent times out", async () => {
  for (const status of [404, 422]) {
    const agent = await startTitleServer(status, '{"detail":"quoted model text"}');
    try {
      await assert.rejects(agentTitler(agent.agentUrl, "k")("t", [{ role: "user", content: "hi" }]),
        (e: unknown) => e instanceof TitleUnavailable && e.status === status && !e.message.includes("quoted"));
    } finally {
      await agent.close();
    }
  }
  const hung = await startTitleServer(200, "", true);
  try {
    await assert.rejects(agentTitler(hung.agentUrl, "k", fetch, 50)("t", [{ role: "user", content: "hi" }]),
      (e: unknown) => e instanceof Error && e.name === "TimeoutError");
  } finally {
    await hung.close();
  }
});
