// What counts as a command (spec §15): one user message whose string content, trimmed, is /compact or
// /compact followed by whitespace and a focus. Case matters.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { Message } from "@ag-ui/client";
import { commandOf, offersCompact, parseCommand, sameCommand } from "./command.ts";

const user = (id: string, content: unknown) => ({ id, role: "user", content }) as Message;

test("parseCommand: the table of decision 31", () => {
  const cases: [unknown, ReturnType<typeof parseCommand>][] = [
    ["/compact", { name: "compact", focus: null }],
    ["  /compact  keep x ", { name: "compact", focus: "keep x" }],
    ["/compact\nkeep x\n\nand y\n", { name: "compact", focus: "keep x\n\nand y" }],
    ["/compact   ", { name: "compact", focus: null }],
    ["/compacted", null],
    ["/compact:", null],
    ["/COMPACT", null],
    ["please /compact", null],
    [[{ type: "text", text: "/compact" }], null],
    [undefined, null],
  ];
  for (const [content, expected] of cases) assert.deepEqual(parseCommand(content), expected, JSON.stringify(content));
});

test("commandOf: exactly one new message, a user message that parses", () => {
  assert.deepEqual(commandOf([user("k", "/compact keep x")]), { name: "compact", focus: "keep x", message_id: "k" });
  assert.equal(commandOf([user("k", "/compact"), user("m", "more")]), null);
  assert.equal(commandOf([{ id: "k", role: "assistant", content: "/compact" } as Message]), null);
  assert.equal(commandOf([]), null);
});

test("sameCommand compares name and focus", () => {
  assert.ok(sameCommand({ name: "compact", focus: null }, { name: "compact", focus: null }));
  assert.ok(!sameCommand({ name: "compact", focus: "a" }, { name: "compact", focus: null }));
});

test("offersCompact: while the whole text is a prefix of /compact, and only then", () => {
  for (const value of ["/", "/c", "/comp", "/compact"]) assert.equal(offersCompact(value), true, value);
  for (const value of ["", "c", " /compact", "/compact ", "/compact keep x", "/compact\n", "/compact\nkeep x", "/\nhello",
    "/compacted", "/x", "/COMPACT", "hi\n/compact"]) {
    assert.equal(offersCompact(value), false, value);
  }
});
