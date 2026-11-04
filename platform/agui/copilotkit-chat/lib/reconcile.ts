// After a run ends, fetch the session list until it shows that run: a run the server saw
// unsubscribed (the stream dropped before its end) is saved after the client has gone, so its
// save can land after the first fetch. Pure apart
// from the injected fetch and sleep, so `node --test` covers it. Browser code: it must not
// import recorder.ts (Node-only); reconcile.test.ts checks the copy below against it.
import type { Fetch } from "./client.ts";
import type { SessionMeta } from "./sessions.ts";

export const SAVE_FAILED_MESSAGE = "this session could not be saved";
export const RECONCILE_RETRIES = 5;
export const RECONCILE_DELAY_MS = 500;
/** RUN_ERROR messages the recorder ends a run with by itself: a refusal (nothing more is journaled for it)
 *  or a journal that could not be written. Nothing to reconcile: the list is fetched once. */
export const REFUSED_RUN_MESSAGES: readonly string[] = [
  "invalid session",
  "this session was deleted",
  "the chat UI is shutting down",
  "this session could not be saved",
  "this run carries no new message",
  "this run was already recorded",
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

/** True when the list has the session with a `last_run_at` not older than the run's start. Not
 *  `updated_at`: a rename, pin or tag change made during the run moves that one too. */
export function showsRun(list: readonly SessionMeta[], id: string, runStartServerMs: number): boolean {
  const s = list.find((x) => x.id === id);
  return s !== undefined && s.last_run_at !== null && Date.parse(s.last_run_at) >= runStartServerMs;
}

/** True when a run error is a run the recorder refused or ended itself (nothing more is journaled for
 *  it): nothing to reconcile. */
export function isRefusal(message: string): boolean {
  return REFUSED_RUN_MESSAGES.some((m) => message.includes(m));
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

/** Which sessions get a model title asked for: those started in this page load (New chat), once each, after
 *  a run of theirs that finished (RUN_FINISHED: the only run the server can title from) and was recorded. A
 *  session that had runs before this page load is never started here, so it is never asked for. */
export class TitleTrigger {
  private readonly fresh = new Set<string>();

  started(id: string): void {
    this.fresh.add(id);
  }

  /** True once per started session, for its first finished, recorded run; it is then forgotten. */
  take(id: string, finished: boolean): boolean {
    if (!finished || !this.fresh.has(id)) return false;
    this.fresh.delete(id);
    return true;
  }
}
