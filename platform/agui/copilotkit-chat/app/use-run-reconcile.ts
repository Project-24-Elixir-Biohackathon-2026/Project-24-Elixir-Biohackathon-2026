// The agent's run state for the page: `busy` while a run is in progress (the sidebar disables switching and
// New chat), and after each run, however it ended, the list is fetched until it shows that run, or the error
// bar says it was not saved. A run the recorder ended itself (a refusal, or a journal it could not write:
// its RUN_ERROR is already in the bar) is fetched once, without retries: nothing more is written for it.
// A run the list shows is passed to `onRecorded`, with whether it finished (RUN_FINISHED), for its title.
import { UseAgentUpdate, useAgent } from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef } from "react";
import type { SessionMeta } from "../lib/sessions.ts";
import { SAVE_FAILED_MESSAGE, fetchSessionList, isRefusal, reconcile } from "../lib/reconcile.ts";

type Options = {
  openId: string;
  onList: (list: SessionMeta[]) => void;
  onError: (message: string) => void;
  onRecorded: (id: string, finished: boolean) => void;
};
type Run = { id: string; startMs: number; refused: boolean; finished: boolean };

const LIST_FAILED = "The session list could not be loaded.";

export function useRunReconcile({ openId, onList, onError, onRecorded }: Options) {
  const { agent } = useAgent({ agentId: "spe", updates: [UseAgentUpdate.OnRunStatusChanged] });
  const latest = useRef({ openId, onList, onError, onRecorded });
  latest.current = { openId, onList, onError, onRecorded };
  const current = useRef<Run | null>(null); // the run in progress
  const last = useRef<Run | null>(null); // the latest run, in progress or ended

  useEffect(() => {
    const sub = agent.subscribe({
      onRunInitialized: () => {
        // The open session is read when a run starts: switching is disabled until it ends.
        current.current = last.current = {
          id: latest.current.openId, startMs: Date.now(), refused: false, finished: false,
        };
      },
      onRunErrorEvent: ({ event }) => {
        const run = current.current;
        if (run !== null && isRefusal(String(event.message ?? ""))) run.refused = true;
      },
      onRunFinishedEvent: () => {
        if (current.current !== null) current.current.finished = true;
      },
      onRunFinalized: () => {
        const ended = current.current;
        current.current = null;
        if (ended === null) return;
        if (ended.refused) {
          fetchSessionList()
            .then(({ list }) => latest.current.onList(list))
            .catch(() => latest.current.onError(LIST_FAILED));
          return;
        }
        reconcile(fetchSessionList, ended.id, ended.startMs)
          .then(({ list, saved }) => {
            latest.current.onList(list);
            if (saved) latest.current.onRecorded(ended.id, ended.finished);
            else latest.current.onError(SAVE_FAILED_MESSAGE);
          })
          .catch(() => latest.current.onError(LIST_FAILED));
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  /** Pass every run error here too: a refusal that reaches the page outside the stream (CopilotChat's
   *  onError) is then not reported as a failed save. */
  const noteRunError = useCallback((message: string) => {
    if (last.current !== null && isRefusal(message)) last.current.refused = true;
  }, []);

  return { busy: agent.isRunning, noteRunError };
}
