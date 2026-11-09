"use client";
// The holder of one session's agent: a private CopilotKit agent, `spe-<id>`, on thread `<id>`, routed to the
// runtime's agent `spe`. It renders nothing; the page keeps one mounted for each session it shows or is
// streaming (lib/live-sessions.ts, `held`), keyed by the id, so the agent, its messages and its run last
// exactly as long as that need. The chat is drawn on the open session's agent by its id (agentIdOf), and a
// run goes on in its holder while another session is open. A session whose run is going elsewhere (another
// tab, or before a reload) is rejoined from here: `rejoin` connects its agent to that run (lib/rejoin.ts).
import type { Message } from "@ag-ui/client";
import { UseAgentUpdate, isAbortError, useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { useEffect, useRef } from "react";
import type { FetchList } from "../lib/reconcile.ts";
import { rejoinAgent } from "../lib/rejoin.ts";
import type { SessionMeta } from "../lib/sessions.ts";
import { useRunReconcile } from "./use-run-reconcile";

export const agentIdOf = (id: string) => `spe-${id}`;

type Props = {
  id: string;
  /** The page's list fetch: every list goes through one, so an older one arriving late is not applied. */
  fetchList: FetchList;
  /** The session's stored messages (`GET`), set on the agent at a rejoined run's end (lib/run-watch.ts). */
  fetchMessages: (id: string) => Promise<Message[] | null>;
  /** Put on the agent once it is ready: the session's stored messages, or [] for a New chat. */
  initialMessages: Message[];
  /** The registered agent exists: the page may draw CopilotChat on it. */
  onReady: (id: string) => void;
  onRunStarted: (id: string) => void;
  /** After the list fetched for the ended run has gone to onList (or failed). */
  onRunEnded: (id: string) => void;
  /** The ended run is in the list (a New chat's title waits for it if it was not listed at the start). */
  onRecorded: (id: string) => void;
  onList: (list: SessionMeta[]) => void;
  onError: (id: string, message: string) => void;
  /** The agent's messages changed (a run's stream). A chat drawn on this agent after its run started is not
   *  among that run's subscribers (AG-UI copies them as a run starts), so the page re-renders it from here. */
  onMessages: (id: string) => void;
  /** The session has a run going that this page does not stream (its GET or a list answered `running`):
   *  connect to it, once while this stays true. */
  rejoin: boolean;
  /** The connect has ended, however (the run's own end still comes through onRunEnded). */
  onRejoined: (id: string) => void;
};

const RUN_FAILED = "The agent run failed.";

export function SessionAgent({
  id, fetchList, fetchMessages, initialMessages, onReady, onRunStarted, onRunEnded, onRecorded, onList, onError, onMessages,
  rejoin, onRejoined,
}: Props): null {
  const { copilotkit } = useCopilotKit();
  // First a provisional agent (`isReady` false), then, on a later render, the registered one: messages set
  // on the provisional one are lost, so everything below waits for `isReady` and re-runs on a new agent.
  const { agent, isReady } = useAgent({
    agentId: agentIdOf(id),
    runtimeAgentId: "spe",
    threadId: id,
    updates: [UseAgentUpdate.OnRunStatusChanged],
  });
  const props = {
    initialMessages, onReady, onRunStarted, onRunEnded, onRecorded, onList, onError, onMessages, onRejoined,
  };
  const latest = useRef(props);
  latest.current = props;

  // Once per holder: a later agent object (none in practice) would otherwise be reset to a history older
  // than the run it has streamed.
  const seeded = useRef(false);
  useEffect(() => {
    if (!isReady) return;
    if (!seeded.current) {
      seeded.current = true;
      agent.setMessages(latest.current.initialMessages);
    }
    latest.current.onReady(id);
  }, [agent, isReady, id]);

  // A run's session is this holder's, whichever session is open when it starts or ends.
  const { noteRunError, rejoining, rejoined } = useRunReconcile(agent, {
    id,
    fetchList,
    fetchMessages,
    onList: (list) => latest.current.onList(list),
    onError: (message) => latest.current.onError(id, message),
    onStarted: (sid) => latest.current.onRunStarted(sid),
    onRecorded: (sid) => latest.current.onRecorded(sid),
    onEnded: (sid) => latest.current.onRunEnded(sid),
  });

  // This agent's own errors, open or not: the chat's onError hears only the open session's agent.
  useEffect(() => {
    const sub = agent.subscribe({
      onRunErrorEvent: ({ event }) => {
        if (event.code === "abort") return; // the stop button: not an error
        const message = String(event.message ?? "");
        noteRunError(message);
        latest.current.onError(id, message || RUN_FAILED);
      },
      // Subscribed before any run of this holder's starts, so every run's changes reach it.
      onMessagesChanged: () => latest.current.onMessages(id),
      onRunFailed: ({ error }) => {
        if (isAbortError(error)) return;
        noteRunError(error.message);
        latest.current.onError(id, error.message || RUN_FAILED);
      },
    });
    return () => sub.unsubscribe();
  }, [agent, id, noteRunError]);

  // Rejoin: after the seeding above (declared first, so it runs first in the same commit), so the history the
  // replay is matched against is the one just set. The connect goes on if the page drops the request
  // meanwhile; one at a time.
  const connecting = useRef(false);
  useEffect(() => {
    if (!isReady || !rejoin || !seeded.current || connecting.current) return;
    connecting.current = true;
    rejoining();
    rejoinAgent(agent, () => copilotkit.connectAgent({ agent }))
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        latest.current.onError(id, e instanceof Error && e.message ? e.message : RUN_FAILED);
      })
      .finally(() => {
        connecting.current = false;
        rejoined();
        latest.current.onRejoined(id);
      });
  }, [agent, isReady, rejoin, id, copilotkit, rejoining, rejoined]);

  return null;
}
