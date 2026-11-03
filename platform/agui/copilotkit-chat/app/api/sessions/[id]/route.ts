// GET, PATCH and DELETE /api/sessions/{id} (lib/api.ts).
import { deleteSession, getSession, patchSession } from "../../../../lib/api.ts";
import { defaultJournals } from "../../../../lib/sessions.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context): Promise<Response> {
  return getSession(defaultJournals(), (await params).id);
}

export async function PATCH(request: Request, { params }: Context): Promise<Response> {
  return patchSession(defaultJournals(), (await params).id, request);
}

export async function DELETE(_request: Request, { params }: Context): Promise<Response> {
  return deleteSession(defaultJournals(), (await params).id);
}
