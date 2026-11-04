// What the session recorder relies on in @ag-ui/client and @copilotkit/runtime: AG-UI
// middleware attached with agent.use() survives the runtime's per-request clone(), keeps
// per-run state per clone, and sees the stop button (abortRun) as RUN_ERROR with code "abort".
import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { EventType, HttpAgent, Middleware } from "@ag-ui/client";
import type { AbstractAgent, BaseEvent, Message, RunAgentInput } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { finalize, map, tap } from "rxjs";
import type { Observable } from "rxjs";
import { startTestAgent } from "./test-agent.ts";

type Seen = { threadId: string; types: string[]; messages: Message[]; errorCode?: string; nextIsAgent: boolean };

class Probe extends Middleware {
  seen: Seen[] = [];
  onEvent: (event: BaseEvent) => void = () => {};
  run(input: RunAgentInput, next: AbstractAgent): Observable<BaseEvent> {
    // per run, in this closure
    const state: Seen = { threadId: input.threadId, types: [], messages: [], nextIsAgent: next instanceof HttpAgent };
    return this.runNextWithState(input, next).pipe(
      tap(({ event, messages }) => {
        state.types.push(event.type);
        state.messages = messages;
        if (event.type === EventType.RUN_ERROR) state.errorCode = (event as any).code;
        this.onEvent(event);
      }),
      map(({ event }) => event),
      finalize(() => this.seen.push(state)),
    );
  }
}

function user(id: string, content: string): Message {
  return { id, role: "user", content } as Message;
}

test("middleware survives clone() and keeps per-run state per clone", async () => {
  const server = await startTestAgent(50);
  try {
    const probe = new Probe();
    const agent = new HttpAgent({ url: server.url });
    agent.use(probe);
    const a = agent.clone();
    const b = agent.clone();
    a.threadId = "thread-a";
    a.setMessages([user("u-a", "first question")]);
    b.threadId = "thread-b";
    b.setMessages([user("u-b", "second question")]);
    await Promise.all([a.runAgent({ runId: "run-a" }), b.runAgent({ runId: "run-b" })]);

    assert.equal(probe.seen.length, 2);
    const byThread = Object.fromEntries(probe.seen.map((s) => [s.threadId, s]));
    for (const [thread, question] of [["thread-a", "first question"], ["thread-b", "second question"]]) {
      const s = byThread[thread];
      assert.equal(s.types[0], EventType.RUN_STARTED);
      assert.equal(s.types.at(-1), EventType.RUN_FINISHED);
      assert.deepEqual(
        s.messages.map((m) => [m.role, m.content]),
        [["user", question], ["assistant", `echo: ${question}`]],
      );
    }
  } finally {
    await server.close();
  }
});

test("abortRun() mid-stream reaches the middleware as RUN_ERROR with code abort", async () => {
  const server = await startTestAgent();
  try {
    const probe = new Probe();
    const agent = new HttpAgent({ url: server.url });
    agent.use(probe);
    const c = agent.clone();
    c.threadId = "thread-c";
    c.setMessages([user("u-c", "please hang")]);
    probe.onEvent = (event) => {
      if (event.type === EventType.TEXT_MESSAGE_CONTENT) c.abortRun();
    };
    await c.runAgent({ runId: "run-c" }).catch(() => {});
    assert.equal(probe.seen.length, 1);
    const s = probe.seen[0];
    assert.equal(s.types.at(-1), EventType.RUN_ERROR);
    assert.equal(s.errorCode, "abort");
  } finally {
    await server.close();
  }
});

test("through the CopilotKit runtime handler, each request's clone keeps the middleware and its own state", async () => {
  const server = await startTestAgent(50);
  try {
    const probe = new Probe();
    const spe = new HttpAgent({ url: server.url });
    spe.use(probe);
    const handler = createCopilotRuntimeHandler({
      runtime: new CopilotRuntime({ agents: { spe } }),
      basePath: "/api/copilotkit",
    });
    const post = (threadId: string, question: string) =>
      handler(new Request("http://chat-ui/api/copilotkit/agent/spe/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          threadId, runId: randomUUID(), state: {}, tools: [], context: [], forwardedProps: {},
          messages: [user(randomUUID(), question)],
        }),
      })).then(async (response) => {
        assert.equal(response.status, 200);
        return response.text(); // the whole SSE stream
      });
    const [a, b] = [randomUUID(), randomUUID()];
    await Promise.all([post(a, "first through the runtime"), post(b, "second through the runtime")]);
    for (let i = 0; i < 100 && probe.seen.length < 2; i++) await new Promise((r) => setTimeout(r, 10));

    assert.equal(server.requests.length, 2);
    assert.equal(probe.seen.length, 2);
    const byThread = Object.fromEntries(probe.seen.map((s) => [s.threadId, s]));
    for (const [thread, question] of [[a, "first through the runtime"], [b, "second through the runtime"]]) {
      const s = byThread[thread];
      assert.equal(s.types.at(-1), EventType.RUN_FINISHED);
      assert.deepEqual(
        s.messages.map((m) => [m.role, m.content]),
        [["user", question], ["assistant", `echo: ${question}`]],
      );
      // `next` is the client's wrapper around the rest of the chain, not the agent: a
      // middleware cannot call abortRun() on it.
      assert.equal(s.nextIsAgent, false);
    }
  } finally {
    await server.close();
  }
});
