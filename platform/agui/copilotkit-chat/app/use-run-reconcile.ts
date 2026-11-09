// One session's runs, on that session's own agent (./session-agent.tsx): the React side of
// lib/run-watch.ts, which says what happens after each run.
import type { AbstractAgent } from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef } from "react";
import { watchRuns } from "../lib/run-watch.ts";
import type { RunWatchOptions } from "../lib/run-watch.ts";

export function useRunReconcile(agent: AbstractAgent, opts: RunWatchOptions) {
  const latest = useRef(opts);
  latest.current = opts;
  const watch = useRef<ReturnType<typeof watchRuns> | null>(null);

  useEffect(() => {
    const w = watchRuns(agent, () => latest.current);
    watch.current = w;
    return () => {
      w.unsubscribe();
      if (watch.current === w) watch.current = null;
    };
  }, [agent]);

  /** Pass every run error here too: a refusal that reaches the page outside the stream (a failed request
   *  rather than a RUN_ERROR event) is then not reported as a failed save. */
  const noteRunError = useCallback((message: string) => watch.current?.noteRunError(message), []);
  /** Around a connect (lib/rejoin.ts): the run it starts ends by waitNotRunning, not by reconcile. */
  const rejoining = useCallback(() => watch.current?.rejoining(), []);
  const rejoined = useCallback(() => watch.current?.rejoined(), []);

  return { noteRunError, rejoining, rejoined };
}
