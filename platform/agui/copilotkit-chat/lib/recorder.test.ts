// The session recorder: admission, one test per way a run can end, metadata changed during a
// run, failed saves, shutdown, and keys kept out of session files.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { EventType, HttpAgent } from "@ag-ui/client";
import type { BaseEvent, Message, RunAgentInput } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { Observable } from "rxjs";
import type { Subscriber } from "rxjs";
import { REFUSAL_MESSAGES, SAVE_FAILED, SessionRecorder } from "./recorder.ts";
import { SessionStore, shared } from "./sessions.ts";
import type { RunEntry, SessionRecord } from "./sessions.ts";
import { startTestAgent } from "./test-agent.ts";
import type { TestAgent } from "./test-agent.ts";

async function setup(delayMs = 0) {
  const store = new SessionStore(await fs.mkdtemp(path.join(os.tmpdir(), "recorder-")));
  const server = await startTestAgent(delayMs);
  const recorder = new SessionRecorder(() => store);
  // As the CopilotKit route builds `spe`: the recorder's fetch lets it close the agent request.
  return { store, server, recorder, agent: () => new HttpAgent({ url: server.url, fetch: recorder.fetch }) };
}

// The agent saw its connection close (the request was aborted, not left running).
async function closedByClient(server: TestAgent, index = 0): Promise<boolean> {
  for (let i = 0; i < 100 && !server.requests[index]?.closed; i++) await new Promise((r) => setTimeout(r, 10));
  return server.requests[index]?.closed === true;
}

// Waits until the agent has received n requests; fails the test after 5 s instead of hanging.
async function requestsReach(server: TestAgent, n: number): Promise<void> {
  const deadline = Date.now() + 5000;
  while (server.requests.length < n && Date.now() < deadline) await new Promise((r) => setTimeout(r, 5));
  assert.ok(server.requests.length >= n, `the agent got ${server.requests.length} of ${n} requests within 5 s`);
}

function input(threadId: string, text: string, history: Message[] = []): RunAgentInput {
  return {
    threadId, runId: randomUUID(), state: {}, tools: [], context: [], forwardedProps: {},
    messages: [...history, { id: randomUUID(), role: "user", content: text } as Message],
  };
}

type Outcome = { events: BaseEvent[]; error?: unknown };

// Calls the recorder as AbstractAgent.runAgent does, on an agent prepared as the runtime prepares
// its per-request clone (runNextWithState applies events to the agent's own messages).
// `stopWhen` unsubscribes right after the matching event.
function drive(
  recorder: SessionRecorder, runInput: RunAgentInput, agent: HttpAgent,
  stopWhen?: (event: BaseEvent) => boolean,
): Promise<Outcome> {
  agent.threadId = runInput.threadId;
  agent.setMessages(runInput.messages);
  return new Promise((resolve) => {
    const events: BaseEvent[] = [];
    const sub = recorder.run(runInput, agent).subscribe({
      next: (event) => {
        events.push(event);
        if (stopWhen?.(event)) {
          queueMicrotask(() => {
            sub.unsubscribe();
            resolve({ events });
          });
        }
      },
      error: (error) => resolve({ events, error }),
      complete: () => resolve({ events }),
    });
  });
}

// A save after unsubscription lands after drive() returns: wait for the session's queue.
async function settled(id: string): Promise<void> {
  for (let i = 0; i < 100 && (shared().running.has(id) || shared().queue.has(id)); i++) {
    await new Promise((r) => setTimeout(r, 10));
  }
}

async function onlyRun(store: SessionStore, id: string): Promise<[SessionRecord, RunEntry]> {
  const record = (await store.read(id)) as SessionRecord;
  assert.equal(record.runs.length, 1, "exactly one runs[] entry");
  return [record, record.runs[0]];
}

const types = (o: Outcome) => o.events.map((e) => e.type);

test("RUN_FINISHED: completed, messages, auto title, a schema-valid version-1 file", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    const runInput = input(id, "list the home directory");
    const out = await drive(recorder, runInput, agent());
    assert.equal(types(out).at(-1), EventType.RUN_FINISHED);
    const [record, run] = await onlyRun(store, id);
    assert.deepEqual(Object.keys(record).sort(), [
      "created_at", "deleted_at", "hidden", "id", "messages", "pinned", "runs", "tags", "title",
      "title_source", "updated_at", "version",
    ]);
    assert.equal(record.version, 1);
    assert.equal(record.id, id);
    assert.deepEqual([record.title, record.title_source, record.tags, record.pinned, record.hidden, record.deleted_at],
      ["list the home directory", "auto", [], false, false, null]);
    for (const stamp of [record.created_at, record.updated_at, run.started_at, run.ended_at]) {
      assert.match(stamp, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);
    }
    assert.deepEqual(Object.keys(run).sort(), ["ended_at", "run_id", "started_at", "status"]);
    assert.deepEqual([run.run_id, run.status], [runInput.runId, "completed"]);
    assert.deepEqual(record.messages.map((m) => [m.role, m.content]),
      [["user", "list the home directory"], ["assistant", "echo: list the home directory"]]);
    assert.equal(shared().running.has(id), false);
  } finally {
    await server.close();
  }
});

for (const [name, text, expected] of [
  ["RUN_ERROR", "error please", "failed"],
  ["an HTTP error from the agent before any event", "boom", "failed"],
  ["a stream error (connection lost)", "crash now", "failed"],
  ["EOF without a terminal event", "eof now", "failed"],
] as const) {
  test(`${name}: ${expected}, recorded once`, async () => {
    const { store, server, recorder, agent } = await setup();
    try {
      const id = randomUUID();
      await drive(recorder, input(id, text), agent());
      await settled(id);
      const [record, run] = await onlyRun(store, id);
      assert.equal(run.status, expected);
      assert.equal(record.messages[0].content, text);
    } finally {
      await server.close();
    }
  });
}

test("unsubscribed before a terminal event: cancelled, partial answer kept, agent request closed", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "hang on"), agent(), (e) => e.type === EventType.TEXT_MESSAGE_CONTENT);
    await settled(id);
    const [record, run] = await onlyRun(store, id);
    assert.equal(run.status, "cancelled");
    assert.deepEqual(record.messages.map((m) => m.role), ["user", "assistant"]);
    assert.equal(await closedByClient(server), true);
  } finally {
    await server.close();
  }
});

test("the stop button (abortRun, RUN_ERROR code abort): cancelled", async () => {
  const { store, server, recorder } = await setup();
  try {
    const id = randomUUID();
    const base = new HttpAgent({ url: server.url, fetch: recorder.fetch });
    base.use(recorder);
    const clone = base.clone(); // as the runtime does per request
    clone.threadId = id;
    clone.setMessages(input(id, "hang until stopped").messages);
    await clone.runAgent({ runId: randomUUID() }, {
      onEvent: ({ event }) => {
        if (event.type === EventType.TEXT_MESSAGE_CONTENT) clone.abortRun();
      },
    }).catch(() => {});
    await settled(id);
    const [, run] = await onlyRun(store, id);
    assert.equal(run.status, "cancelled");
  } finally {
    await server.close();
  }
});

test("a terminal event followed by unsubscription: completed, exactly one entry", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "quick"), agent(), (e) => e.type === EventType.RUN_FINISHED);
    await settled(id);
    const [, run] = await onlyRun(store, id);
    assert.equal(run.status, "completed");
  } finally {
    await server.close();
  }
});

test("refused runs: RUN_STARTED then RUN_ERROR, the agent never called, nothing written", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const deleted = randomUUID();
    await drive(recorder, input(deleted, "first"), agent());
    await store.softDelete(deleted, new Date());
    const before = await fs.readFile(path.join(store.dir, `${deleted}.json`), "utf8");
    const calls = server.requests.length;
    const unreadable = randomUUID();
    const broken = '{"version":1,"title":not json';
    await fs.writeFile(path.join(store.dir, `${unreadable}.json`), broken);
    const logged = mock.method(console, "error", () => {});
    try {
      for (const [id, message] of [
        ["../x", "invalid session"],
        ["6F1C0D2E-1234-4ABC-8DEF-0123456789AB", "invalid session"],
        [deleted, "this session was deleted"],
        [unreadable, "this session could not be read"],
      ]) {
        const out = await drive(recorder, input(id, "again"), agent());
        assert.deepEqual(types(out), [EventType.RUN_STARTED, EventType.RUN_ERROR]);
        assert.equal((out.events[1] as { message?: string }).message, message);
        assert.ok(REFUSAL_MESSAGES.includes(message), message);
      }
    } finally {
      logged.mock.restore();
    }
    assert.equal(server.requests.length, calls);
    assert.deepEqual((await fs.readdir(store.dir)).sort(), [`${deleted}.json`, `${unreadable}.json`].sort());
    assert.equal(await fs.readFile(path.join(store.dir, `${deleted}.json`), "utf8"), before);
    assert.equal(await fs.readFile(path.join(store.dir, `${unreadable}.json`), "utf8"), broken);
  } finally {
    await server.close();
  }
});

test("a second run on a running session is refused and never reaches the agent", async () => {
  const { store, server, recorder, agent } = await setup(200);
  try {
    const id = randomUUID();
    const first = drive(recorder, input(id, "slow first"), agent());
    await requestsReach(server, 1);
    const second = await drive(recorder, input(id, "second"), agent());
    assert.deepEqual(types(second), [EventType.RUN_STARTED, EventType.RUN_ERROR]);
    assert.equal((second.events[1] as { message?: string }).message, "this session is already running");
    await first;
    assert.equal(server.requests.length, 1);
    const [record] = await onlyRun(store, id);
    assert.equal(record.messages[0].content, "slow first");
  } finally {
    await server.close();
  }
});

test("PATCH and DELETE during a run survive its finalisation", async () => {
  const { store, server, recorder, agent } = await setup(200);
  try {
    const id = randomUUID();
    const first = input(id, "first question");
    await drive(recorder, first, agent());
    const history = ((await store.read(id)) as SessionRecord).messages;
    const running = drive(recorder, input(id, "second question", history), agent());
    await requestsReach(server, 2);
    await store.patch(id, { title: "Renamed", tags: ["dns"] }, new Date());
    await store.softDelete(id, new Date());
    await running;
    const record = (await store.read(id)) as SessionRecord;
    assert.deepEqual([record.title, record.title_source, record.tags], ["Renamed", "user", ["dns"]]);
    assert.notEqual(record.deleted_at, null);
    assert.equal(record.runs.length, 2);
    assert.equal(record.messages.at(-1)?.content, "echo: second question");
    // a later run would be refused: the session is deleted; the title stays the user's
    await drive(recorder, input(id, "third"), agent());
    assert.equal(((await store.read(id)) as SessionRecord).runs.length, 2);
  } finally {
    await server.close();
  }
});

test("a failed save: spe.session_save_failed before the terminal event, logged without content", async () => {
  const { server, store } = await setup();
  try {
    class Failing extends SessionStore {
      async recordRun(): Promise<void> {
        throw new Error("ENOSPC: no space left on device");
      }
    }
    const failing = new Failing(store.dir);
    const recorder = new SessionRecorder(() => failing);
    const logged = mock.method(console, "error", () => {});
    const id = randomUUID();
    let out: Outcome;
    try {
      out = await drive(recorder, input(id, "secret canary text"), new HttpAgent({ url: server.url }));
    } finally {
      logged.mock.restore();
    }
    const tail = out.events.slice(-2);
    assert.deepEqual(tail.map((e) => e.type), [EventType.CUSTOM, EventType.RUN_FINISHED]);
    assert.equal((tail[0] as { name?: string }).name, SAVE_FAILED);
    assert.equal(logged.mock.callCount(), 1);
    assert.doesNotMatch(JSON.stringify(logged.mock.calls[0].arguments), /secret canary text/);
    assert.equal(shared().running.has(id), false);
  } finally {
    await server.close();
  }
});

test("RunHandle.cancel() ends a running session's run as cancelled and closes the agent request", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    const outcome = drive(recorder, input(id, "hang for shutdown"), agent());
    await requestsReach(server, 1);
    shared().running.get(id)?.cancel();
    const out = await outcome;
    const last = out.events.at(-1) as { type: string; code?: string };
    assert.deepEqual([last.type, last.code], [EventType.RUN_ERROR, "cancelled"]);
    const [, run] = await onlyRun(store, id);
    assert.equal(run.status, "cancelled");
    assert.equal(await closedByClient(server), true, "the agent saw its connection close");
  } finally {
    await server.close();
  }
});

test("closing: new runs are refused once shutdown has begun", async () => {
  const { server, recorder, agent } = await setup();
  shared().closing = true;
  try {
    const out = await drive(recorder, input(randomUUID(), "late"), agent());
    assert.deepEqual(types(out), [EventType.RUN_STARTED, EventType.RUN_ERROR]);
    assert.equal((out.events[1] as { message?: string }).message, "the chat UI is shutting down");
    assert.equal(server.requests.length, 0);
  } finally {
    shared().closing = false;
    await server.close();
  }
});

test("closing set while admission's store read is pending: the run is refused, not admitted", async () => {
  const { server } = await setup();
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "recorder-"));
  try {
    // Simulates SIGTERM landing during `await this.store().read(id)`: admit's first `closing`
    // check has already passed, so only a re-check right before `running.set` catches it.
    class ClosesDuringRead extends SessionStore {
      async read(id: string): Promise<SessionRecord | null> {
        const record = await super.read(id);
        shared().closing = true;
        return record;
      }
    }
    const store = new ClosesDuringRead(dir);
    const recorder = new SessionRecorder(() => store);
    const id = randomUUID();
    const out = await drive(recorder, input(id, "late"), new HttpAgent({ url: server.url, fetch: recorder.fetch }));
    assert.deepEqual(types(out), [EventType.RUN_STARTED, EventType.RUN_ERROR]);
    assert.equal((out.events[1] as { message?: string }).message, "the chat UI is shutting down");
    assert.equal(server.requests.length, 0);
    await settled(id);
    assert.equal(shared().running.has(id), false);
    assert.equal(shared().queue.has(id), false);
  } finally {
    shared().closing = false;
    await server.close();
  }
});

test("neither the request's nor the agent's bearer key reaches the session file", async () => {
  const { store, server } = await setup();
  try {
    const k1 = `k1-${randomUUID()}`; // sent by the browser to the runtime
    const k2 = `k2-${randomUUID()}`; // the runtime's agent key, sent to the agent
    const recorder = new SessionRecorder(() => store);
    const spe = new HttpAgent({ url: server.url, headers: { Authorization: `Bearer ${k2}` }, fetch: recorder.fetch });
    spe.use(recorder);
    const handler = createCopilotRuntimeHandler({
      runtime: new CopilotRuntime({ agents: { spe } }),
      basePath: "/api/copilotkit",
    });
    const id = randomUUID();
    const response = await handler(new Request("http://chat-ui/api/copilotkit/agent/spe/run", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${k1}` },
      body: JSON.stringify(input(id, "hello through the runtime")),
    }));
    assert.equal(response.status, 200);
    await response.text(); // the whole SSE stream
    await settled(id);
    assert.equal(server.requests[0].headers.authorization, `Bearer ${k2}`); // the key was in play
    const text = await fs.readFile(path.join(store.dir, `${id}.json`), "utf8");
    assert.doesNotMatch(text, new RegExp(k1));
    assert.doesNotMatch(text, new RegExp(k2));
    const [record, run] = await onlyRun(store, id);
    assert.equal(run.status, "completed");
    assert.equal(record.messages.at(-1)?.content, "echo: hello through the runtime");
  } finally {
    await server.close();
  }
});

test("SPE_SESSIONS_TEST_SAVE_DELAY_MS holds a stopped run's save after the client has gone", async () => {
  const { store, server, recorder, agent } = await setup();
  process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS = "300";
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "hang then stop"), agent(), (e) => e.type === EventType.TEXT_MESSAGE_CONTENT);
    const stopped = Date.now();
    assert.equal(await store.read(id), null); // not yet saved
    await settled(id);
    assert.ok(Date.now() - stopped >= 250, "the save waited for the delay");
    const [, run] = await onlyRun(store, id);
    assert.equal(run.status, "cancelled");
  } finally {
    delete process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS;
    await server.close();
  }
});

test("a run started right after a stopped one is admitted and recorded after it", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "hang then stop"), agent(), (e) => e.type === EventType.TEXT_MESSAGE_CONTENT);
    const next = await drive(recorder, input(id, "right after"), agent());
    assert.equal(types(next).at(-1), EventType.RUN_FINISHED);
    const record = (await store.read(id)) as SessionRecord;
    assert.deepEqual(record.runs.map((r) => r.status), ["cancelled", "completed"]);
    assert.equal(shared().running.has(id), false);
  } finally {
    await server.close();
  }
});

// A recorder whose agent stream is scripted: `script` gets the subscriber, and the run's id, and
// emits on it synchronously, so a test can act between a terminal event reaching the recorder
// and the write queued after it (over HTTP that gap is a few microtasks wide).
class Scripted extends SessionRecorder {
  script: (sub: Subscriber<{ event: BaseEvent; messages: Message[]; state: unknown }>, id: string) => void = () => {};
  runNextWithState(runInput: RunAgentInput): ReturnType<SessionRecorder["runNextWithState"]> {
    return new Observable((sub) => this.script(sub, runInput.threadId)) as ReturnType<SessionRecorder["runNextWithState"]>;
  }
}

test("cancel() after a terminal event, before or during its save: no RUN_ERROR, the terminal's status", async () => {
  const store = new SessionStore(await fs.mkdtemp(path.join(os.tmpdir(), "recorder-")));
  const recorder = new Scripted(() => store);
  process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS = "100";
  try {
    const runInput = input(randomUUID(), "finish then cancel");
    const id = runInput.threadId;
    const ids = { threadId: id, runId: runInput.runId };
    recorder.script = (sub) => {
      const messages = runInput.messages;
      sub.next({ event: { type: EventType.RUN_STARTED, ...ids } as BaseEvent, messages, state: {} });
      sub.next({ event: { type: EventType.RUN_FINISHED, ...ids } as BaseEvent, messages, state: {} });
      const handle = shared().running.get(id);
      handle?.cancel(); // before the write is queued
      setTimeout(() => {
        handle?.cancel(); // while the delayed save runs
        sub.complete();
      }, 30);
    };
    const out = await drive(recorder, runInput, new HttpAgent({ url: "http://127.0.0.1:9/unused" }));
    assert.deepEqual(types(out), [EventType.RUN_STARTED, EventType.RUN_FINISHED]);
    await settled(id);
    const [, run] = await onlyRun(store, id);
    assert.equal(run.status, "completed");
  } finally {
    delete process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS;
  }
});

test("an agent that throws on run() fails the run and leaves the session free for the next one", async () => {
  const { store, server, recorder, agent } = await setup();
  class Throwing extends HttpAgent {
    run(): never {
      throw new Error("agent bug with secret canary text");
    }
  }
  const logged = mock.method(console, "error", () => {});
  try {
    const id = randomUUID();
    let out: Outcome;
    try {
      out = await drive(recorder, input(id, "secret canary text"), new Throwing({ url: server.url }));
    } finally {
      logged.mock.restore();
    }
    assert.ok(out.error instanceof Error, "the run's stream errors");
    await settled(id);
    assert.equal(shared().running.has(id), false);
    assert.ok(logged.mock.callCount() >= 1);
    assert.doesNotMatch(JSON.stringify(logged.mock.calls.map((c) => c.arguments)), /secret canary text/);
    const next = await drive(recorder, input(id, "after the bug"), agent());
    assert.equal(types(next).at(-1), EventType.RUN_FINISHED);
    const record = (await store.read(id)) as SessionRecord;
    assert.deepEqual(record.runs.map((r) => r.status), ["failed", "completed"]);
  } finally {
    await server.close();
  }
});

test("the test agent answers a body that is not JSON with 400", async () => {
  const server = await startTestAgent();
  try {
    const response = await fetch(server.url, { method: "POST", body: "{not json" });
    assert.equal(response.status, 400);
    assert.equal(server.requests.length, 0);
  } finally {
    await server.close();
  }
});
