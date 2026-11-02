#!/usr/bin/env node
// Checks the built standalone server: what unit tests cannot show because Next.js
// bundles each route separately. Builds nothing: run `npm run build` first. Starts
// platform/dev/fake_agent.py (no model calls) and `node .next/standalone/server.js` with a
// temporary sessions directory and a delayed save, then checks that
//   1. two sessions run at once keep separate recorder state (per-run state across clones);
//   2. PATCHes overlapping a run's finalisation all land, and the run's messages too (one
//      session queue shared by the session routes and the CopilotKit route).
// Exits non-zero on the first failure, or after DEADLINE_MS if something hangs; each request
// gives up after REQUEST_MS.
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { rmSync } from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const chat = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const agentDir = path.resolve(chat, "../pydantic-ai-agent");
const fakeAgent = path.resolve(chat, "../../dev/fake_agent.py");
const AGENT_PORT = 18171;
const UI_PORT = 18172;
const KEY = `check-${randomUUID()}`;
const SAVE_DELAY_MS = 1500;
const REQUEST_MS = 30_000;
const DEADLINE_MS = 180_000;
const ui = `http://127.0.0.1:${UI_PORT}`;
const children = [];

function start(cmd, args, options) {
  const child = spawn(cmd, args, { stdio: ["ignore", "inherit", "inherit"], ...options });
  children.push(child);
  return child;
}

// A fetch that fails instead of waiting forever on a wedged server.
function request(url, init = {}) {
  return fetch(url, { ...init, signal: AbortSignal.timeout(REQUEST_MS) });
}

async function waitFor(url) {
  for (let i = 0; i < 300; i++) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(2000) });
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw new Error(`${url} did not come up`);
}

function check(ok, what) {
  if (!ok) throw new Error(`FAILED: ${what}`);
  console.log(`ok: ${what}`);
}

function user(content) {
  return { id: randomUUID(), role: "user", content };
}

// One run through the CopilotKit route, read to its end (the SSE stream ends after the save).
async function run(threadId, messages) {
  const response = await request(`${ui}/api/copilotkit/agent/spe/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ threadId, runId: randomUUID(), messages, tools: [], context: [], state: {}, forwardedProps: {} }),
  });
  const text = await response.text();
  check(response.status === 200 && text.includes("RUN_FINISHED"), `run on ${threadId} finished`);
}

async function session(id) {
  return JSON.parse(await fs.readFile(path.join(dir, `${id}.json`), "utf8"));
}

const dir = await fs.mkdtemp(path.join(os.tmpdir(), "check-sessions-"));
// The whole check's bound: kill what it started and fail, whatever step is stuck.
const deadline = setTimeout(() => {
  console.error(`FAILED: the check did not finish within ${DEADLINE_MS / 1000} s`);
  // SIGTERM, as below: uv passes it on to the fake agent, a SIGKILL would orphan it.
  for (const child of children) child.kill("SIGTERM");
  rmSync(dir, { recursive: true, force: true });
  setTimeout(() => process.exit(1), 1000);
}, DEADLINE_MS);
try {
  start("uv", ["run", "--group", "dev", "python", fakeAgent, "--port", String(AGENT_PORT), "--key", KEY], {
    cwd: agentDir, env: { ...process.env, PYDANTIC_AI_NO_BANNER: "1" },
  });
  start("node", [".next/standalone/server.js"], {
    cwd: chat,
    env: {
      ...process.env, PORT: String(UI_PORT), HOSTNAME: "127.0.0.1", AGENT_URL: `http://127.0.0.1:${AGENT_PORT}/agent`,
      AGENT_API_KEY: KEY, SPE_SESSIONS_DIR: dir, SPE_SESSIONS_TEST_SAVE_DELAY_MS: String(SAVE_DELAY_MS),
      NEXT_TELEMETRY_DISABLED: "1", COPILOTKIT_TELEMETRY_DISABLED: "true", DO_NOT_TRACK: "1",
    },
  });
  await waitFor(`http://127.0.0.1:${AGENT_PORT}/`);
  await waitFor(`${ui}/api/sessions`);

  // 1. Two sessions at once.
  const a = randomUUID();
  const b = randomUUID();
  await Promise.all([run(a, [user("first session question")]), run(b, [user("second session question")])]);
  const [ra, rb] = [await session(a), await session(b)];
  check(ra.messages[0].content === "first session question" && rb.messages[0].content === "second session question",
    "each session holds its own conversation");
  check(!JSON.stringify(ra.messages).includes("second session") && !JSON.stringify(rb.messages).includes("first session"),
    "no message crossed between the two sessions");
  check(ra.runs.length === 1 && rb.runs.length === 1 && ra.runs[0].status === "completed" && rb.runs[0].status === "completed",
    "one completed run each");

  // 2. PATCHes, one after another, for as long as a run on the same session is in progress.
  //    The save is delayed by SAVE_DELAY_MS under the queue, so PATCHes sent meanwhile wait for it.
  let ended = false;
  const running = run(a, [...ra.messages, user("second turn")]).finally(() => (ended = true));
  const acknowledged = [];
  const waits = [];
  for (let i = 0; !ended; i++) {
    const t0 = Date.now();
    const response = await request(`${ui}/api/sessions/${a}`, {
      method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: `patch ${i}` }),
    });
    if (response.status !== 200) throw new Error(`FAILED: PATCH ${i} answered ${response.status}`);
    acknowledged.push(`patch ${i}`);
    waits.push(Date.now() - t0);
  }
  await running;
  check(acknowledged.length > 0, `${acknowledged.length} PATCHes answered 200 during the run`);
  check(waits.some((ms) => ms >= SAVE_DELAY_MS / 2), "a PATCH overlapped the run's finalisation and waited for it");
  const after = await session(a);
  check(after.title === acknowledged.at(-1) && after.title_source === "user", "the last PATCH's title is on disk");
  check(after.runs.length === 2 && after.messages.some((m) => m.content === "second turn"), "the run's messages are on disk");
  console.log("check-built-server: all checks passed");
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  for (const child of children) child.kill("SIGTERM");
  await fs.rm(dir, { recursive: true, force: true });
}
