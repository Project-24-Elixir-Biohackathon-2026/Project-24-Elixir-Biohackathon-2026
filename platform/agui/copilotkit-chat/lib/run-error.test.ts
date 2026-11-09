// A run error in the error bar (spec §6 *Errors*): bare for the open session, with its session's title first
// for one that is not open.
import { test } from "node:test";
import assert from "node:assert/strict";
import { runErrorText } from "./run-error.ts";

test("runErrorText: the open session's error is bare", () => {
  assert.equal(runErrorText("Counting files", "scripted model failure", true), "scripted model failure");
  assert.equal(runErrorText(null, "scripted model failure", true), "scripted model failure");
});

test("runErrorText: a left session's error names it", () => {
  assert.equal(runErrorText("Counting files", "scripted model failure", false),
    "“Counting files”: scripted model failure");
});

test("runErrorText: a session without a title is New chat", () => {
  assert.equal(runErrorText(null, "boom", false), "“New chat”: boom");
  assert.equal(runErrorText("", "boom", false), "“New chat”: boom");
});
