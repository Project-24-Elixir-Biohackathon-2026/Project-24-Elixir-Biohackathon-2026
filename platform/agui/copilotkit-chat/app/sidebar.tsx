"use client";
// The sessions sidebar: New chat, the title search (with `tag:` terms), the list the search shows
// (pinned first, then Today / Yesterday / Previous 7 days / Older), each row's menu, and Show hidden.
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
//
// One owner for what a row is doing: `Sidebar` holds which row has its menu, rename, tag editor or
// delete dialog open, so at most one row is ever busy, and opening a session, New chat, collapsing
// or another row's menu ends it. The close and focus rules follow Open WebUI's sidebar: the menu
// closes on a press outside it, Escape or a choice, and gives focus back to its ⋯ (after a press outside,
// only when the press left focus nowhere, so it never takes focus from a field or button); a rename is saved
// by Enter or a press outside the row and cancelled by Escape; a tag typed but not added is dropped.
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type { MouseEvent } from "react";
import { removeSession, renamePatch, tagSuggestions, updateSession, withTag, withoutTag } from "../lib/client.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
import { DEFAULT as DEFAULT_WIDTH, MAX as MAX_WIDTH, MIN as MIN_WIDTH, clampWidth, maxFor, parseWidth, stepWidth } from "../lib/sidebar-width.ts";
import { refocusIfLost } from "../lib/menu.ts";
import { filterSessions, sections } from "../lib/sidebar-view.ts";
import type { ViewFilter } from "../lib/sidebar-view.ts";
import { DeleteDialog } from "./delete-dialog";
import { Ellipsis, PencilSquare, SidebarToggle, Spinner } from "./icons";
import { Popover } from "./popover";
import { RenameInput, RowMenu } from "./row-menu";
import { HiddenToggle, SearchBox } from "./session-filters";
import { TagEditor } from "./tag-editor";

type SidebarProps = {
  sessions: SessionMeta[];
  knownTags: string[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onChanged: () => Promise<unknown>; // resolves once the list is fetched again
  onDeleted: (id: string) => void;
  onError: (message: string) => void;
  /** Every session with a run in progress, open or not (lib/live-sessions.ts): each of their rows shows the
   *  running mark and has its Delete disabled. Switching and New chat stay enabled during a run. */
  runningIds: ReadonlySet<string>;
  /** False until the page is safe to click: hydrated, the agent runtime connected, and the page's own
   *  first-load `startNew()`/`open()` has actually run (not just become due). Every button here
   *  starts an action, so each stays disabled until then rather than risk a click landing before
   *  its handler is attached, before the runtime can run anything, or in the sub-frame window
   *  between the runtime connecting and that first-load effect running. */
  ready: boolean;
};

// What the one busy row is doing. `keyboard`: the menu was opened from the keyboard, so its first
// item takes focus. `suggest`: the tag suggestions are shown for what is typed.
type Busy =
  | { id: string; mode: "menu"; keyboard: boolean }
  | { id: string; mode: "rename"; draft: string }
  | { id: string; mode: "tags"; draft: string; suggest: boolean; error: string | null }
  | { id: string; mode: "delete" };

const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

// The sidebar's width, kept per browser. Read and written in try/catch: the page works without it.
const WIDTH_KEY = "spe.sidebarWidth";
const readStoredWidth = (): number => {
  try {
    return parseWidth(localStorage.getItem(WIDTH_KEY));
  } catch {
    return DEFAULT_WIDTH;
  }
};
const writeStoredWidth = (width: number): void => {
  try {
    localStorage.setItem(WIDTH_KEY, String(width));
  } catch {
    // no persistence without storage; the width still applies for this render
  }
};


export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError, runningIds, ready }: SidebarProps) {
  const [busy, setBusy] = useState<Busy | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  // DEFAULT_WIDTH on the server and on the first client render (so there is no hydration
  // mismatch); the stored width, if any, loads right after in an effect. The stored value itself
  // is never put through the viewport cap below, so a desktop width survives a visit from a phone.
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  // MAX_WIDTH until the viewport is known (effect: there is no window during SSR), then kept live
  // across a resize. Only used to report and limit the *live* range (aria, drag, keyboard); the
  // CSS `min(var(--sidebar-width), calc(100vw - 48px))` on `.spe-sidebar` is what actually stops a
  // wider `--sidebar-width` from causing horizontal page scroll.
  const [viewportMax, setViewportMax] = useState(MAX_WIDTH);
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);
  useEffect(() => setWidth(readStoredWidth()), []);
  useEffect(() => {
    const update = () => setViewportMax(maxFor(window.innerWidth));
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  const triggers = useRef(new Map<string, HTMLButtonElement>());
  const popover = useRef<HTMLDivElement>(null);
  // The session id whose tag change is in flight, until the list is fetched again: each patch is
  // the whole tag list, so a second add or remove before then (ignored) would start from the
  // list without the first change and undo it.
  const savingTag = useRef<string | null>(null);
  const [filter, setFilter] = useState<ViewFilter>({ query: "", showHidden: false });
  // `sessions` is every session the server lists; the filter decides which rows show.
  const visible = filterSessions(sessions, filter);
  const shown = sections(visible, new Date());
  const busySession = busy ? visible.find((s) => s.id === busy.id) : undefined;
  const suggestions = busy?.mode === "tags" && busy.suggest && busySession
    ? tagSuggestions(knownTags, busySession.tags, busy.draft)
    : [];

  const focusTrigger = (id: string) => triggers.current.get(id)?.focus();

  const save = async (id: string, patch: MetaPatch | null) => {
    if (!patch) return;
    try {
      await updateSession(id, patch);
      void onChanged();
    } catch (e) {
      onError(errorText(e, "Saving the change failed."));
    }
  };

  // Ends whatever is open. A rename in progress is saved if it changed the title (Open WebUI's
  // blur rule); a tag typed but not added is dropped (its tag editor's).
  const end = (returnFocus = false) => {
    if (!busy) return;
    setBusy(null);
    if (busy.mode === "rename" && busySession) void save(busy.id, renamePatch(busy.draft, busySession.title));
    if (returnFocus) focusTrigger(busy.id);
  };

  // The busy row left the list (hidden, deleted, or gone after a refresh): nothing is open.
  useEffect(() => {
    if (busy && !busySession) setBusy(null);
  }, [busy, busySession]);

  // A press outside ends it: outside the menu and its ⋯ for the popover, outside the row for a rename.
  // Capture phase, so it runs before the press's own target acts (another row opens, another ⋯ toggles).
  // The popover's ⋯ gets focus back if the press left it nowhere (lib/menu.ts, `refocusIfLost`).
  useEffect(() => {
    if (!busy || busy.mode === "delete") return;
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;
      const trigger = triggers.current.get(busy.id);
      if (busy.mode === "rename") {
        if (!trigger?.closest(".spe-row")?.contains(target)) end();
        return;
      }
      if (popover.current?.contains(target) || trigger?.contains(target)) return;
      end();
      const id = busy.id;
      if (e.pointerType !== "touch") refocusIfLost(document, () => triggers.current.get(id));
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  });

  // Escape, wherever focus is: the tag suggestions first, then the menu or editor. The rename input
  // and the dialog handle their own.
  useEffect(() => {
    if (!busy || busy.mode === "rename" || busy.mode === "delete") return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing || e.defaultPrevented) return;
      e.preventDefault();
      if (busy.mode === "tags" && suggestions.length > 0) setBusy({ ...busy, suggest: false });
      else end(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const toggleMenu = (id: string, e: MouseEvent) => {
    if (busy?.id === id && busy.mode === "rename") return; // inert while renaming
    if (busy?.id === id && (busy.mode === "menu" || busy.mode === "tags")) {
      end();
      return;
    }
    end();
    // A click with no pointer behind it (detail 0) is Enter or Space on the ⋯.
    setBusy({ id, mode: "menu", keyboard: e.detail === 0 });
  };
  const startRename = (s: SessionMeta) => {
    end();
    setBusy({ id: s.id, mode: "rename", draft: s.title });
  };
  const choose = (s: SessionMeta, patch: MetaPatch) => {
    end(true);
    void save(s.id, patch);
  };

  // The tag editor stays open for the next tag; on a failed save it keeps the text and shows why.
  const setTags = (id: string, change: (b: Extract<Busy, { mode: "tags" }>) => Busy) =>
    setBusy((b) => (b && b.mode === "tags" && b.id === id ? change(b) : b));
  const addTag = async (s: SessionMeta, text: string) => {
    if (!text.trim() || savingTag.current === s.id) return;
    const patch = withTag(s.tags, text);
    if (!patch) {
      setTags(s.id, (b) => ({ ...b, draft: "", suggest: false, error: null })); // already there
      return;
    }
    savingTag.current = s.id;
    try {
      await updateSession(s.id, patch);
      setTags(s.id, (b) => ({ ...b, draft: "", suggest: false, error: null }));
      await onChanged();
    } catch (e) {
      setTags(s.id, (b) => ({ ...b, draft: text, suggest: false, error: errorText(e, "Saving the tag failed.") }));
    } finally {
      savingTag.current = null;
    }
  };
  const removeTag = async (s: SessionMeta, tag: string) => {
    popover.current?.querySelector<HTMLInputElement>(".spe-tag-input")?.focus();
    if (savingTag.current === s.id) return;
    savingTag.current = s.id;
    try {
      await updateSession(s.id, withoutTag(s.tags, tag));
      setTags(s.id, (b) => ({ ...b, error: null }));
      await onChanged();
    } catch (e) {
      setTags(s.id, (b) => ({ ...b, error: errorText(e, "Saving the tag failed.") }));
    } finally {
      savingTag.current = null;
    }
  };

  const remove = async (id: string) => {
    setBusy(null);
    try {
      await removeSession(id);
      onDeleted(id);
    } catch (e) {
      onError(errorText(e, "Deleting the session failed."));
      focusTrigger(id);
    }
  };

  const newChat = () => { end(); onNew(); };

  // The resize handle: pointer drag (with pointer capture, so leaving the handle mid-drag still
  // tracks), Left/Right to step, double-click to reset. Every change is clamped (including to the
  // current viewport, read fresh here rather than trusted from state, in case a resize landed
  // between renders) and persisted.
  const resizeTo = (next: number) => {
    const clamped = Math.min(clampWidth(next), maxFor(window.innerWidth));
    setWidth(clamped);
    writeStoredWidth(clamped);
  };
  // The rendered width (the CSS cap can show less than `width` on a narrow viewport): a drag or a
  // key step starts from what is actually on screen, not the stored value, or the first presses do
  // nothing until the pointer or the steps catch up to it.
  const shownWidth = Math.min(width, viewportMax);
  const onResizerPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { pointerId: e.pointerId, startX: e.clientX, startWidth: shownWidth };
  };
  const onResizerPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== e.pointerId) return;
    resizeTo(drag.current.startWidth + (e.clientX - drag.current.startX));
  };
  const onResizerPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId === e.pointerId) drag.current = null;
  };
  const onResizerKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); resizeTo(stepWidth(shownWidth, -1)); }
    else if (e.key === "ArrowRight") { e.preventDefault(); resizeTo(stepWidth(shownWidth, 1)); }
  };

  if (collapsed) {
    return (
      <nav className="spe-sidebar spe-sidebar-collapsed" aria-label="Sessions">
        <button type="button" className="spe-icon-button" aria-label="Show sessions" title="Show sessions"
          onClick={() => setCollapsed(false)}><SidebarToggle /></button>
        <button type="button" className="spe-icon-button" aria-label="New chat" title="New chat"
          disabled={!ready} onClick={newChat}><PencilSquare /></button>
      </nav>
    );
  }

  const row = (s: SessionMeta) => {
    const mine = busy?.id === s.id ? busy : null;
    const popoverOpen = mine?.mode === "menu" || mine?.mode === "tags";
    const running = runningIds.has(s.id);
    const classes = ["spe-row"];
    if (s.id === activeId) classes.push("spe-row-active");
    if (s.hidden) classes.push("spe-row-hidden");
    if (popoverOpen) classes.push("spe-row-menu-open");
    if (mine?.mode === "rename") classes.push("spe-row-renaming");
    return (
      <li key={s.id} className={classes.join(" ")} data-session-id={s.id} data-running={running || undefined}>
        {mine?.mode === "rename" ? (
          <RenameInput
            value={mine.draft}
            onChange={(draft) => setBusy({ ...mine, draft })}
            onSave={() => { end(true); }}
            onLeave={() => end()}
            onCancel={() => { setBusy(null); focusTrigger(s.id); }}
          />
        ) : (
          <button type="button" className="spe-row-open" aria-current={s.id === activeId ? "page" : undefined}
            disabled={!ready} onClick={() => { end(); onOpen(s.id); }} onDoubleClick={() => startRename(s)}>
            {/* The Pinned section shows it; this tells a screen reader too. */}
            {s.pinned && <span className="spe-pin spe-sr-only">Pinned: </span>}
            <span className="spe-row-title">{s.title}</span>
          </button>
        )}
        {running && mine?.mode !== "rename" && (
          <span className="spe-row-running"><Spinner /><span className="spe-sr-only">Running</span></span>
        )}
        <button
          type="button"
          className="spe-row-menu"
          ref={(el) => { if (el) triggers.current.set(s.id, el); else triggers.current.delete(s.id); }}
          aria-label={`Menu for ${s.title}`}
          aria-haspopup="menu"
          aria-expanded={popoverOpen}
          disabled={!ready}
          aria-disabled={mine?.mode === "rename" || undefined}
          tabIndex={mine?.mode === "rename" ? -1 : undefined}
          onClick={(e) => toggleMenu(s.id, e)}
        ><Ellipsis /></button>
      </li>
    );
  };
  return (
    <nav className="spe-sidebar" aria-label="Sessions"
      // Scoped to this nav on purpose, not a shared ancestor: `.spe-sidebar`'s own CSS caps it
      // against the viewport (globals.css), so setting it anywhere else would need that cap too.
      style={{ "--sidebar-width": `${width}px` } as CSSProperties}>
      <div className="spe-sidebar-top">
        <span className="spe-brand">SPE agent</span>
        <button type="button" className="spe-icon-button spe-collapse" aria-label="Hide sessions" title="Hide sessions"
          onClick={() => { end(); setCollapsed(true); }}><SidebarToggle /></button>
      </div>
      <div
        className="spe-sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuenow={shownWidth}
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={viewportMax}
        tabIndex={0}
        onPointerDown={onResizerPointerDown}
        onPointerMove={onResizerPointerMove}
        onPointerUp={onResizerPointerUp}
        onPointerCancel={onResizerPointerUp}
        onKeyDown={onResizerKeyDown}
        onDoubleClick={() => resizeTo(DEFAULT_WIDTH)}
      />
      <div className="spe-sidebar-actions">
        <button type="button" className="spe-new" disabled={!ready} onClick={newChat}><PencilSquare />New chat</button>
        <SearchBox query={filter.query} knownTags={knownTags} onChange={(query) => setFilter({ ...filter, query })} />
      </div>
      <div className="spe-sidebar-list">
        {shown.map((section, i) => (
          <section key={section.label} className="spe-group" data-group={section.label}
            aria-labelledby={`spe-section-${i}`}>
            <h2 className="spe-section" id={`spe-section-${i}`}>{section.label}</h2>
            <ul className="spe-list">{section.sessions.map(row)}</ul>
          </section>
        ))}
        {shown.length === 0 && (
          <p className="spe-empty">{sessions.length === 0 ? "No sessions yet." : "No session matches."}</p>
        )}
      </div>
      <div className="spe-sidebar-foot">
        <HiddenToggle showHidden={filter.showHidden} onChange={(showHidden) => { end(); setFilter({ ...filter, showHidden }); }} />
      </div>

      {busySession && busy?.mode === "menu" && (
        <Popover anchor={triggers.current.get(busy.id)} box={popover} key={`menu-${busy.id}`}>
          <RowMenu
            session={busySession}
            keyboard={busy.keyboard}
            onRename={() => startRename(busySession)}
            onPin={() => choose(busySession, { pinned: !busySession.pinned })}
            onTags={() => setBusy({ id: busySession.id, mode: "tags", draft: "", suggest: false, error: null })}
            onHide={() => choose(busySession, { hidden: !busySession.hidden })}
            onDelete={() => setBusy({ id: busySession.id, mode: "delete" })}
            deleteDisabled={runningIds.has(busySession.id)}
          />
        </Popover>
      )}
      {busySession && busy?.mode === "tags" && (
        <Popover anchor={triggers.current.get(busy.id)} box={popover} key={`tags-${busy.id}`}>
          <TagEditor
            tags={busySession.tags}
            draft={busy.draft}
            suggestions={suggestions}
            error={busy.error}
            onDraft={(draft) => setBusy({ ...busy, draft, suggest: true, error: null })}
            onAdd={(text) => void addTag(busySession, text)}
            onRemove={(tag) => void removeTag(busySession, tag)}
          />
        </Popover>
      )}
      {busySession && busy?.mode === "delete" && (
        <DeleteDialog
          onCancel={() => { setBusy(null); focusTrigger(busySession.id); }}
          onDelete={() => void remove(busySession.id)}
        />
      )}
    </nav>
  );
}
