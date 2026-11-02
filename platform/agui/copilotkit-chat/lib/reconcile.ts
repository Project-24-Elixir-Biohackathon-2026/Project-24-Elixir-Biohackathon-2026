// After a run ends, fetch the session list until it shows that run: a run the server saw
// unsubscribed (the stream dropped before its end) is saved after the client has gone, so its
// save can land after the first fetch. Pure apart
// from the injected fetch and sleep, so `node --test` covers it. Browser code: it must not
// import recorder.ts (Node-only); reconcile.test.ts checks the copies below against it.
import type { Fetch } from "./client.ts";
import type { SessionMeta } from "./sessions.ts";

export const SAVE_FAILED_MESSAGE = "this session could not be saved";
export const RECONCILE_RETRIES = 5;
export const RECONCILE_DELAY_MS = 500;
/** Name of the CUSTOM event the recorder sends, before the run's last event, when the session
 *  file could not be written; its value is `{ session: <id> }`. */
export const SAVE_FAILED_EVENT = "spe.session_save_failed";
/** RUN_ERROR messages of a run the recorder refused at admission: such a run writes nothing. */
export const REFUSED_RUN_MESSAGES: readonly string[] = [
  "invalid session",
  "this session was deleted",
  "this session is already running",
  "the chat UI is shutting down",
  "this session could not be read",
];

export type ListResult = { list: SessionMeta[]; serverOffsetMs: number };
export type FetchList = () => Promise<ListResult>;

/** Server clock minus browser clock, from a response's `Date` header; 0 when absent or invalid.
 *  The header has whole seconds, rounded down, so this is up to 1 s too small. */
export function clockOffset(dateHeader: string | null, browserNowMs: number): number {
  const server = dateHeader === null ? NaN : Date.parse(dateHeader);
  return Number.isNaN(server) ? 0 : server - browserNowMs;
}

/** The run's start in server time, from the browser's clock and the last measured offset. The
 *  offset's rounding makes it up to 1 s early: a save is never missed, and a save older than
 *  that is never taken for this run's. */
export function serverRunStart(browserStartMs: number, serverOffsetMs: number): number {
  return browserStartMs + serverOffsetMs;
}

/** True when the list has the session with an `updated_at` not older than the run's start. */
export function showsRun(list: readonly SessionMeta[], id: string, runStartServerMs: number): boolean {
  const s = list.find((x) => x.id === id);
  return s !== undefined && Date.parse(s.updated_at) >= runStartServerMs;
}

/** True when a run error is the recorder's refusal at admission (nothing to reconcile). */
export function isRefusal(message: string): boolean {
  return REFUSED_RUN_MESSAGES.some((m) => message.includes(m));
}

/** True when a CUSTOM event is the recorder's report that session `id` could not be saved. */
export function isSaveFailed(event: { name: string; value?: unknown }, id: string): boolean {
  const value = event.value as { session?: unknown } | null | undefined;
  return event.name === SAVE_FAILED_EVENT && typeof value === "object" && value !== null && value.session === id;
}

/** GET /api/sessions, as lib/client.ts's fetchSessions, plus the clock offset its `Date` header
 *  gives. Throws on a non-200. */
export async function fetchSessionList(f?: Fetch): Promise<ListResult> {
  const res = await (f ?? ((input, init) => fetch(input, init)))("/api/sessions", { cache: "no-store" });
  if (res.status !== 200) throw new Error(`Loading the sessions failed (${res.status})`);
  const list = (await res.json()) as SessionMeta[];
  return { list, serverOffsetMs: clockOffset(res.headers.get("date"), Date.now()) };
}

/** Fetch the list once, then up to RECONCILE_RETRIES more times RECONCILE_DELAY_MS apart, until
 *  it shows the run that started at `browserStartMs` (the browser's clock; each fetch's `Date`
 *  header converts it to server time). `saved` false: it never did (the page shows
 *  SAVE_FAILED_MESSAGE). The last list fetched is returned either way, for the sidebar. A fetch
 *  that throws ends the loop: the caller shows that error instead. */
export async function reconcile(
  fetchList: FetchList,
  id: string,
  browserStartMs: number,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<{ list: SessionMeta[]; saved: boolean }> {
  for (let retry = 0; ; retry++) {
    const { list, serverOffsetMs } = await fetchList();
    if (showsRun(list, id, serverRunStart(browserStartMs, serverOffsetMs))) return { list, saved: true };
    if (retry === RECONCILE_RETRIES) return { list, saved: false };
    await sleep(RECONCILE_DELAY_MS);
  }
}
