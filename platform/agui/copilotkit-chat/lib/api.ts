// The session API's handlers, framework-free: the Next.js routes in app/api/sessions/ only call these.
// Metadata only: PATCH and DELETE append a meta line; no route changes a message. Error bodies are
// generic; details go to the server log.
import { ValidationError, codeOf, isSessionId, parsePatch } from "./sessions.ts";
import type { Journals } from "./sessions.ts";

const MAX_BODY = 16 * 1024;

function fail(status: number, error: string): Response {
  return Response.json({ error }, { status });
}

function serverError(what: string, error: unknown): Response {
  console.error(`sessions api: ${what}:`, codeOf(error));
  return fail(500, "the session store failed; see the chat-ui logs");
}

class TooLarge extends Error {}

// Reads at most MAX_BODY bytes; a larger body is refused without reading the rest.
async function readBody(request: Request): Promise<string> {
  const declared = Number(request.headers.get("content-length") ?? 0);
  if (declared > MAX_BODY) throw new TooLarge();
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY) {
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
