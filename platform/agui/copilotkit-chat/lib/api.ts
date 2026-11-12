// The session API's handlers, framework-free: the Next.js routes in app/api/sessions/ only call these.
// Metadata only: PATCH, DELETE and POST .../title append a meta line; no route changes a message. Error
// bodies are generic; details go to the server log.
import { ValidationError, codeOf, isSessionId, parsePatch } from "./sessions.ts";
import type { Journals } from "./sessions.ts";
import { TitleUnavailable, firstQuestion } from "./title.ts";
import type { Titler } from "./title.ts";

const MAX_BODY = 16 * 1024;

function fail(status: number, error: string): Response {
  return Response.json({ error }, { status });
}

function serverError(what: string, error: unknown): Response {
  console.error(`sessions api: ${what}:`, codeOf(error));
  return fail(500, "the session store failed; see the chat-ui logs");
}

export class TooLarge extends Error {}

// A JSON `Content-Type`, ignoring any `; charset=...` suffix.
export function isJsonContentType(request: Request): boolean {
  return (request.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase() === "application/json";
}

// Reads at most `max` bytes (MAX_BODY by default); a larger body is refused without reading the rest.
export async function readBody(request: Request, max = MAX_BODY): Promise<string> {
  const declared = Number(request.headers.get("content-length") ?? 0);
  if (declared > max) throw new TooLarge();
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel();
      throw new TooLarge();
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

export async function listSessions(journals: Journals): Promise<Response> {
  try {
    return Response.json(await journals.list());
  } catch (error) {
    return serverError("list", error);
  }
}

export async function getSession(journals: Journals, id: string): Promise<Response> {
  if (!isSessionId(id)) return fail(400, "invalid session id");
  try {
    const view = await journals.get(id);
    return view ? Response.json(view) : fail(404, "no such session");
  } catch (error) {
    return serverError(`read ${id}`, error);
  }
}

export async function patchSession(journals: Journals, id: string, request: Request): Promise<Response> {
  if (!isSessionId(id)) return fail(400, "invalid session id");
  let patch;
  try {
    patch = parsePatch(JSON.parse(await readBody(request)));
  } catch (error) {
    if (error instanceof TooLarge) return fail(413, "the request body is too large");
    if (error instanceof SyntaxError || error instanceof ValidationError) return fail(400, "invalid session metadata");
    return serverError(`read body for ${id}`, error);
  }
  try {
    const meta = await journals.patch(id, patch);
    return meta ? Response.json(meta) : fail(404, "no such session");
  } catch (error) {
    return serverError(`patch ${id}`, error);
  }
}

export async function deleteSession(journals: Journals, id: string): Promise<Response> {
  if (!isSessionId(id)) return fail(400, "invalid session id");
  try {
    return (await journals.softDelete(id)) ? new Response(null, { status: 204 }) : fail(404, "no such session");
  } catch (error) {
    return serverError(`delete ${id}`, error);
  }
}

// POST /api/sessions/{id}/title: once a run of the session has added a user message (from its run_start, so
// while that run is still going) and the session has no title of its own (no meta title: neither a rename nor
// an earlier model title), the agent writes one from that first question, read from the journal; it is
// appended only if still no title is set (a rename meanwhile wins). Answers the
// metadata, unchanged when nothing was written. The agent failing is logged, not an error for the browser.
// No body is needed, so without this check the request would be a CORS simple request (no preflight) that
// another site could trigger freely, each call a paid model call while the agent keeps failing; requiring a
// JSON Content-Type forces a preflight.
export async function titleSession(journals: Journals, id: string, titler: Titler, request: Request): Promise<Response> {
  if (!isSessionId(id)) return fail(400, "invalid session id");
  if (!isJsonContentType(request)) return fail(415, "Content-Type must be application/json");
  let messages;
  try {
    const state = await journals.meta(id);
    if (!state) return fail(404, "no such session");
    if (state.titled) return Response.json(state.meta);
    const conv = await journals.load(id, { outsideQueue: true });
    messages = conv && firstQuestion(conv);
    if (!messages) return Response.json(state.meta);
  } catch (error) {
    return serverError(`read ${id}`, error);
  }
  let title: string;
  try {
    title = parsePatch({ title: await titler(id, messages) }).title!;
  } catch (error) {
    // The status or the error's name only: the agent's detail may quote the model.
    const why = error instanceof TitleUnavailable ? error.message : codeOf(error);
    console.warn(`sessions api: title ${id}: no title (${why})`);
    return unchanged(journals, id);
  }
  try {
    const meta = await journals.titleIfUntitled(id, title);
    return meta ? Response.json(meta) : fail(404, "no such session");
  } catch (error) {
    return serverError(`title ${id}`, error);
  }
}

async function unchanged(journals: Journals, id: string): Promise<Response> {
  try {
    const state = await journals.meta(id);
    return state ? Response.json(state.meta) : fail(404, "no such session");
  } catch (error) {
    return serverError(`read ${id}`, error);
  }
}
