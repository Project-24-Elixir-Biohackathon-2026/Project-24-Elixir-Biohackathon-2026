// The page's calls to the session API (lib/api.ts answers them). Browser-safe: types only from sessions.ts.
import type { MetaPatch, SessionMeta, SessionView } from "./sessions.ts";

export type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function failure(response: Response, what: string): Promise<ApiError> {
  let detail = "";
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && typeof (body as { error?: unknown }).error === "string") {
      detail = `: ${(body as { error: string }).error}`;
    }
  } catch {
    // not JSON: the status says enough
  }
  return new ApiError(response.status, `${what} failed (${response.status})${detail}`);
}

const call = (f: Fetch | undefined): Fetch => f ?? ((input, init) => fetch(input, init));

export async function fetchSessions(f?: Fetch): Promise<SessionMeta[]> {
  const response = await call(f)("/api/sessions", { cache: "no-store" });
  if (!response.ok) throw await failure(response, "Loading the sessions");
  return (await response.json()) as SessionMeta[];
}

// null: the session does not exist (or was deleted).
export async function fetchSession(id: string, f?: Fetch): Promise<SessionView | null> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw await failure(response, "Opening the session");
  return (await response.json()) as SessionView;
}

export async function updateSession(id: string, patch: MetaPatch, f?: Fetch): Promise<SessionMeta> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw await failure(response, "Saving the change");
  return (await response.json()) as SessionMeta;
}

// The model-written title, asked for once as a new session's first run starts: the server reads that run's
// question from the journal and writes a title only if none is set. The metadata either way.
export async function askTitle(id: string, f?: Fetch): Promise<SessionMeta> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}/title`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) throw await failure(response, "Titling the session");
  return (await response.json()) as SessionMeta;
}

export async function removeSession(id: string, f?: Fetch): Promise<void> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw await failure(response, "Deleting the session");
}

// The row menu's edits, as the PATCH bodies they send. The server normalises and validates tags
// (lib/sessions.ts, normaliseTags); here only blanks and duplicates are dropped.
export function renamePatch(input: string, current: string): MetaPatch | null {
  const title = input.trim();
  return title && title !== current ? { title } : null;
}

export function withTag(tags: string[], input: string): MetaPatch | null {
  const tag = input.trim().toLowerCase();
  return tag && !tags.includes(tag) ? { tags: [...tags, tag] } : null;
}

export function withoutTag(tags: string[], tag: string): MetaPatch {
  return { tags: tags.filter((t) => t !== tag) };
}

// The tag editor's suggestions for what is typed: tags in use (`known`) that contain it, ignoring case,
// leaving out those the session already has; at most `max` (Open WebUI shows 8).
export function tagSuggestions(known: string[], current: string[], input: string, max = 8): string[] {
  const typed = input.trim().toLowerCase();
  if (!typed) return [];
  return known.filter((t) => !current.includes(t) && t.toLowerCase().includes(typed)).slice(0, max);
}
