// POST /api/sessions/{id}/title: a model-written title from the session's first question, asked as its first run starts (lib/api.ts).
// The agent's URL and key come from the same server-side environment as the chat runtime's
// (app/api/copilotkit/[[...slug]]/route.ts) and are sent only to the agent.
import { titleSession } from "../../../../../lib/api.ts";
import { defaultJournals } from "../../../../../lib/sessions.ts";
import { agentTitler } from "../../../../../lib/title.ts";
import type { Titler } from "../../../../../lib/title.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ id: string }> };

// Read on the first request, not at import: `next build` imports this module without the env. Without it,
// the call fails and the session keeps its title (titleSession logs why).
const titler: Titler = (threadId, messages) => {
  const url = process.env.AGENT_URL;
  const key = process.env.AGENT_API_KEY;
  if (!url || !key) return Promise.reject(new Error("AGENT_URL and AGENT_API_KEY must be set"));
  return agentTitler(url, key)(threadId, messages);
};

export async function POST(request: Request, { params }: Context): Promise<Response> {
  return titleSession(defaultJournals(), (await params).id, titler, request);
}
