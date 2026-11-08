import assert from "node:assert/strict";
import { test } from "node:test";
import type { Fetch } from "./client.ts";
// Node-only: the recorder is never imported by the browser module; the test pins the copies.
import { REFUSAL_MESSAGES } from "./recorder.ts";
import type { SessionMeta } from "./sessions.ts";
import {
  RECONCILE_DELAY_MS, REFUSED_RUN_MESSAGES, SAVE_FAILED_MESSAGE, TitleTrigger, clockOffset, fetchSessionList,
  RECONCILE_RETRIES, isRefusal, reconcile, serverRunStart, showsRun, waitListed,
} from "./reconcile.ts";

const ID = "6f1c0d2e-4b1a-4c3d-8e9f-0a1b2c3d4e5f";
const START = Date.parse("2026-10-29T10:00:00.000Z");
// The browser's start time; with offset 0 the clocks agree.
const BROWSER_START = START;
// A session whose last recorded run ended at `ran`; `updated_at` as late as that, or later.
const row = (ran: string | null, id = ID, updated = ran ?? "2026-10-29T08:00:00.000Z"): SessionMeta => ({
  id, title: "t", tags: [], pinned: false, hidden: false, created_at: updated, updated_at: updated, last_run_at: ran,
});

test("showsRun: the session present with last_run_at not older than the run's start", () => {
  assert.equal(showsRun([row("2026-10-29T10:00:00.000Z")], ID, START), true);
  assert.equal(showsRun([row("2026-10-29T10:00:05.000Z")], ID, START), true);
  assert.equal(showsRun([row("2026-10-29T09:59:59.999Z")], ID, START), false);
  assert.equal(showsRun([row("2026-10-29T10:00:05.000Z", "other")], ID, START), false);
  assert.equal(showsRun([], ID, START), false);
});

test("showsRun: a metadata change during the run (updated_at moved, no new run) is not this run's save", () => {
  assert.equal(showsRun([row("2026-10-29T09:00:00.000Z", ID, "2026-10-29T10:00:03.000Z")], ID, START), false);
  assert.equal(showsRun([row(null, ID, "2026-10-29T10:00:03.000Z")], ID, START), false);
});

test("clockOffset and serverRunStart: a browser clock 30 s fast does not lose the run", () => {
  const browserNow = Date.parse("2026-10-29T10:00:30.000Z");
  const offset = clockOffset("Thu, 29 Oct 2026 10:00:00 GMT", browserNow);
  assert.equal(offset, -30_000);
  assert.equal(serverRunStart(browserNow, offset), START);
  // The browser saw the run start at 10:00:30 by its clock; the server saved at 10:00:02.
  assert.equal(showsRun([row("2026-10-29T10:00:02.000Z")], ID, serverRunStart(browserNow, offset)), true);
  assert.equal(clockOffset(null, browserNow), 0);
  assert.equal(clockOffset("garbage", browserNow), 0);
});

test("reconcile: a save that lands on the third fetch is found, two sleeps of 500 ms", async () => {
  const answers = [[], [row("2026-10-29T09:00:00.000Z")], [row("2026-10-29T10:00:01.000Z")]];
  const sleeps: number[] = [];
  let calls = 0;
  const result = await reconcile(async () => ({ list: answers[calls++], serverOffsetMs: 0 }), ID, BROWSER_START,
    async (ms) => { sleeps.push(ms); });
  assert.equal(result.saved, true);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [RECONCILE_DELAY_MS, RECONCILE_DELAY_MS]);
  assert.equal(result.list[0].updated_at, "2026-10-29T10:00:01.000Z");
});

test("reconcile: each fetch's own clock offset converts the browser's start", async () => {
  // Browser clock 30 s fast: it saw the run start at 10:00:30; the server saved at 10:00:02.
  const result = await reconcile(async () => ({ list: [row("2026-10-29T10:00:02.000Z")], serverOffsetMs: -30_000 }),
    ID, START + 30_000, async () => assert.fail("no sleep expected"));
  assert.equal(result.saved, true);
});

test("reconcile: the previous run's save, 1.5 s before this run's start, is not this run", async () => {
  // Clocks agree. Second case, the Date header's rounding at its worst: the run starts at
  // 10:00:00.999 and the header says 10:00:00, so the offset is 999 ms too small.
  for (const [browserStart, serverOffsetMs] of [
    [START, 0],
    [START + 999, clockOffset("Thu, 29 Oct 2026 10:00:00 GMT", START + 999)],
  ]) {
    const previous = [row(new Date(browserStart - 1500).toISOString())];
    let calls = 0;
    const result = await reconcile(async () => { calls++; return { list: previous, serverOffsetMs }; }, ID,
      browserStart, async () => {});
    assert.deepEqual([result.saved, calls], [false, 6], previous[0].updated_at);
  }
});

test("reconcile: shown at once, no retry", async () => {
  let calls = 0;
  const result = await reconcile(async () => { calls++; return { list: [row("2026-10-29T10:00:01.000Z")], serverOffsetMs: 0 }; },
    ID, BROWSER_START, async () => assert.fail("no sleep expected"));
  assert.deepEqual([result.saved, calls], [true, 1]);
});

test("reconcile: never shown gives up after one fetch and five retries", async () => {
  let calls = 0;
  const result = await reconcile(async () => { calls++; return { list: [], serverOffsetMs: 0 }; }, ID, BROWSER_START, async () => {});
  assert.deepEqual([result.saved, calls], [false, 6]);
  assert.equal(SAVE_FAILED_MESSAGE, "this session could not be saved");
});

test("reconcile: a failing fetch is the caller's error, not a save failure", async () => {
  await assert.rejects(reconcile(async () => { throw new Error("Loading the sessions failed (500)"); }, ID, BROWSER_START, async () => {}),
    /failed \(500\)/);
});

test("isRefusal: the recorder's admission errors, nothing else", () => {
  for (const m of REFUSED_RUN_MESSAGES) assert.equal(isRefusal(m), true, m);
  assert.equal(isRefusal("scripted model failure (the message asked for it)"), false);
});

test("REFUSED_RUN_MESSAGES are the recorder's refusal messages, all of them", () => {
  assert.deepEqual([...REFUSED_RUN_MESSAGES], [...REFUSAL_MESSAGES]);
});

test("fetchSessionList: list and offset from one GET; a non-200 throws", async () => {
  const ok: Fetch = async () => new Response(JSON.stringify([row("2026-10-29T10:00:01.000Z")]), {
    status: 200, headers: { "content-type": "application/json", date: new Date(Date.now() + 60_000).toUTCString() },
  });
  const { list, serverOffsetMs } = await fetchSessionList(ok);
  assert.equal(list.length, 1);
  assert.ok(serverOffsetMs > 58_000 && serverOffsetMs <= 60_000, String(serverOffsetMs));
  const bad: Fetch = async () => new Response('{"error":"x"}', { status: 500 });
  await assert.rejects(fetchSessionList(bad), /failed \(500\)/);
});

test("TitleTrigger: once per session started here, at its first run's start; re-armed by started()", () => {
  const titles = new TitleTrigger();
  titles.started(ID);
  assert.equal(titles.take("other"), false); // a session from before this page load
  assert.equal(titles.take(ID), true);
  assert.equal(titles.take(ID), false); // at most once
  titles.started(ID); // its run was never listed: the next run asks again
  assert.equal(titles.take(ID), true);
});

test("waitListed: fetches until the list has the session, RECONCILE_DELAY_MS apart", async () => {
  const answers = [[], [row(null, "other")], [row(null)]];
  let calls = 0;
  const sleeps: number[] = [];
  const result = await waitListed(async () => ({ list: answers[calls++], serverOffsetMs: 0 }), ID,
    async (ms) => { sleeps.push(ms); });
  assert.equal(result.listed, true);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [RECONCILE_DELAY_MS, RECONCILE_DELAY_MS]);
  assert.equal(result.list[0].id, ID);
});

test("waitListed: gives up after RECONCILE_RETRIES more fetches, with the last list", async () => {
  let calls = 0;
  const result = await waitListed(async () => { calls++; return { list: [row(null, "other")], serverOffsetMs: 0 }; },
    ID, async () => {});
  assert.equal(result.listed, false);
  assert.equal(calls, RECONCILE_RETRIES + 1);
  assert.equal(result.list[0].id, "other");
});
