import assert from "node:assert/strict";
import { test } from "node:test";
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
function fakeAgent() {
  let s: Parameters<RunSource["subscribe"]>[0] = {};
  const agent: RunSource = { subscribe: (x) => { s = x; return { unsubscribe: () => { s = {}; } }; } };
  return { agent, start: () => s.onRunInitialized?.(), end: () => s.onRunFinalized?.() };
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
    id: ID, fetchList, onList: () => {}, onError: () => {}, onStarted: () => {}, onRecorded: () => {},
    onEnded: (id) => ended.push(id),
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
