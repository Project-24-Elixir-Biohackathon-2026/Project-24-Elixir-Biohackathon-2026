// What counts as the agent's compaction marker: the same rule as the agent's input rewrite.
import { test } from "node:test";
import assert from "node:assert/strict";
import { MARKER_PREFIX, isCompactionMarker } from "./compaction.ts";

test("an assistant text message with the prefix is a marker", () => {
  assert.equal(MARKER_PREFIX, "spe-compaction-");
  assert.equal(isCompactionMarker({ id: "spe-compaction-1", role: "assistant", content: "summary" }), true);
  assert.equal(isCompactionMarker({ id: "spe-compaction-1", role: "assistant", content: "" }), true);
});

test("anything else is an ordinary message", () => {
  for (const message of [
    { id: "a1", role: "assistant", content: "spe-compaction- in the text" },
    { id: "spe-compaction-1", role: "user", content: "a participant's id" },
    { id: "spe-compaction-1", role: "assistant", content: [{ type: "text", text: "parts" }] },
    { id: "spe-compaction-1", role: "assistant", content: "x", toolCalls: [{ id: "c1" }] },
    { id: "spe-compaction-1", role: "assistant" },
    { role: "assistant", content: "no id" },
  ]) {
    assert.equal(isCompactionMarker(message), false, JSON.stringify(message));
  }
  assert.equal(isCompactionMarker({ id: "spe-compaction-1", role: "assistant", content: "x", toolCalls: [] }), true);
});
