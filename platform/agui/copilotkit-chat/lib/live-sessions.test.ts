// The page's live sessions (decision 40, spec §6 *A session's agent*, *Leaving a running chat*): which
// session ids need a mounted holder component (the open one, plus every one this page streams), and when
// leaving the list while streaming should start a new session once its run ends. Pure: no React, no clock.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  EMPTY, held, isHeld, listed, openSession, runEnded, runningIds, runStarted,
} from "./live-sessions.ts";

test("keeps a running session held after a switch, drops it at its run's end", () => {
  let live = openSession(EMPTY, "A");
  live = runStarted(live, "A");
  live = openSession(live, "B");
  assert.deepEqual(held(live), ["B", "A"]);
  const ended = runEnded(live, "A");
  assert.deepEqual(held(ended.live), ["B"]);
  assert.equal(ended.startNew, false);
});

test("the open session stays held after its run ends", () => {
  let live = openSession(EMPTY, "A");
  live = runStarted(live, "A");
  const ended = runEnded(live, "A");
  assert.deepEqual(held(ended.live), ["A"]);
  assert.equal(ended.startNew, false);
});

test("a streaming session that leaves the list keeps its holder until its run ends", () => {
  let live = openSession(EMPTY, "A");
  live = listed(live, new Set(["A"])).live;
  live = runStarted(live, "A");
  const afterList = listed(live, new Set());
  assert.deepEqual(held(afterList.live), ["A"]);
  assert.equal(afterList.startNew, false);
  const ended = runEnded(afterList.live, "A");
  assert.deepEqual(held(ended.live), []);
  assert.equal(ended.startNew, true);
});

test("an open session deleted elsewhere while idle starts a new one", () => {
  let live = openSession(EMPTY, "A");
  live = listed(live, new Set(["A"])).live;
  const result = listed(live, new Set());
  assert.equal(result.startNew, true);
});

test("a streaming session never listed is not dropped by a list without it (ruling 4)", () => {
  let live = openSession(EMPTY, "A");
  live = runStarted(live, "A");
  live = openSession(live, "B");
  const result = listed(live, new Set());
  assert.deepEqual(held(result.live), ["B", "A"]);
});

test("runningIds joins the list's running and the page's streaming", () => {
  let live = openSession(EMPTY, "A");
  live = runStarted(live, "B"); // streaming in this page, not (yet) marked running by the list
  const list = [
    { id: "A", running: false },
    { id: "C", running: true },
  ];
  assert.deepEqual([...runningIds(list, live)].sort(), ["B", "C"]);
});

test("isHeld agrees with held()", () => {
  let live = openSession(EMPTY, "A");
  live = runStarted(live, "A");
  live = openSession(live, "B");
  assert.equal(isHeld(live, "A"), true);
  assert.equal(isHeld(live, "B"), true);
  assert.equal(isHeld(live, "C"), false);
});

test("EMPTY holds nothing", () => {
  assert.deepEqual(held(EMPTY), []);
  assert.equal(isHeld(EMPTY, "A"), false);
  assert.deepEqual([...runningIds([], EMPTY)], []);
});
