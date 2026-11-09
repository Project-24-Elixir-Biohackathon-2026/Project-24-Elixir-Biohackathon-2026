import assert from "node:assert/strict";
import { test } from "node:test";
import type { Message } from "@ag-ui/client";
import type { SessionMeta } from "./sessions.ts";
import type { ListResult } from "./reconcile.ts";
import { watchRuns } from "./run-watch.ts";
import type { RunSource, RunWatchOptions } from "./run-watch.ts";

const ID = "6f1c0d2e-4b1a-4c3d-8e9f-0a1b2c3d4e5f";
const row = (ran: string): SessionMeta => ({
  id: ID, title: "t", tags: [], pinned: false, hidden: false, created_at: ran, updated_at: ran, last_run_at: ran,
  running: false,
});

// A fake agent: the test fires its run events by hand.
function fakeAgent(messages: Message[] = []) {
  let s: Parameters<RunSource["subscribe"]>[0] = {};
  const sets: Message[][] = [];
  const agent: RunSource = {
    messages,
    setMessages: (m) => { sets.push(m); agent.messages = m; },
    subscribe: (x) => { s = x; return { unsubscribe: () => { s = {}; } }; },
  };
  return { agent, sets, start: () => s.onRunInitialized?.(), end: () => s.onRunFinalized?.() };
}

// A list fetch the test answers by hand, one pending call at a time.
function manualFetch() {
  const pending: ((r: ListResult) => void)[] = [];
  const fetchList = () => new Promise<ListResult>((r) => pending.push(r));
  const answer = () => pending.shift()!({ list: [row(new Date(Date.now() + 60_000).toISOString())], serverOffsetMs: 0 });
  return { fetchList, answer, pending };
}

const tick = () => new Promise((r) => setImmediate(r));

function options(fetchList: RunWatchOptions["fetchList"], ended: string[]): RunWatchOptions {
  return {
    id: ID, fetchList, fetchMessages: async () => null, onList: () => {}, onError: () => {}, onStarted: () => {},
    onRecorded: () => {}, onEnded: (id) => ended.push(id),
  };
}

test("watchRuns: a run's end calls onEnded once its list has come back", async () => {
  const { agent, start, end } = fakeAgent();
  const f = manualFetch();
  const ended: string[] = [];
  watchRuns(agent, () => options(f.fetchList, ended));
  start();
  end();
  await tick();
  assert.deepEqual(ended, []);
  f.answer();
  await tick();
  assert.deepEqual(ended, [ID]);
});

test("watchRuns: a run started before the previous run's list came back is not ended by it", async () => {
  const { agent, start, end } = fakeAgent();
  const f = manualFetch();
  const ended: string[] = [];
  watchRuns(agent, () => options(f.fetchList, ended));
  start();
  end();
  start(); // the second run, while the first one's list is pending
  f.answer();
  await tick();
  assert.deepEqual(ended, [], "the first run's list must not end the session while the second streams");
  end();
  await tick();
  f.answer();
  await tick();
  assert.deepEqual(ended, [ID]);
});

// A rejoined run (connect): the page does not know its start, so its end waits for the list to show the
// session not running (lib/reconcile.ts, waitNotRunning), not for a `last_run_at` after the connect.
const listed = (running: boolean): ListResult => ({ list: [{ ...row("2026-01-01T00:00:00.000Z"), running }], serverOffsetMs: 0 });

test("watchRuns: a rejoined run ends once the list shows the session not running", async () => {
  const { agent, start, end } = fakeAgent();
  const answers = [listed(false)];
  const ended: string[] = [];
  const recorded: string[] = [];
  const errors: string[] = [];
  const w = watchRuns(agent, () => ({
    ...options(async () => answers.shift()!, ended),
    onRecorded: (id) => recorded.push(id), onError: (m) => errors.push(m),
  }));
  w.rejoining();
  start();
  end();
  await tick();
  await tick();
  // A `last_run_at` older than the connect would have failed reconcile(); waitNotRunning takes it.
  assert.deepEqual({ ended, recorded, errors }, { ended: [ID], recorded: [ID], errors: [] });
});

test("watchRuns: a rejoined run whose session left the list ends with no error", async () => {
  const { agent, start, end } = fakeAgent();
  const ended: string[] = [];
  const lists: number[] = [];
  const errors: string[] = [];
  const w = watchRuns(agent, () => ({
    ...options(async () => ({ list: [], serverOffsetMs: 0 }), ended),
    onList: (l) => lists.push(l.length), onError: (m) => errors.push(m),
  }));
  w.rejoining();
  start();
  end();
  await tick();
  await tick();
  assert.deepEqual({ ended, lists, errors }, { ended: [ID], lists: [0], errors: [] });
});

test("watchRuns: only the run a rejoin starts is a rejoin; a connect that never started one leaves none", async () => {
  const { agent, start, end } = fakeAgent();
  const f = manualFetch();
  const ended: string[] = [];
  const w = watchRuns(agent, () => options(f.fetchList, ended));
  w.rejoining();
  w.rejoined(); // the connect failed before its run started
  start(); // an ordinary send: reconcile(), which a list with a fresh last_run_at satisfies at once
  end();
  await tick();
  f.answer();
  await tick();
  assert.deepEqual(ended, [ID]);
  assert.equal(f.pending.length, 0);
});

// At a rejoined run's end the chat is set to the journal's messages (GET) when they differ: the replay may have
// appended past runs the runtime holds in memory on a branch the journal's tip has left.
const msg = (id: string, content: string): Message => ({ id, role: "user", content });

async function rejoinedEnd(shown: Message[], fetchMessages: RunWatchOptions["fetchMessages"], restart = false) {
  const { agent, sets, start, end } = fakeAgent(shown);
  const ended: string[] = [];
  const errors: string[] = [];
  let release!: () => void;
  const gate = new Promise<void>((r) => { release = r; });
  const w = watchRuns(agent, () => ({
    ...options(async () => listed(false), ended),
    fetchMessages: async (id) => { await gate; return fetchMessages(id); },
    onError: (m) => errors.push(m),
  }));
  w.rejoining();
  start();
  end();
  if (restart) { await tick(); start(); } // a send while the end's GET is pending
  release();
  for (let i = 0; i < 5; i++) await tick();
  return { sets, ended, errors };
}

test("watchRuns: a rejoined run's end sets the journal's messages when the chat's differ", async () => {
  const journal = [msg("a", "q"), msg("b", "answer")];
  const r = await rejoinedEnd([msg("a", "q"), msg("x", "a past branch"), msg("b", "answer")], async () => journal);
  assert.deepEqual(r, { sets: [journal], ended: [ID], errors: [] });
});

test("watchRuns: a rejoined run's end leaves the messages when they equal the journal's", async () => {
  const journal = [msg("a", "q"), msg("b", "answer")];
  const r = await rejoinedEnd(structuredClone(journal), async () => journal);
  assert.deepEqual(r, { sets: [], ended: [ID], errors: [] });
});

test("watchRuns: a rejoined run's end keeps the chat, with no error, when its GET fails or finds nothing", async () => {
  const shown = [msg("a", "q"), msg("x", "a past branch")];
  const failed = await rejoinedEnd(shown, async () => { throw new Error("Failed to fetch"); });
  assert.deepEqual(failed, { sets: [], ended: [ID], errors: [] });
  const gone = await rejoinedEnd(shown, async () => null);
  assert.deepEqual(gone, { sets: [], ended: [ID], errors: [] });
});

test("watchRuns: a rejoined run's end does not set messages once a newer run has started", async () => {
  const r = await rejoinedEnd([msg("a", "q"), msg("x", "past")], async () => [msg("a", "q")], true);
  assert.deepEqual(r.sets, []);
});
