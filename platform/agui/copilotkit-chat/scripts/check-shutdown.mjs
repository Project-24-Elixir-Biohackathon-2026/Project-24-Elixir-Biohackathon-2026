// The SIGTERM drain against the built server, the barrier the archive export relies on: a slow run in progress, with the
// browser still reading and with the browser gone, is saved `cancelled` and the server exits by
// itself well inside `docker stop -t 30`.
//   node scripts/check-shutdown.mjs                     # node .next/standalone/server.js
//   node scripts/check-shutdown.mjs --image spe-chat-ui:check   # the image, as compose runs it, via docker stop -t 30
// Needs `npm run build` (or the image) first, and uv for platform/dev/fake_agent.py. No model calls.
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const APP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const AGENT_DIR = resolve(APP, "../pydantic-ai-agent");
const KEY = "check-shutdown-key";
const AGENT_PORT = 18107;
const UI_PORT = 3107;
const imageAt = process.argv.indexOf("--image");
const IMAGE = imageAt > 0 ? process.argv[imageAt + 1] : null;
const children = [];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function fail(message) {
  console.error(`FAIL: ${message}`);
  for (const c of children) c.kill("SIGKILL");
  if (IMAGE) spawnSync("docker", ["rm", "-f", "spe-check-shutdown"], { stdio: "ignore" });
  process.exit(1);
}

async function waitFor(url, what, ms = 60_000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return;
    } catch {
      // not up yet
    }
    await sleep(250);
  }
  fail(`${what} did not come up at ${url}`);
}

function startAgent() {
  const agent = spawn("uv", ["run", "--group", "dev", "python", "../../dev/fake_agent.py", "--port", String(AGENT_PORT), "--key", KEY],
    { cwd: AGENT_DIR, stdio: ["ignore", "inherit", "inherit"] });
  children.push(agent);
  return agent;
}

function startServer(dataDir) {
  const env = { AGENT_URL: `http://127.0.0.1:${AGENT_PORT}/agent`, AGENT_API_KEY: KEY, PORT: String(UI_PORT) };
  if (IMAGE) {
    // As the compose file runs it: read-only root, tmpfs, no capabilities; /data a writable mount.
    const args = ["run", "-d", "--name", "spe-check-shutdown", "--network", "host", "--read-only",
      "--tmpfs", "/tmp", "--tmpfs", "/app/.next/cache:uid=1000,gid=1000,mode=0700", "--cap-drop", "ALL",
      "--security-opt", "no-new-privileges:true", "-v", `${dataDir}:/data`,
      ...Object.entries({ ...env, HOSTNAME: "127.0.0.1" }).flatMap(([k, v]) => ["-e", `${k}=${v}`]), IMAGE];
    const r = spawnSync("docker", args, { encoding: "utf8" });
    if (r.status !== 0) fail(`docker run: ${r.stderr}`);
    return null;
  }
  const standalone = join(APP, ".next/standalone");
  if (!existsSync(join(standalone, "server.js"))) fail("no .next/standalone/server.js: run npm run build first");
  cpSync(join(APP, ".next/static"), join(standalone, ".next/static"), { recursive: true });
  const server = spawn("node", ["server.js"], {
    cwd: standalone,
    env: { ...process.env, ...env, HOSTNAME: "127.0.0.1", SPE_SESSIONS_DIR: join(dataDir, "sessions"), NEXT_MANUAL_SIG_HANDLE: "true" },
    stdio: ["ignore", "pipe", "inherit"],
  });
  server.output = "";
  server.stdout.on("data", (d) => { server.output += d; process.stdout.write(d); });
  children.push(server);
  return server;
}

// Starts a slow run and returns once RUN_STARTED has arrived; `keepReading` false drops the client.
async function startSlowRun(threadId, keepReading) {
  const controller = new AbortController();
  const body = {
    threadId, runId: randomUUID(), state: {}, tools: [], context: [], forwardedProps: {},
    messages: [{ id: randomUUID(), role: "user", content: "a slow one, please" }],
  };
  const response = await fetch(`http://127.0.0.1:${UI_PORT}/api/copilotkit/agent/spe/run`, {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body), signal: controller.signal,
  });
  if (!response.ok || !response.body) fail(`run request: HTTP ${response.status}`);
  const reader = response.body.getReader();
  let seen = "";
  while (!seen.includes("RUN_STARTED")) {
    const { value, done } = await reader.read();
    if (done) fail("the run stream ended before RUN_STARTED");
    seen += new TextDecoder().decode(value);
  }
  await sleep(1000); // well inside the slow run's ~10 s
  if (keepReading) {
    void (async () => { try { for (;;) { const { done } = await reader.read(); if (done) return; } } catch { /* server gone */ } })();
  } else {
    controller.abort();
    await sleep(300);
  }
}

async function stopAndTime(server) {
  const started = Date.now();
  if (IMAGE) {
    const r = spawnSync("docker", ["stop", "-t", "30", "spe-check-shutdown"], { encoding: "utf8" });
    if (r.status !== 0) fail(`docker stop: ${r.stderr}`);
    const code = spawnSync("docker", ["inspect", "-f", "{{.State.ExitCode}}", "spe-check-shutdown"], { encoding: "utf8" }).stdout.trim();
    const logs = spawnSync("docker", ["logs", "spe-check-shutdown"], { encoding: "utf8" });
    spawnSync("docker", ["rm", "-f", "spe-check-shutdown"], { stdio: "ignore" });
    return { seconds: (Date.now() - started) / 1000, code: Number(code), output: logs.stdout + logs.stderr };
  }
  const exited = new Promise((r) => server.on("exit", (code) => r(code)));
  server.kill("SIGTERM");
  const code = await Promise.race([exited, sleep(35_000).then(() => "timeout")]);
  if (code === "timeout") fail("the server did not exit within 35 s of SIGTERM");
  return { seconds: (Date.now() - started) / 1000, code, output: server.output };
}

async function phase(name, keepReading) {
  const dataDir = mkdtempSync(join(tmpdir(), "spe-check-shutdown-"));
  mkdirSync(join(dataDir, "sessions"), { mode: 0o700 });
  const server = startServer(dataDir);
  await waitFor(`http://127.0.0.1:${UI_PORT}/api/sessions`, "the chat UI");
  const threadId = randomUUID();
  await startSlowRun(threadId, keepReading);
  const { seconds, code, output } = await stopAndTime(server);
  const file = join(dataDir, "sessions", `${threadId}.json`);
  if (!existsSync(file)) fail(`${name}: no session file after SIGTERM`);
  const record = JSON.parse(readFileSync(file, "utf8"));
  if (record.runs.length !== 1 || record.runs[0].status !== "cancelled") fail(`${name}: runs = ${JSON.stringify(record.runs)}`);
  if (!record.messages.some((m) => m.role === "user" && String(m.content).includes("slow"))) fail(`${name}: user message missing`);
  if (seconds >= 30) fail(`${name}: took ${seconds} s, beyond docker stop -t 30`);
  if (code !== 0) fail(`${name}: exit code ${code}`);
  if (!output.includes("shutdown: 1 run(s) cancelled, sessions saved")) fail(`${name}: no drain log line`);
  console.log(`ok - ${name}: saved cancelled, exit 0 after ${seconds.toFixed(1)} s`);
  rmSync(dataDir, { recursive: true, force: true });
}

startAgent();
await waitFor(`http://127.0.0.1:${AGENT_PORT}/healthz`, "the fake agent");
await phase("browser still reading", true);
await phase("browser gone, run detached", false);
for (const c of children) c.kill("SIGTERM");
console.log("check-shutdown: all passed");
