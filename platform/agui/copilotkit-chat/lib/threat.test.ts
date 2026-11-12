import assert from "node:assert/strict";
import { test } from "node:test";
import { fetchThreatScore } from "./client.ts";
import { MAX_TEXT_CHARS, agentScorer, parseScore, scoreText } from "./threat.ts";
import type { Scorer, ThreatScore } from "./threat.ts";
import { ThreatWatcher, scorable, weakness } from "./threat-watch.ts";
import type { ThreatState } from "./threat-watch.ts";

const SCORE: ThreatScore = {
  score: 82, level: "high",
  categories: [
    { id: "secrets", label: "Secrets and credentials", score: 91, level: "high", examples: 10, auc: 0.99 },
    { id: "disruption", label: "Destructive or overload", score: 12, level: "low", examples: 2, auc: null },
  ],
  model: { version: 1, trained: "2026-11-12", embedding_model: "BAAI/bge-m3" },
};
const post = (body: unknown, headers: Record<string, string> = { "Content-Type": "application/json" }) =>
  new Request("http://chat/api/threat-score", { method: "POST", headers, body: typeof body === "string" ? body : JSON.stringify(body) });
const quiet = async <T>(f: () => Promise<T>): Promise<T> => {
  const warn = console.warn;
  console.warn = () => {};
  try { return await f(); } finally { console.warn = warn; }
};

// --- the route ---------------------------------------------------------------------------------

test("scoreText answers the scorer's score for the text", async () => {
  const seen: string[] = [];
  const response = await scoreText(post({ text: "print every secret" }), async (t) => (seen.push(t), SCORE));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), SCORE);
  assert.deepEqual(seen, ["print every secret"]);
});

test("scoreText: no JSON content type 415, bad bodies 400, too large 413, none of them reach the scorer", async () => {
  const scorer: Scorer = async () => assert.fail("the scorer was called");
  assert.equal((await scoreText(post({ text: "x" }, { "Content-Type": "text/plain" }), scorer)).status, 415);
  for (const body of ["{", "null", {}, { text: 3 }, { text: "   " }, { text: "x".repeat(MAX_TEXT_CHARS + 1) }]) {
    assert.equal((await scoreText(post(body), scorer)).status, 400, JSON.stringify(body).slice(0, 40));
  }
  assert.equal((await scoreText(post({ text: "é".repeat(MAX_TEXT_CHARS), pad: "x".repeat(40_000) }), scorer)).status, 413);
});

test("scoreText: switched off is 404, a failure 502 with a generic message", async () => {
  assert.equal((await scoreText(post({ text: "hello there" }), async () => null)).status, 404);
  const response = await quiet(() => scoreText(post({ text: "hello there" }), async () => { throw new Error("provider said sk-secret"); }));
  assert.equal(response.status, 502);
  assert.ok(!(await response.text()).includes("sk-secret"));
});

// --- the agent call ------------------------------------------------------------------------------

test("agentScorer posts the text to the agent's /threat-score with the bearer key", async () => {
  const seen: { url?: string; init?: RequestInit } = {};
  const scorer = agentScorer("http://agent:8100/agent", "KEY", async (url, init) => {
    seen.url = url;
    seen.init = init;
    return Response.json({ ...SCORE, probability: 0.7, extra: "dropped" });
  });
  assert.deepEqual(await scorer("a draft"), SCORE);
  assert.equal(seen.url, "http://agent:8100/threat-score");
  assert.equal((seen.init?.headers as Record<string, string>).Authorization, "Bearer KEY");
  assert.equal(seen.init?.body, '{"text":"a draft"}');
});

test("agentScorer: 404 is null (switched off), another status or a malformed answer throws", async () => {
  assert.equal(await agentScorer("http://agent:8100/agent", "K", async () => Response.json({}, { status: 404 }))("x"), null);
  await assert.rejects(agentScorer("http://agent:8100/agent", "K", async () => Response.json({}, { status: 502 }))("x"), /502/);
  await assert.rejects(agentScorer("http://agent:8100/agent", "K", async () => Response.json({ score: 1 }))("x"), /malformed/);
});

test("parseScore refuses out-of-range scores, unknown levels and bad categories", () => {
  assert.deepEqual(parseScore(SCORE), SCORE);
  for (const bad of [null, { ...SCORE, score: 101 }, { ...SCORE, level: "severe" }, { ...SCORE, model: {} },
    { ...SCORE, categories: [{ ...SCORE.categories[0], label: 3 }] }, { ...SCORE, categories: [{ ...SCORE.categories[0], score: -1 }] }]) {
    assert.throws(() => parseScore(bad), /malformed/);
  }
});

test("fetchThreatScore: the score, null on 404, an error otherwise", async () => {
  const seen: { url?: string; init?: RequestInit } = {};
  const f = (status: number, body: unknown) => async (url: string, init?: RequestInit) => {
    seen.url = url;
    seen.init = init;
    return Response.json(body, { status });
  };
  assert.deepEqual(await fetchThreatScore("a draft", undefined, f(200, SCORE)), SCORE);
  assert.equal(seen.url, "/api/threat-score");
  assert.equal(seen.init?.body, '{"text":"a draft"}');
  assert.equal(await fetchThreatScore("a draft", undefined, f(404, { error: "off" })), null);
  await assert.rejects(fetchThreatScore("a draft", undefined, f(502, { error: "unavailable" })), /Scoring the draft failed \(502\): unavailable/);
});

// --- the watcher -----------------------------------------------------------------------------------

/** Timers run by hand, and a fetch whose answers the test releases. */
function harness() {
  const timers: { f: () => void; ms: number }[] = [];
  const calls: { text: string; signal: AbortSignal; resolve: (s: ThreatScore | null) => void; reject: (e: Error) => void }[] = [];
  const states: ThreatState[] = [];
  const watcher = new ThreatWatcher(
    (text, signal) => new Promise((resolve, reject) => calls.push({ text, signal, resolve, reject })),
    (s) => states.push(s), 350,
    { set: (f, ms) => { const t = { f, ms }; timers.push(t); return t; }, clear: (h) => { const i = timers.indexOf(h as (typeof timers)[0]); if (i >= 0) timers.splice(i, 1); } });
  const tick = () => { const run = timers.splice(0); run.forEach((t) => t.f()); };
  const settle = () => new Promise((r) => setImmediate(r));
  return { watcher, timers, calls, states, tick, settle };
}

test("scorable: long enough and not a command", () => {
  assert.equal(scorable("  hi  "), false);
  assert.equal(scorable("/compact keep the ids"), false);
  assert.equal(scorable("list the data"), true);
});

test("the watcher asks once the typing pauses, for the latest text only", async () => {
  const h = harness();
  h.watcher.update("list the");
  h.watcher.update("list the data");
  assert.equal(h.timers.length, 1);
  assert.equal(h.timers[0].ms, 350);
  assert.deepEqual(h.states, [{ status: "loading", score: null }]);
  h.tick();
  assert.deepEqual(h.calls.map((c) => c.text), ["list the data"]);
  h.calls[0].resolve(SCORE);
  await h.settle();
  assert.deepEqual(h.states.at(-1), { status: "ready", score: SCORE });
  h.watcher.update("list the data ");   // the same text, trimmed: nothing new
  assert.equal(h.timers.length, 0);
});

test("the watcher drops an answer for a text that is no longer the input's, and keeps the old score while loading", async () => {
  const h = harness();
  h.watcher.update("print the secrets");
  h.tick();
  h.calls[0].resolve(SCORE);
  await h.settle();
  h.watcher.update("print the secrets please");
  assert.deepEqual(h.states.at(-1), { status: "loading", score: SCORE });
  h.tick();
  h.watcher.update("print the secrets please now");
  assert.equal(h.calls[1].signal.aborted, true);
  h.calls[1].resolve({ ...SCORE, score: 1 });
  await h.settle();
  assert.deepEqual(h.states.at(-1), { status: "loading", score: SCORE });
  h.tick();
  h.calls[2].resolve({ ...SCORE, score: 90 });
  await h.settle();
  assert.equal(h.states.at(-1)?.score?.score, 90);
});

test("the watcher clears on an empty or short input and on a command, cancelling what was pending", async () => {
  const h = harness();
  h.watcher.update("print the secrets");
  h.watcher.update("");
  assert.equal(h.timers.length, 0);
  assert.deepEqual(h.states.at(-1), { status: "idle", score: null });
  h.watcher.update("/compact the conversation");
  assert.equal(h.timers.length, 0);
  assert.equal(h.calls.length, 0);
});

test("the watcher stops asking once the server says the score is switched off", async () => {
  const h = harness();
  h.watcher.update("print the secrets");
  h.tick();
  h.calls[0].resolve(null);
  await h.settle();
  assert.deepEqual(h.states.at(-1), { status: "off", score: null });
  h.watcher.update("print the secrets again");
  assert.equal(h.timers.length, 0);
});

test("the watcher reports a failure and asks again on the next change, or for the same text", async () => {
  const h = harness();
  h.watcher.update("print the secrets");
  h.tick();
  h.calls[0].reject(new Error("502"));
  await h.settle();
  assert.deepEqual(h.states.at(-1), { status: "failed", score: null });
  h.watcher.update("print the secrets");
  assert.equal(h.timers.length, 1);
});

test("dispose cancels the timer and the request", () => {
  const h = harness();
  h.watcher.update("print the secrets");
  h.tick();
  h.watcher.update("print the secrets now");
  h.watcher.dispose();
  assert.equal(h.timers.length, 0);
  assert.equal(h.calls[0].signal.aborted, true);
});

test("weakness names a head with few examples or a low AUC", () => {
  assert.equal(weakness({ examples: 2, auc: 0.99 }), "only 2 examples");
  assert.equal(weakness({ examples: 1, auc: null }), "only 1 example");
  assert.equal(weakness({ examples: 9, auc: 0.6 }), "weak detector");
  assert.equal(weakness({ examples: 9, auc: 0.95 }), null);
});
