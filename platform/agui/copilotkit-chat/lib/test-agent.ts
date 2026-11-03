// Test helper: a tiny AG-UI agent over SSE (node:http), scripted by the last user message.
//   contains "hang": RUN_STARTED and one text chunk, then nothing until the client goes away
//   contains "boom": HTTP 500 before any event
//   contains "error": RUN_STARTED then RUN_ERROR
//   contains "eof": RUN_STARTED and a text message, then the stream ends without a terminal event
//   contains "crash": RUN_STARTED and one text chunk, then the connection is destroyed
//   contains "compact": also sends a compaction marker (an assistant message, id `spe-compaction-<runId>`)
//   contains "activity": also sends an ACTIVITY_SNAPSHOT (the form the spec first chose; pinned as dropped)
//   contains "echo-input": the reply's text is the JSON of [{role, id}] for every message the agent received
//   a body that is not JSON: HTTP 400, not kept in `requests`
//   anything else: a text message echoing it, then RUN_FINISHED (after `delayMs`, default 0)
// Each request is kept in `requests`; `closed` turns true when its connection closes.
// `headerDelayMs`: wait this long after the request is parsed, before writing any response (status
// line included) — for a test that must abort before the agent's response headers arrive.
import { createServer } from "node:http";
import type { IncomingMessage, Server } from "node:http";
import type { AddressInfo } from "node:net";

export type TestAgent = {
  url: string;
  requests: { headers: IncomingMessage["headers"]; body: any; closed: boolean }[];
  close: () => Promise<void>;
};

export async function startTestAgent(delayMs = 0, headerDelayMs = 0): Promise<TestAgent> {
  const requests: TestAgent["requests"] = [];
  const server: Server = createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", async () => {
      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        res.writeHead(400, { "content-type": "application/json" }).end('{"detail":"the body is not JSON"}');
        return;
      }
      const entry = { headers: req.headers, body, closed: false };
      res.on("close", () => (entry.closed = true));
      requests.push(entry);
      const users = (body.messages ?? []).filter((m: any) => m.role === "user");
      const text = String(users.at(-1)?.content ?? "");
      if (headerDelayMs) await new Promise((r) => setTimeout(r, headerDelayMs));
      if (res.destroyed || res.writableEnded) return; // the client (e.g. an abort) already closed this
      if (text.includes("boom")) {
        res.writeHead(500, { "content-type": "application/json" }).end('{"detail":"agent down"}');
        return;
      }
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      const send = (event: object) => res.write(`data: ${JSON.stringify(event)}\n\n`);
      const ids = { threadId: body.threadId, runId: body.runId };
      const messageId = `reply-${body.runId}`;
      send({ type: "RUN_STARTED", ...ids });
      if (text.includes("compact")) {
        // As the agent sends a compaction marker: an assistant message whose id has the marker prefix.
        const markerId = `spe-compaction-${body.runId}`;
        send({ type: "TEXT_MESSAGE_START", messageId: markerId, role: "assistant" });
        send({ type: "TEXT_MESSAGE_CONTENT", messageId: markerId, delta: "SUMMARY of the earlier turns" });
        send({ type: "TEXT_MESSAGE_END", messageId: markerId });
      }
      if (text.includes("activity")) {
        // The form the spec first chose; pinned as dropped by CopilotKit's input path.
        send({ type: "ACTIVITY_SNAPSHOT", messageId: `act-${body.runId}`, activityType: "pydantic_ai_compaction",
               content: { content: "SUMMARY as activity", provider_name: "spe-agent" }, replace: true });
      }
      if (text.includes("error")) {
        send({ type: "RUN_ERROR", message: "scripted failure" });
        res.end();
        return;
      }
      send({ type: "TEXT_MESSAGE_START", messageId, role: "assistant" });
      const reply = text.includes("echo-input")
        ? JSON.stringify((body.messages ?? []).map((m: any) => ({ role: m.role, id: m.id })))
        : `echo: ${text}`;
      send({ type: "TEXT_MESSAGE_CONTENT", messageId, delta: reply });
      if (text.includes("hang")) return; // the client's abort or close ends it
      if (text.includes("crash")) {
        setTimeout(() => res.socket?.destroy(), 20);
        return;
      }
      send({ type: "TEXT_MESSAGE_END", messageId });
      if (text.includes("eof")) {
        res.end();
        return;
      }
      if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
      send({ type: "RUN_FINISHED", ...ids });
      res.end();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}/agent`,
    requests,
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}
