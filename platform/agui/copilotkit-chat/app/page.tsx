"use client";
// Chat with agent `spe`, and a sidebar of sessions. Each tool call is a collapsible card: name,
// status, arguments and the first lines of the result. Everything is rendered as text, never HTML.
// Sessions are recorded on the server (lib/recorder.ts); this page only reads them and changes
// their metadata. The open session is in the URL (`?session=<id>`), so a reload reopens it.
import type { Message } from "@ag-ui/client";
import {
  CopilotChat,
  CopilotChatConfigurationProvider,
  CopilotKitProvider,
  useAgent,
  useDefaultRenderTool,
} from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSession, fetchSessions, removeSession, updateSession } from "../lib/client.ts";
import { searchWith, sessionFromSearch } from "../lib/session-url.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
import { ChatHeader } from "./chat-header";
import { ChevronRight } from "./icons";
import { Sidebar } from "./sidebar";
import { useHydrated } from "./use-hydrated";
import { useRunReconcile } from "./use-run-reconcile";

const MAX_RESULT_LINES = 40;
const MAX_RESULT_CHARS = 4000;

type ToolProps = {
  name: string;
  parameters: unknown;
  status: "inProgress" | "executing" | "complete";
  result: string | undefined;
};

function preview(result: string): string {
  let text = result;
  try {
    text = JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    // not JSON: show as is
  }
  const lines = text.split("\n");
  let shown = lines.slice(0, MAX_RESULT_LINES).join("\n");
  if (shown.length > MAX_RESULT_CHARS) shown = shown.slice(0, MAX_RESULT_CHARS);
  return shown.length < text.length ? `${shown}\n… (${text.length - shown.length} more characters)` : shown;
}

function brief(name: string, parameters: unknown): string {
  if (parameters && typeof parameters === "object") {
    const p = parameters as Record<string, unknown>;
    for (const key of ["command", "path", "pattern", "query", "process_id"]) {
      if (typeof p[key] === "string" || typeof p[key] === "number") return String(p[key]);
    }
  }
  return "";
}

// Under the composer, where claude.ai and chatgpt.com keep their notice; the header holds the title only.
const LABELS = {
  chatDisclaimerText: "SPE agent · runs inside the secure processing environment · every tool call is shown",
  chatInputPlaceholder: "Message the SPE agent",
};

const STATUS: Record<ToolProps["status"], string> = {
  inProgress: "preparing…",
  executing: "running…",
  complete: "done",
};

function ToolCard({ name, parameters, status, result }: ToolProps) {
  return (
    <details className="spe-tool">
      <summary>
        <ChevronRight className="spe-tool-chevron" />
        <span className="spe-tool-name">{name}</span>
        <span className="spe-tool-brief">{brief(name, parameters)}</span>
        <span className="spe-tool-status">{STATUS[status]}</span>
      </summary>
      <div className="spe-tool-label">arguments</div>
      <pre>{JSON.stringify(parameters ?? {}, null, 2)}</pre>
      {result !== undefined && (
        <>
          <div className="spe-tool-label">result</div>
          <pre>{preview(result)}</pre>
        </>
      )}
    </details>
  );
}

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "The request failed.";
}

// Puts `id` into the URL (or drops the parameter), without a navigation or a history entry.
function showInUrl(id: string | null): void {
  const { pathname, search, hash } = window.location;
  window.history.replaceState(null, "", `${pathname}${searchWith(search, id)}${hash}`);
}

function Chat() {
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const activeRef = useRef<string | null>(null);
  // Bumped by every open()/startNew() call, so a response from a call that is no longer the
  // latest (a second click while the first's fetch is still in flight) is ignored on arrival.
  const requestRef = useRef(0);
  const { agent, isReady } = useAgent({ agentId: "spe" });
  useDefaultRenderTool({ render: (props) => <ToolCard {...props} /> });
  // One owner of "safe to click": passed down to every button that starts an action from the
  // sidebar and header, so a click before hydration is disabled rather than dropped. Hydration
  // alone is not enough: the first-load effect below (startNew()/open(), gated on `isReady`) must
  // also have run, or an early New chat/row-open call sets `active` itself and mounts the chat
  // before the agent is ready to run anything, the same way a click that lands between hydration
  // and `isReady` would, just without a dropped click to show for it. `isReady` alone still leaves
  // a sub-frame window open between the render where it flips (committing enabled buttons) and the
  // first-load effect that runs after that commit, so `ready` also waits for the effect itself:
  // `active !== null` is only ever false before that effect has set it (every one of its paths —
  // `open()`'s success, its not-found/error fallback to `startNew()`, and the no-parameter
  // `startNew()` — ends by calling `select()`, which sets `active`), so this cannot leave `ready`
  // false once the agent is actually ready, including with an empty session list.
  const ready = useHydrated() && isReady && active !== null;

  // After each run (finished, failed or stopped) the list, fetched until it shows that run; once the
  // open session is in it (its first run recorded), the URL names it.
  const onList = useCallback((list: SessionMeta[]) => {
    setSessions(list);
    const id = activeRef.current;
    if (id && list.some((s) => s.id === id)) showInUrl(id);
  }, []);
  const { busy, noteRunError } = useRunReconcile({ openId: active ?? "", onList, onError: setError });

  // The history goes onto the agent first, then CopilotChat remounts on the new thread
  // (key={id}): a freshly mounted chat on a non-explicit thread keeps the agent's messages,
  // and makes no connect request that would clear them (README, Sessions).
  const select = useCallback((id: string, messages: Message[]) => {
    agent.setMessages(messages);
    activeRef.current = id;
    setActive(id);
  }, [agent]);

  const refresh = useCallback(async (): Promise<SessionMeta[] | null> => {
    try {
      const list = await fetchSessions();
      setSessions(list);
      return list;
    } catch (e) {
      setError(messageOf(e));
      return null;
    }
  }, []);

  // New chat: a fresh thread id and an empty history; it joins the list once its first run is recorded.
  const startNew = useCallback(() => {
    requestRef.current += 1;
    select(crypto.randomUUID(), []);
    showInUrl(null);
  }, [select]);

  const open = useCallback(async (id: string) => {
    const requestId = (requestRef.current += 1);
    try {
      const session = await fetchSession(id);
      if (requestId !== requestRef.current) return; // superseded by a later open()/startNew()
      if (!session) {
        // Deleted, or never recorded: a new session, without an error bar.
        startNew();
        void refresh();
        return;
      }
      select(id, session.messages);
      showInUrl(id);
    } catch (e) {
      if (requestId !== requestRef.current) return; // superseded by a later open()/startNew()
      setError(messageOf(e));
      // On first load (no session opened yet) this was a failed attempt to open the
      // id named in the URL: fall back to a new session, and make sure the URL no
      // longer names a session the page did not open.
      if (activeRef.current === null) {
        startNew();
        showInUrl(null);
      }
    }
  }, [refresh, select, startNew]);

  // First load, once the runtime's agent is there (messages set on the provisional one are lost).
  useEffect(() => {
    if (!isReady || activeRef.current !== null) return;
    void refresh();
    const id = sessionFromSearch(window.location.search);
    if (id) void open(id);
    else startNew(); // no parameter, or a malformed one: dropped
  }, [isReady, open, refresh, startNew]);

  const onDeleted = useCallback((id: string) => {
    if (id === activeRef.current) startNew();
    void refresh();
  }, [refresh, startNew]);

  // The header's menu: the same PATCH and DELETE as the row's, on the open session.
  const patchOpen = useCallback(async (patch: MetaPatch) => {
    const id = activeRef.current;
    if (id === null) return;
    await updateSession(id, patch);
    await refresh();
  }, [refresh]);
  const deleteOpen = useCallback(async () => {
    const id = activeRef.current;
    if (id === null) return;
    try {
      await removeSession(id);
      onDeleted(id);
    } catch (e) {
      setError(messageOf(e));
    }
  }, [onDeleted]);
  const knownTags = [...new Set(sessions.flatMap((s) => s.tags))].sort();

  return (
    <div className="spe-layout">
      <Sidebar
        sessions={sessions}
        knownTags={knownTags}
        activeId={active}
        // Switching sessions mid-run would put the new session's history on the agent that is
        // still streaming the old one's run. `running={busy}` below disables the buttons
        // themselves; these guards are the backstop for a click that lands before that
        // re-render reaches the DOM (busy comes from the same agent.isRunning, just a render
        // behind), so both stay ignored until the run truly ends either way.
        onNew={() => { if (!agent.isRunning) startNew(); }}
        onOpen={(id) => { if (!agent.isRunning) void open(id); }}
        onChanged={refresh}
        onDeleted={onDeleted}
        onError={setError}
        running={busy}
        ready={ready}
      />
      <div className="spe-page">
        <ChatHeader
          key={active ?? "none"}
          session={active === null ? undefined : (sessions.find((s) => s.id === active) ?? null)}
          knownTags={knownTags}
          running={busy}
          ready={ready}
          onPatch={patchOpen}
          onDelete={() => void deleteOpen()}
          onError={setError}
        />
        {error && (
          <div className="spe-error" role="alert">
            <span className="spe-error-text">{error}</span>
            <button type="button" onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}
        {active === null ? (
          <div className="spe-loading">Loading…</div>
        ) : (
          <CopilotChatConfigurationProvider agentId="spe" threadId={active} hasExplicitThreadId={false} labels={LABELS}>
            <CopilotChat
              key={active}
              agentId="spe"
              className="spe-chat"
              onError={(event) => {
                // The prop's type also admits a DOM error event; only CopilotKit's carries `error`.
                if ("error" in event && event.error instanceof Error) {
                  noteRunError(event.error.message);
                  setError(event.error.message || "The agent run failed.");
                }
              }}
            />
          </CopilotChatConfigurationProvider>
        )}
      </div>
    </div>
  );
}

// CopilotKit's own dark styles key on a `dark` class; this page follows the system setting.
function useSystemColorScheme() {
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.classList.toggle("dark", query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);
}

export default function Page() {
  useSystemColorScheme();
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit" agentId="spe" showDevConsole={false}>
      <Chat />
    </CopilotKitProvider>
  );
}
