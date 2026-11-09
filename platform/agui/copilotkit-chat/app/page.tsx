"use client";
// Chat with the runtime's agent `spe`, and a sidebar of sessions. Each session the page shows or streams has
// an agent of its own, held by ./session-agent.tsx, so a run goes on while another session is open. Each tool
// call is a collapsible card: a status icon and title, the arguments as rows (run_command's as a `$ <command>`
// line) and the first lines of the result; calls made in a row, across model steps, are grouped
// (./tool-calls.tsx). Everything is rendered as text, never HTML.
// Sessions are recorded on the server (lib/recorder.ts); this page only reads them and changes
// their metadata. The open session is in the URL (`?session=<id>`), so a reload reopens it.
import type { Message } from "@ag-ui/client";
import {
  CopilotChat,
  CopilotChatConfigurationProvider,
  CopilotKitCoreErrorCode,
  CopilotKitCoreRuntimeConnectionStatus,
  CopilotKitProvider,
  useCopilotKit,
  useDefaultRenderTool,
} from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { HTMLAttributes } from "react";
import { askTitle, fetchSession, fetchSessions, removeSession, updateSession } from "../lib/client.ts";
import {
  EMPTY, held, isHeld, listed, openSession, runEnded, runningIds as runningIdsOf, runStarted,
} from "../lib/live-sessions.ts";
import type { Live } from "../lib/live-sessions.ts";
import { ListOrder } from "../lib/list-order.ts";
import { TitleTrigger, fetchSessionList, waitListed } from "../lib/reconcile.ts";
import { searchWith, sessionFromSearch } from "../lib/session-url.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
import { effectiveTheme, parseTheme } from "../lib/theme.ts";
import { ChatHeader } from "./chat-header";
import { CommandInput } from "./command-input";
import { AssistantOrCompaction } from "./compaction-divider";
import { ToolCard } from "./tool-calls";
import { SessionAgent, agentIdOf } from "./session-agent";
import { Sidebar } from "./sidebar";
import { ThemeControl } from "./theme-control";
import { useHydrated } from "./use-hydrated";

// A stable object: CopilotChat re-renders its message view when the slot value changes identity.
const MESSAGE_VIEW = { assistantMessage: AssistantOrCompaction };
// An opened or reloaded session lands on its newest content at once. CopilotChat's default (use-stick-to-bottom's
// `initial: "smooth"`) animated through the whole history first, about a second, and left the end below the fold
// meanwhile; a live send still scrolls smoothly (`resize`). The slot's props reach `<StickToBottom>` (CopilotKit
// 1.79.0, `CopilotChatView.ScrollView`'s `...props`), but its type leaves `initial` out, hence the cast; an upgrade
// that stops passing it through brings the animation back, which a reload of a long session shows. Stable for the
// same reason as MESSAGE_VIEW.
const SCROLL_VIEW = ({ initial: "instant" } satisfies { initial: "instant" | "smooth" | boolean }) as
  HTMLAttributes<HTMLDivElement>;

// Under the composer, where claude.ai and chatgpt.com keep their notice; the header holds the title only.
const LABELS = {
  chatDisclaimerText: "SPE agent · runs inside the secure processing environment · every tool call is shown",
  chatInputPlaceholder: "Message the SPE agent",
};

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "The request failed.";
}

// Puts `id` into the URL (or drops the parameter), without a navigation or a history entry.
function showInUrl(id: string | null): void {
  const { pathname, search, hash } = window.location;
  window.history.replaceState(null, "", `${pathname}${searchWith(search, id)}${hash}`);
}

// The errors CopilotKit raises for a run, which the run's holder also hears on its agent (./session-agent.tsx).
const RUN_ERROR_CODES: ReadonlySet<string> = new Set([
  CopilotKitCoreErrorCode.AGENT_RUN_FAILED,
  CopilotKitCoreErrorCode.AGENT_RUN_FAILED_EVENT,
  CopilotKitCoreErrorCode.AGENT_RUN_ERROR_EVENT,
  CopilotKitCoreErrorCode.AGENT_THREAD_LOCKED,
]);

const UNREACHABLE = "The agent runtime is unreachable; reload the page.";
const UNREACHABLE_AFTER_MS = 15_000;

function Chat() {
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const sessionsRef = useRef<SessionMeta[]>([]);
  // The sessions this page shows or streams (lib/live-sessions.ts); `live.open` is the open one. The ref is
  // the current value for callbacks, the state the one rendered: setLive writes both.
  const [live, setLiveState] = useState<Live>(EMPTY);
  const liveRef = useRef<Live>(EMPTY);
  // The holders whose agent is registered: CopilotChat looks its agent up by id and throws if it is not
  // there yet, so the chat waits for this. An id leaves it with its holder (setLive).
  const [agentsReady, setAgentsReady] = useState<ReadonlySet<string>>(new Set());
  // What each holder puts on its agent once ready: the GET's messages, or [] for a New chat.
  const initial = useRef(new Map<string, Message[]>());
  // Bumped by every open()/startNew() call, so a response from a call that is no longer the
  // latest (a second click while the first's fetch is still in flight) is ignored on arrival.
  const requestRef = useRef(0);
  const { copilotkit } = useCopilotKit();
  const connected = copilotkit.runtimeConnectionStatus === CopilotKitCoreRuntimeConnectionStatus.Connected;
  // `group`: CopilotKit groups the calls this draws, across the model's steps (./tool-calls.tsx).
  useDefaultRenderTool({ render: (props) => <ToolCard {...props} />, group: true });
  const active = live.open;
  // One owner of "safe to click": passed down to every button that starts an action from the
  // sidebar and header, so a click before hydration is disabled rather than dropped. Hydration
  // alone is not enough: the first-load effect below (startNew()/open(), gated on the runtime having
  // answered) must also have run, or an early New chat/row-open call opens a session itself before the
  // page has read the URL. `connected` alone still leaves a sub-frame window open between the render where
  // it flips (committing enabled buttons) and the first-load effect that runs after that commit, so
  // `ready` also waits for the effect itself: `active !== null` is only ever false before that effect
  // has opened a session (every one of its paths — `open()`'s success, its not-found/error fallback to
  // `startNew()`, and the no-parameter `startNew()` — ends with one open), so this cannot leave `ready`
  // false once the runtime is there, including with an empty session list.
  const ready = useHydrated() && connected && active !== null;

  // Every list fetch is stamped as it starts, and only a list newer than the last applied is applied: a
  // late, older list would otherwise mark a session the newer one showed as gone, for good.
  const listOrder = useRef(new ListOrder()).current;
  const fetchList = useRef(listOrder.wrap(fetchSessionList)).current;

  const startNewRef = useRef<() => void>(() => {});
  const setLive = useCallback((next: Live) => {
    liveRef.current = next;
    setLiveState(next);
    const keep = new Set(held(next));
    for (const id of initial.current.keys()) if (!keep.has(id)) initial.current.delete(id);
    setAgentsReady((r) => ([...r].every((id) => keep.has(id)) ? r : new Set([...r].filter((id) => keep.has(id)))));
  }, []);

  // Every list the page fetches comes through here: the sidebar shows it, the live sessions learn which
  // ids left it (an open session that left it while idle is replaced by a new one), and once the open
  // session is in it (its first run recorded), the URL names it.
  const applyList = useCallback((list: SessionMeta[]) => {
    if (!listOrder.accept(list)) return; // older than one already applied
    sessionsRef.current = list;
    setSessions(list);
    const { live: next, startNew } = listed(liveRef.current, new Set(list.map((s) => s.id)));
    setLive(next);
    if (startNew) startNewRef.current();
    else {
      const id = liveRef.current.open;
      if (id && list.some((s) => s.id === id)) showInUrl(id);
    }
  }, [listOrder, setLive]);
  const refresh = useCallback(async (): Promise<SessionMeta[] | null> => {
    try {
      const list = await listOrder.track(() => fetchSessions(), (l) => l);
      applyList(list);
      return list;
    } catch (e) {
      setError(messageOf(e));
      return null;
    }
  }, [applyList, listOrder]);

  // A New chat's first run, as it starts: the list is fetched until it has the session (the server lists it
  // once the run's question is on disk, before the agent answers), so the sidebar and header show the first
  // message as the title at once; then one call for its model-written title, from that question (the server
  // writes one only if the session has no title of its own), which can land before the answer ends. The list
  // is refetched rather than patched with the answer, so a rename that lands while the title call is in
  // flight is not overwritten by it. Not listed in time, or the list failing, re-arms the session: the call is
  // then made once its run is recorded (onRecorded), or at its next run.
  const titles = useRef(new TitleTrigger());
  const askFor = useCallback((id: string) => {
    askTitle(id)
      .then(() => refresh())
      .catch((e: unknown) => console.warn(`session ${id}: no model title: ${messageOf(e)}`));
  }, [refresh]);
  const onRunStarted = useCallback((id: string) => {
    setLive(runStarted(liveRef.current, id));
    if (!titles.current.take(id)) return;
    waitListed(fetchList, id)
      .then(({ list, listed: isListed }) => {
        applyList(list);
        if (isListed) askFor(id);
        else titles.current.started(id);
      })
      .catch(() => titles.current.started(id));
  }, [applyList, askFor, fetchList, setLive]);
  const onRecorded = useCallback((id: string) => {
    if (titles.current.take(id)) askFor(id);
  }, [askFor]);
  // A run ended, in any session, open or not, and its list has been applied: the session's agent is dropped
  // unless it is open; an open session that left the list meanwhile is replaced by a new one.
  const onRunEnded = useCallback((id: string) => {
    if (midRun.current === id) midRun.current = null;
    const { live: next, startNew } = runEnded(liveRef.current, id);
    setLive(next);
    if (startNew) startNewRef.current();
  }, [setLive]);
  const onAgentReady = useCallback((id: string) => {
    setAgentsReady((r) => (r.has(id) ? r : new Set(r).add(id)));
  }, []);
  // A run's errors, in any session, open or not: CopilotChat's onError hears only the open session's agent,
  // so each holder reports its own (and the chat's onError, below, leaves run errors to it).
  const onAgentError = useCallback((_id: string, message: string) => {
    setError(message);
  }, []);

  // The open session, when its chat was drawn while its run was already streaming (opened again mid-run, or
  // remounted by a switch back): that chat is not among the run's subscribers, so it is re-rendered on each of
  // the agent's message changes until the run ends. A chat drawn before its run starts hears the run itself.
  const midRun = useRef<string | null>(null);
  const [, redrawChat] = useReducer((x: number) => x + 1, 0);
  const onAgentMessages = useCallback((id: string) => {
    if (id === midRun.current && id === liveRef.current.open) redrawChat();
  }, []);

  // New chat: a fresh thread id and an empty history, on a new agent; it joins the list once its first run starts.
  const startNew = useCallback(() => {
    requestRef.current += 1;
    midRun.current = null;
    const id = crypto.randomUUID();
    titles.current.started(id);
    initial.current.set(id, []);
    setLive(openSession(liveRef.current, id));
    showInUrl(null);
  }, [setLive]);
  startNewRef.current = startNew;

  const open = useCallback(async (id: string) => {
    const requestId = (requestRef.current += 1);
    // A session with an agent in this page is shown as it is, its run still streaming if it is: its messages
    // are newer than the journal's, so no fetch.
    if (isHeld(liveRef.current, id)) {
      midRun.current = liveRef.current.streaming.has(id) ? id : null;
      setLive(openSession(liveRef.current, id));
      showInUrl(sessionsRef.current.some((s) => s.id === id) ? id : null);
      return;
    }
    try {
      const session = await fetchSession(id);
      if (requestId !== requestRef.current) return; // superseded by a later open()/startNew()
      if (!session) {
        // Deleted, or never recorded: a new session, without an error bar.
        startNew();
        void refresh();
        return;
      }
      initial.current.set(id, session.messages);
      // Only where the open session changes: the one still open while this fetch ran kept streaming.
      midRun.current = null;
      setLive(openSession(liveRef.current, id));
      showInUrl(id);
    } catch (e) {
      if (requestId !== requestRef.current) return; // superseded by a later open()/startNew()
      setError(messageOf(e));
      // On first load (no session opened yet) this was a failed attempt to open the
      // id named in the URL: fall back to a new session, and make sure the URL no
      // longer names a session the page did not open.
      if (liveRef.current.open === null) {
        startNew();
        showInUrl(null);
      }
    }
  }, [refresh, setLive, startNew]);

  // First load, once the runtime has answered: a holder's agent registers while the runtime is still
  // pending, so the runtime's status, not an agent's `isReady`, says the page can run anything.
  const firstLoad = useRef(false);
  useEffect(() => {
    if (!connected || firstLoad.current) return;
    firstLoad.current = true;
    void refresh();
    const id = sessionFromSearch(window.location.search);
    if (id) void open(id);
    else startNew(); // no parameter, or a malformed one: dropped
  }, [connected, open, refresh, startNew]);

  // A runtime that never answers would leave "Loading…" up for good: say so after a while, and take
  // the message back once it does answer.
  useEffect(() => {
    if (connected) {
      setError((e) => (e === UNREACHABLE ? null : e));
      return;
    }
    const timer = setTimeout(() => setError(UNREACHABLE), UNREACHABLE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [connected]);

  const onDeleted = useCallback((id: string) => {
    if (id === liveRef.current.open) startNew();
    void refresh();
  }, [refresh, startNew]);

  // The header's menu: the same PATCH and DELETE as the row's, on the open session.
  const patchOpen = useCallback(async (patch: MetaPatch) => {
    const id = liveRef.current.open;
    if (id === null) return;
    await updateSession(id, patch);
    await refresh();
  }, [refresh]);
  const deleteOpen = useCallback(async () => {
    const id = liveRef.current.open;
    if (id === null) return;
    try {
      await removeSession(id);
      onDeleted(id);
    } catch (e) {
      setError(messageOf(e));
    }
  }, [onDeleted]);
  const knownTags = [...new Set(sessions.flatMap((s) => s.tags))].sort();
  // The sidebar's running mark and Delete's refusal (decision 44): the list's own `running` ids ∪ this
  // page's streaming ones (lib/live-sessions.ts).
  const runningIds = useMemo(() => runningIdsOf(sessions, live), [sessions, live]);

  return (
    <div className="spe-layout">
      {held(live).map((id) => (
        <SessionAgent
          key={id}
          id={id}
          fetchList={fetchList}
          initialMessages={initial.current.get(id) ?? []}
          onReady={onAgentReady}
          onRunStarted={onRunStarted}
          onRunEnded={onRunEnded}
          onRecorded={onRecorded}
          onList={applyList}
          onError={onAgentError}
          onMessages={onAgentMessages}
        />
      ))}
      <Sidebar
        sessions={sessions}
        knownTags={knownTags}
        activeId={active}
        // Switching and New chat stay enabled during a run: the run goes on in its session's agent.
        onNew={startNew}
        onOpen={(id) => void open(id)}
        onChanged={refresh}
        onDeleted={onDeleted}
        onError={setError}
        runningIds={runningIds}
        ready={ready}
      />
      <div className="spe-page">
        <ChatHeader
          key={active ?? "none"}
          session={active === null ? undefined : (sessions.find((s) => s.id === active) ?? null)}
          knownTags={knownTags}
          runningIds={runningIds}
          ready={ready}
          onPatch={patchOpen}
          onDelete={() => void deleteOpen()}
          onError={setError}
        />
        <ThemeControl />
        {error && (
          <div className="spe-error" role="alert">
            <span className="spe-error-text">{error}</span>
            <button type="button" onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}
        {active === null || !agentsReady.has(active) ? (
          <div className="spe-loading">Loading…</div>
        ) : (
          <CopilotChatConfigurationProvider
            agentId={agentIdOf(active)}
            threadId={active}
            hasExplicitThreadId={false}
            labels={LABELS}
          >
            <CopilotChat
              key={active}
              agentId={agentIdOf(active)}
              className="spe-chat"
              messageView={MESSAGE_VIEW}
              scrollView={SCROLL_VIEW}
              input={CommandInput}
              onError={(event) => {
                // The prop's type also admits a DOM error event; only CopilotKit's carries `error`. A run's
                // own errors are the holder's to report (onAgentError), so they are not shown twice.
                if (!("error" in event) || !(event.error instanceof Error)) return;
                if (RUN_ERROR_CODES.has(event.code)) return;
                setError(event.error.message || "The agent run failed.");
              }}
            />
          </CopilotChatConfigurationProvider>
        )}
      </div>
    </div>
  );
}

// CopilotKit's own dark styles key on a `dark` class; this follows the *effective* theme (the
// theme toggle's forced choice, via <html>'s data-theme attribute, or else the system setting),
// updating when either changes. The attribute is read fresh each time rather than mirrored into
// state, since app/theme-control.tsx (and the before-paint script in app/layout.tsx) are the
// only writers of it.
function useSystemColorScheme() {
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const choice = parseTheme(document.documentElement.getAttribute("data-theme"));
      document.documentElement.classList.toggle("dark", effectiveTheme(choice, query.matches) === "dark");
    };
    apply();
    query.addEventListener("change", apply);
    const attrs = new MutationObserver(apply);
    attrs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      query.removeEventListener("change", apply);
      attrs.disconnect();
    };
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
