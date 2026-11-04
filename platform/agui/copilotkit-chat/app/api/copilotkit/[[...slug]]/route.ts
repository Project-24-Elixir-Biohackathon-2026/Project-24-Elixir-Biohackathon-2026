// CopilotKit runtime (v2, multi-route: /api/copilotkit/info, /api/copilotkit/agent/spe/run, ...).
// The only place that knows the agent's URL and bearer key: both come from server-side
// environment variables (never NEXT_PUBLIC_*) and are sent only to the agent.
import { HttpAgent } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { SessionRecorder } from "../../../../lib/recorder.ts";
import { defaultJournals } from "../../../../lib/sessions.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Handler = (request: Request) => Promise<Response>;
let handler: Handler | undefined;

// Built on the first request, not at import: `next build` imports this module without the env.
function getHandler(): Handler {
  if (!handler) {
    const url = process.env.AGENT_URL;
    const key = process.env.AGENT_API_KEY;
    if (!url || !key) {
      throw new Error("AGENT_URL and AGENT_API_KEY must be set");
    }
    // Keeps every run in its session's journal (lib/recorder.ts): the agent is sent the journal's history,
    // not the client's. The runtime clones `spe` per request and the clone keeps the recorder and its fetch,
    // through which the recorder closes the agent request of a run it ends.
    const recorder = new SessionRecorder(defaultJournals);
    const spe = new HttpAgent({ url, headers: { Authorization: `Bearer ${key}` }, fetch: recorder.fetch });
    spe.use(recorder);
    const copilotRuntime = new CopilotRuntime({ agents: { spe } });
    handler = createCopilotRuntimeHandler({ runtime: copilotRuntime, basePath: "/api/copilotkit" });
  }
  return handler;
}

async function handle(request: Request): Promise<Response> {
  try {
    return await getHandler()(request);
  } catch (error) {
    // Details go to the server log only; the browser gets a generic message.
    console.error("copilotkit runtime:", error instanceof Error ? error.message : error);
    return Response.json({ error: "The chat runtime failed; see the chat-ui logs." }, { status: 500 });
  }
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
