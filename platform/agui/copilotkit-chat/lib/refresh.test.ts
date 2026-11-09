// The list's refresh (spec §6 *Refresh*, decision 44): poll every POLL_MS while the list shows a session
// running that no holder in this page streams (a run from another tab, or from before a reload).
import { test } from "node:test";
import assert from "node:assert/strict";
import { EMPTY, runStarted } from "./live-sessions.ts";
import { POLL_MS, afterListApplied, needsPoll, stillFailed } from "./refresh.ts";
import { LIST_FAILED } from "./run-watch.ts";
import type { SessionMeta } from "./sessions.ts";

const row = (id: string, running: boolean): SessionMeta => ({
  id, title: id, tags: [], pinned: false, hidden: false, created_at: "2026-11-09T10:00:00.000Z",
  updated_at: "2026-11-09T10:00:00.000Z", last_run_at: null, running,
});

test("POLL_MS is the spec's 2 s", () => {
  assert.equal(POLL_MS, 2000);
});

test("polls while a running session is not streamed, stops when every running one is", () => {
  const list = [row("A", true), row("B", true), row("C", false)];
  const streamsA = runStarted(EMPTY, "A");
  assert.equal(needsPoll(list, streamsA), true);
  assert.equal(needsPoll(list, runStarted(streamsA, "B")), false);
  assert.equal(needsPoll([row("A", false), row("B", false)], EMPTY), false);
  assert.equal(needsPoll([], EMPTY), false);
});

test("a streamed session the list does not show running does not poll", () => {
  assert.equal(needsPoll([row("A", false)], runStarted(EMPTY, "A")), false);
});

test("a list applied clears the list's own error, and no other", () => {
  assert.equal(afterListApplied("Failed to fetch", "Failed to fetch"), null);
  assert.equal(afterListApplied("“A”: scripted model failure", "Failed to fetch"), "“A”: scripted model failure");
  assert.equal(afterListApplied("Failed to fetch", null), "Failed to fetch");
  assert.equal(afterListApplied(null, "Failed to fetch"), null);
});

test("a list applied also clears a run end's failed list fetch, bare or with its session's title", () => {
  assert.equal(afterListApplied(LIST_FAILED, null), null);
  assert.equal(afterListApplied(`“A”: ${LIST_FAILED}`, null), null);
  assert.equal(afterListApplied(`“A”: ${LIST_FAILED}`, "Failed to fetch"), null);
  assert.equal(afterListApplied("“A”: this session could not be saved", null), "“A”: this session could not be saved");
});

test("a failed rejoin is forgotten once a list shows its session not running, or not at all", () => {
  const failed = new Set(["a", "b", "c"]);
  const next = stillFailed(failed, [row("a", true), row("b", false)]);
  assert.deepEqual([...next], ["a"]);
  const same = new Set(["a"]);
  assert.equal(stillFailed(same, [row("a", true)]), same, "unchanged: the same set");
});
