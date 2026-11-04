import assert from "node:assert/strict";
import { test } from "node:test";
import { argumentRows, cardState, commandOf, groupState, readResult, toolSummary } from "./tool-card.ts";

test("argumentRows: one row per key, strings as they are, everything else as JSON", () => {
  assert.deepEqual(argumentRows({ path: "/home/x", recursive: true, depth: 2, opts: { a: 1 }, none: null }), [
    ["path", "/home/x"],
    ["recursive", "true"],
    ["depth", "2"],
    ["opts", '{"a":1}'],
    ["none", "null"],
  ]);
});

test("argumentRows: no arguments, or arguments that are not an object, give no rows or one", () => {
  assert.deepEqual(argumentRows(undefined), []);
  assert.deepEqual(argumentRows({}), []);
  assert.deepEqual(argumentRows("raw"), [["", "raw"]]);
  assert.deepEqual(argumentRows([1, 2]), [["", "[1,2]"]]);
});

test("commandOf: run_command's command, while it streams in too; any other tool has none", () => {
  assert.equal(commandOf("run_command", { command: "ls -la" }), "ls -la");
  assert.equal(commandOf("run_command", {}), "");
  assert.equal(commandOf("run_command", undefined), "");
  assert.equal(commandOf("read_file", { command: "ls" }), null);
});

test("readResult: a JSON object with a string `error` is a failure, its message the body", () => {
  assert.deepEqual(readResult("read_file", '{"error": "HTTP error 404: not found"}'),
    { failed: true, body: "HTTP error 404: not found" });
});

test("readResult: run_command's output parts joined, \\r\\n as \\n; a nonzero exit code fails", () => {
  const ok = JSON.stringify({ id: "1", command: "seq 1 2", status: "done", exit_code: 0,
    output: [{ type: "output", data: "1\r\n" }, { type: "output", data: "2\r\n" }] });
  assert.deepEqual(readResult("run_command", ok), { failed: false, body: "1\n2\n" });
  const bad = JSON.stringify({ id: "1", status: "done", exit_code: 2, output: [{ type: "output", data: "no such file" }] });
  assert.deepEqual(readResult("run_command", bad), { failed: true, body: "no such file\n[exit code 2]" });
});

test("readResult: run_command output as a plain string is taken as is", () => {
  const r = JSON.stringify({ status: "done", exit_code: 0, output: "$ echo hi\nhi" });
  assert.deepEqual(readResult("run_command", r), { failed: false, body: "$ echo hi\nhi" });
});

test("readResult: any other JSON is pretty-printed; text that is not JSON is shown as is", () => {
  assert.deepEqual(readResult("list_files", '{"files":["a"]}'),
    { failed: false, body: '{\n  "files": [\n    "a"\n  ]\n}' });
  const truncated = '{"id":"1","output":[{"data":"1\\r\\n2\n[truncated: 10 of 99 bytes shown]';
  assert.deepEqual(readResult("run_command", truncated), { failed: false, body: truncated });
});

test("readResult: a result the agent truncated still fails on a nonzero exit_code or a leading error", () => {
  const cutOk = '{"id":"1","command":"make","status":"done","exit_code":0,"output":[{"data":"ok\n[truncated: 5 of 9 bytes shown]';
  assert.equal(readResult("run_command", cutOk).failed, false);
  const cutBad = '{"id":"1","command":"make","status":"done","exit_code":2,"output":[{"data":"boom\n[truncated: 5 of 9 bytes shown]';
  assert.equal(readResult("run_command", cutBad).failed, true);
  assert.equal(readResult("x", '{"error": "HTTP error 500: ' + "x".repeat(50) + "\n[truncated: 10 of 99 bytes shown]").failed, true);
});

test("readResult: a command still running when the call returned is not a failure, and says so", () => {
  const r = JSON.stringify({ id: "p9", status: "running", exit_code: null, output: [{ type: "output", data: "partial" }] });
  assert.deepEqual(readResult("run_command", r), { failed: false, body: "partial\n[still running: process p9]" });
});

test("readResult: the exit code note survives the cut", () => {
  const long = Array.from({ length: 100 }, (_, i) => `line ${i}`).join("\n");
  const r = JSON.stringify({ status: "done", exit_code: 3, output: long });
  assert.match(readResult("run_command", r).body, /more characters\)\n\[exit code 3\]$/);
});

test("readResult: a long body is cut to its first lines, saying how much is left out", () => {
  const text = Array.from({ length: 100 }, (_, i) => `line ${i}`).join("\n");
  const { body } = readResult("x", text);
  assert.equal(body.split("\n").length, 41);
  assert.match(body, /^line 0\n/);
  assert.match(body, /\n… \(\d+ more characters\)$/);
});

test("cardState: running until a result arrives, then done or failed", () => {
  assert.equal(cardState("inProgress", undefined), "running");
  assert.equal(cardState("executing", undefined), "running");
  assert.equal(cardState("complete", '{"ok":true}'), "done");
  assert.equal(cardState("complete", '{"error":"x"}'), "failed");
});

test("groupState: running while any call runs, else failed if any failed, else done", () => {
  assert.equal(groupState(["done", "running", "failed"]), "running");
  assert.equal(groupState(["done", "failed"]), "failed");
  assert.equal(groupState(["done", "done"]), "done");
});

test("toolSummary: each name once in first-call order, counted when called more than once", () => {
  assert.equal(toolSummary(["run_command"]), "run_command");
  assert.equal(toolSummary(["run_command", "run_command"]), "2 run_command");
  assert.equal(toolSummary(["list_files", "run_command", "list_files", "run_command", "run_command"]),
    "2 list_files, 3 run_command");
  assert.equal(toolSummary(["read_file", "list_files", "read_file"]), "2 read_file, list_files");
});
