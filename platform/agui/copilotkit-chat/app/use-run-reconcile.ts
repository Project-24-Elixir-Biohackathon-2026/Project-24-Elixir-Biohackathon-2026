// The agent's run state for the page: `busy` while a run is in progress (the sidebar disables
// switching and New chat), and after each run, however it ended, the list is fetched until it
// shows that run, or the error bar says it was not saved. When the server reports the failed
// save itself (a CUSTOM event during the run), the bar says so at once and the list is fetched
// once, without retries.
import { UseAgentUpdate, useAgent } from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef } from "react";
import type { SessionMeta } from "../lib/sessions.ts";
import { SAVE_FAILED_MESSAGE, fetchSessionList, isRefusal, isSaveFailed, reconcile } from "../lib/reconcile.ts";

type Options = {
  openId: string;
  onList: (list: SessionMeta[]) => void;
  onError: (message: string) => void;
};
type Run = { id: string; startMs: number; refused: boolean; saveFailed: boolean };

const LIST_FAILED = "The session list could not be loaded.";

export function useRunReconcile({ openId, onList, onError }: Options) {
  const { agent } = useAgent({ agentId: "spe", updates: [UseAgentUpdate.OnRunStatusChanged] });
  const latest = useRef({ openId, onList, onError });
  latest.current = { openId, onList, onError };
  const current = useRef<Run | null>(null); // the run in progress
  const last = useRef<Run | null>(null); // the latest run, in progress or ended

  useEffect(() => {
    const sub = agent.subscribe({
      onRunInitialized: () => {
        // The open session is read when a run starts: switching is disabled until it ends.
        current.current = last.current = {
          id: latest.current.openId, startMs: Date.now(), refused: false, saveFailed: false,
        };
      },
      onCustomEvent: ({ event }) => {
        const run = current.current;
        if (run === null || run.saveFailed || !isSaveFailed(event, run.id)) return;
        run.saveFailed = true;
        latest.current.onError(SAVE_FAILED_MESSAGE);
      },
      onRunFinalized: () => {
        const ended = current.current;
        current.current = null;
        if (ended === null) return;
        if (ended.saveFailed) {
          // Already reported; the file will not change, so one fetch for the sidebar is enough.
          fetchSessionList()
            .then(({ list }) => latest.current.onList(list))
            .catch(() => latest.current.onError(LIST_FAILED));
          return;
        }
        reconcile(fetchSessionList, ended.id, ended.startMs)
          .then(({ list, saved }) => {
            latest.current.onList(list);
            // A run refused at admission writes nothing; its own error is already in the bar.
            if (!saved && !ended.refused) latest.current.onError(SAVE_FAILED_MESSAGE);
          })
          .catch(() => latest.current.onError(LIST_FAILED));
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  /** Pass every run error here, so a refusal at admission is not reported as a failed save.
   *  It may arrive just before or after the run ends: the reconciliation takes longer. */
  const noteRunError = useCallback((message: string) => {
    if (last.current !== null && isRefusal(message)) last.current.refused = true;
  }, []);

  return { busy: agent.isRunning, noteRunError };
}
