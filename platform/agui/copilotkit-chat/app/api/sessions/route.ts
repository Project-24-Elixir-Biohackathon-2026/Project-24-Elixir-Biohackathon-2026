// GET /api/sessions: the session list (lib/api.ts), from the journals' index.
import { listSessions } from "../../../lib/api.ts";
import { defaultJournals } from "../../../lib/sessions.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(): Promise<Response> {
  return listSessions(defaultJournals());
}
