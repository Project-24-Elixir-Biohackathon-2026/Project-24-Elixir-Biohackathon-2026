// When the page fetches the session list on its own (spec §6 *Refresh*): besides load, run ends and metadata
// changes, on `visibilitychange` (visible) and `focus`, and every POLL_MS while the list shows a session
// running that no holder in this page streams (a run from another tab, or from before a reload), until it
// shows none. Pure: no React, no clock.
import { runningIds } from "./live-sessions.ts";
import type { Live } from "./live-sessions.ts";
import { LIST_FAILED } from "./run-watch.ts";
import type { SessionMeta } from "./sessions.ts";

export const POLL_MS = 2000;

/** True while the list shows a session running that no holder in the page streams. */
export function needsPoll(list: readonly SessionMeta[], live: Live): boolean {
  for (const id of runningIds(list, live)) if (!live.streaming.has(id)) return true;
  return false;
}

/** The error bar's text once a fetched list is applied: a failed list fetch's error goes (the list loads
 *  again), any other error stays. `listError` is the text the last failed refresh showed, if any; a run end's
 *  failed fetch shows LIST_FAILED (lib/run-watch.ts), bare or after its session's title (lib/run-error.ts). */
export function afterListApplied(shown: string | null, listError: string | null): string | null {
  if (listError !== null && shown === listError) return null;
  if (shown === LIST_FAILED || shown?.endsWith(`”: ${LIST_FAILED}`)) return null;
  return shown;
}

/** The sessions whose rejoin failed before its run started, still not to be rejoined: each poll's list would
 *  otherwise connect again (one /info and /connect every POLL_MS). One goes once a list shows it not running,
 *  or not at all; `failed` itself when none goes. */
export function stillFailed(failed: ReadonlySet<string>, list: readonly SessionMeta[]): ReadonlySet<string> {
  const running = new Set(list.filter((s) => s.running).map((s) => s.id));
  if ([...failed].every((id) => running.has(id))) return failed;
  return new Set([...failed].filter((id) => running.has(id)));
}
