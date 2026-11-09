// One session's runs, on that session's own agent (app/session-agent.tsx): after each run, however it ended,
// the list is fetched until it shows that run, or the error bar says it was not saved. A run the recorder
// ended itself (a refusal, or a journal it could not write: its RUN_ERROR is already in the bar) is fetched
// once, without retries: nothing more is written for it. `onStarted` hears each run as it starts, for a New
// chat's title; `onRecorded` once the list shows the run; `onEnded` last, once the list (or its error) has
// been passed on, so the page drops the agent only after it has seen that list. `onEnded` is for the latest
// run only: a run started before the previous one's list came back keeps the session streaming, and the
// page must not drop its agent. A rejoined run (a connect to a run already going, lib/rejoin.ts) has a start
// the page does not know, so its end waits for the list to show the session not running instead
// (waitNotRunning); a list without the session is the session deleted, which the page's list handling deals
// with, not an error bar. Once saved, the rejoined run's chat is set to the journal's messages (`GET`,
// `fetchMessages`) when they differ: the connect's replay may have added past runs the runtime holds in memory
// on a branch the journal's tip has left (lib/rejoin.ts appends whatever the history lacks). Not once a newer
// run has started, whose stream that would cut; a failed or empty GET keeps the chat as it is, with no error
// bar: the run is saved, and the session's next opening reads the journal. Pure apart from the agent, so
// `node --test` covers it.
import type { Message } from "@ag-ui/client";
import type { SessionMeta } from "./sessions.ts";
import { SAVE_FAILED_MESSAGE, isRefusal, reconcile, waitNotRunning } from "./reconcile.ts";
import type { FetchList } from "./reconcile.ts";

export type RunWatchOptions = {
  id: string;
  /** The page's list fetch, stamped with its order (lib/list-order.ts). */
  fetchList: FetchList;
  /** The session's stored messages (`GET /api/sessions/{id}`), null if it has none. */
  fetchMessages: (id: string) => Promise<Message[] | null>;
  onList: (list: SessionMeta[]) => void;
  onError: (message: string) => void;
  onStarted: (id: string) => void;
  onRecorded: (id: string) => void;
  onEnded: (id: string) => void;
};

/** The part of an AG-UI agent this needs. */
export type RunSource = {
  messages: Message[];
  setMessages(messages: Message[]): void;
  subscribe(s: {
    onRunInitialized?: () => void;
    onRunErrorEvent?: (p: { event: { message?: unknown } }) => void;
    onRunFinalized?: () => void;
  }): { unsubscribe(): void };
};

type Run = { startMs: number; refused: boolean; rejoined: boolean };

export const LIST_FAILED = "The session list could not be loaded.";

/** `opts` is read at each event, so the caller may pass its latest props. */
export function watchRuns(agent: RunSource, opts: () => RunWatchOptions, now: () => number = Date.now) {
  let current: Run | null = null; // the run in progress
  let last: Run | null = null; // the latest run, in progress or ended
  let rejoining = false; // a connect is under way: the next run to start is the one it rejoins
  // The journal's messages on the agent, when they differ, unless a newer run than `ended` has started.
  const showJournal = async (id: string, ended: Run) => {
    const stored = await opts().fetchMessages(id).catch(() => null);
    if (stored === null || last !== ended || current !== null) return;
    if (JSON.stringify(stored) !== JSON.stringify(agent.messages)) agent.setMessages(stored);
  };
  const sub = agent.subscribe({
    onRunInitialized: () => {
      current = last = { startMs: now(), refused: false, rejoined: rejoining };
      rejoining = false;
      opts().onStarted(opts().id);
    },
    onRunErrorEvent: ({ event }) => {
      if (current !== null && isRefusal(String(event.message ?? ""))) current.refused = true;
    },
    onRunFinalized: () => {
      const ended = current;
      current = null;
      if (ended === null) return;
      const { id } = opts();
      // Only the latest run ends the session: a newer one started since keeps it streaming.
      const done = () => { if (last === ended) opts().onEnded(id); };
      if (ended.refused) {
        opts().fetchList()
          .then(({ list }) => opts().onList(list))
          .catch(() => opts().onError(LIST_FAILED))
          .finally(done);
        return;
      }
      if (ended.rejoined) {
        waitNotRunning(opts().fetchList, id)
          .then(async ({ list, saved }) => {
            opts().onList(list);
            if (!list.some((s) => s.id === id)) return; // deleted: the list's own handling, no error bar
            if (!saved) {
              opts().onError(SAVE_FAILED_MESSAGE);
              return;
            }
            await showJournal(id, ended);
            opts().onRecorded(id);
          })
          .catch(() => opts().onError(LIST_FAILED))
          .finally(done);
        return;
      }
      reconcile(opts().fetchList, id, ended.startMs)
        .then(({ list, saved }) => {
          opts().onList(list);
          if (saved) opts().onRecorded(id);
          else opts().onError(SAVE_FAILED_MESSAGE);
        })
        .catch(() => opts().onError(LIST_FAILED))
        .finally(done);
    },
  });
  return {
    unsubscribe: () => sub.unsubscribe(),
    /** Just before a connect: the run it starts is a rejoined one. */
    rejoining: () => { rejoining = true; },
    /** Once the connect has ended, however: a connect that never started a run leaves no mark on the next. */
    rejoined: () => { rejoining = false; },
    /** Pass every run error here too: a refusal that reaches the page outside the stream (a failed request
     *  rather than a RUN_ERROR event) is then not reported as a failed save. */
    noteRunError: (message: string) => {
      if (last !== null && isRefusal(message)) last.refused = true;
    },
  };
}
