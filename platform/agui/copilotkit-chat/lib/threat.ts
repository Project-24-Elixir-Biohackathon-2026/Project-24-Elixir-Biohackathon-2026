// POST /api/threat-score: how much a draft looks like an attack, for the indicator under the chat input
// (app/threat-indicator.tsx). The score comes from the agent's POST /threat-score, next to its /agent, with the
// bearer key the chat runtime uses: the agent holds the LLM key the embedding needs. Advisory only: nothing is
// journaled and nothing is blocked. Node-only; the browser's side is lib/threat-watch.ts.
import { TooLarge, isJsonContentType, readBody } from "./api.ts";

export type ThreatLevel = "low" | "elevated" | "high";
export type ThreatCategory = {
  id: string; label: string; score: number; level: ThreatLevel;
  /** In-domain adversarial prompts the head was trained on, and its cross-validated AUC: how far to trust it. */
  examples: number; auc: number | null;
};
export type ThreatScore = {
  /** 0-100 on the model's own scale: 50 is where 5% of benign prompts score higher, 75 where 1% do. */
  score: number; level: ThreatLevel; categories: ThreatCategory[];
  model: { version: number; trained: string; embedding_model: string };
};

/** The draft's score, or null when the agent has the threat score switched off. Throws when it cannot be had. */
export type Scorer = (text: string) => Promise<ThreatScore | null>;

export const MAX_TEXT_CHARS = 16_000; // the agent's limit
const MAX_BODY = 4 * MAX_TEXT_CHARS + 1024; // every character as four UTF-8 bytes, and the JSON around it
export const SCORE_TIMEOUT_MS = 12_000;

const LEVELS = new Set(["low", "elevated", "high"]);
const isScore = (v: unknown): v is number => typeof v === "number" && v >= 0 && v <= 100;

/** The agent's answer, checked field by field: the page renders it, so nothing else passes through. */
export function parseScore(body: unknown): ThreatScore {
  const b = body as Record<string, unknown> | null;
  const model = b?.model as Record<string, unknown> | undefined;
  if (!b || !isScore(b.score) || !LEVELS.has(b.level as string) || !Array.isArray(b.categories) || !model
    || typeof model.version !== "number" || typeof model.trained !== "string" || typeof model.embedding_model !== "string") {
    throw new Error("the agent's threat score is malformed");
  }
  const categories = b.categories.map((raw): ThreatCategory => {
    const c = raw as Record<string, unknown> | null;
    if (!c || typeof c.id !== "string" || typeof c.label !== "string" || !isScore(c.score) || !LEVELS.has(c.level as string)
      || typeof c.examples !== "number" || !(c.auc === null || typeof c.auc === "number")) {
      throw new Error("the agent's threat score is malformed");
    }
    return { id: c.id, label: c.label, score: c.score, level: c.level as ThreatLevel, examples: c.examples, auc: c.auc };
  });
  return {
    score: b.score, level: b.level as ThreatLevel, categories,
    model: { version: model.version, trained: model.trained, embedding_model: model.embedding_model },
  };
}

type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export function agentScorer(agentUrl: string, key: string, f: Fetch = fetch, timeoutMs = SCORE_TIMEOUT_MS): Scorer {
  const url = new URL("/threat-score", agentUrl).toString();
  return async (text) => {
    const response = await f(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (response.status === 404) {
      await response.body?.cancel();
      return null;
    }
    if (response.status !== 200) {
      await response.body?.cancel();
      throw new Error(`the agent answered ${response.status}`);
    }
    return parseScore(await response.json());
  };
}

function fail(status: number, error: string): Response {
  return Response.json({ error }, { status });
}

// A JSON Content-Type is required, as for the title route: without it the request would be a CORS simple
// request that another site could send freely, each one an embedding call on the instance's LLM key.
export async function scoreText(request: Request, scorer: Scorer): Promise<Response> {
  if (!isJsonContentType(request)) return fail(415, "Content-Type must be application/json");
  let text: unknown;
  try {
    text = (JSON.parse(await readBody(request, MAX_BODY)) as { text?: unknown } | null)?.text;
  } catch (error) {
    if (error instanceof TooLarge) return fail(413, "the request body is too large");
    return fail(400, "invalid request");
  }
  if (typeof text !== "string" || text.trim() === "" || text.length > MAX_TEXT_CHARS) return fail(400, "invalid request");
  try {
    const score = await scorer(text);
    return score ? Response.json(score) : fail(404, "the threat score is switched off");
  } catch (error) {
    // The reason only: the agent's detail may quote the provider.
    console.warn("threat score:", error instanceof Error ? error.message : "failed");
    return fail(502, "the threat score is unavailable; see the chat-ui logs");
  }
}
