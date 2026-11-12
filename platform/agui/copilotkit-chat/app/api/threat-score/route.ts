// POST /api/threat-score: the draft's threat score, asked for while typing (lib/threat.ts).
// The agent's URL and key come from the same server-side environment as the chat runtime's and are sent
// only to the agent.
import { agentScorer, scoreText } from "../../../lib/threat.ts";
import type { Scorer } from "../../../lib/threat.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read on the first request, not at import: `next build` imports this module without the env.
const scorer: Scorer = (text) => {
  const url = process.env.AGENT_URL;
  const key = process.env.AGENT_API_KEY;
  if (!url || !key) return Promise.reject(new Error("AGENT_URL and AGENT_API_KEY must be set"));
  return agentScorer(url, key)(text);
};

export function POST(request: Request): Promise<Response> {
  return scoreText(request, scorer);
}
