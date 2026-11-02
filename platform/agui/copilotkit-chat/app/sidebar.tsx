"use client";
// The sessions sidebar: New chat, the list (pinned first, then newest) and each row's menu.
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
//
// One owner for what a row is doing: `Sidebar` holds which row has its menu, rename, tag editor or
// delete dialog open, so at most one row is ever busy, and opening a session, New chat, collapsing
// or another row's menu ends it. The close and focus rules follow Open WebUI's sidebar: the menu
// closes on a press outside it, Escape or a choice, and gives focus back to its ⋯; a rename is saved
// by Enter or a press outside the row and cancelled by Escape; a tag typed but not added is dropped.
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { removeSession, renamePatch, tagSuggestions, updateSession, withTag, withoutTag } from "../lib/client.ts";
import { menuIndex } from "../lib/menu.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
import { DeleteDialog } from "./delete-dialog";
import { Ellipsis, Eye, EyeSlash, PencilSquare, Pencil, Pin, PinSlash, SidebarToggle, Tag, Trash } from "./icons";
import { composing } from "./keys.ts";
import { Popover } from "./popover";
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
};

// What the one busy row is doing. `keyboard`: the menu was opened from the keyboard, so its first
// item takes focus. `suggest`: the tag suggestions are shown for what is typed.
type Busy =
  | { id: string; mode: "menu"; keyboard: boolean }
  | { id: string; mode: "rename"; draft: string }
  | { id: string; mode: "tags"; draft: string; suggest: boolean; error: string | null }
  | { id: string; mode: "delete" };

const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);


export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError }: SidebarProps) {
  const [busy, setBusy] = useState<Busy | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const triggers = useRef(new Map<string, HTMLButtonElement>());
  const popover = useRef<HTMLDivElement>(null);
  // The session id whose tag change is in flight, until the list is fetched again: each patch is
  // the whole tag list, so a second add or remove before then (ignored) would start from the
  // list without the first change and undo it.
  const savingTag = useRef<string | null>(null);
  const busySession = busy ? sessions.find((s) => s.id === busy.id) : undefined;
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
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  });

  // Escape, wherever focus is: the tag suggestions first, then the menu or editor. The rename input
  // and the dialog handle their own.
  useEffect(() => {
    if (!busy || busy.mode === "rename" || busy.mode === "delete") return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing) return;
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
  if (collapsed) {
    return (
      <nav className="spe-sidebar spe-sidebar-collapsed" aria-label="Sessions">
        <button type="button" className="spe-icon-button" aria-label="Show sessions" title="Show sessions"
          onClick={() => setCollapsed(false)}><SidebarToggle /></button>
        <button type="button" className="spe-icon-button" aria-label="New chat" title="New chat"
          onClick={newChat}><PencilSquare /></button>
      </nav>
    );
  }

  const row = (s: SessionMeta) => {
    const mine = busy?.id === s.id ? busy : null;
    const popoverOpen = mine?.mode === "menu" || mine?.mode === "tags";
    const classes = ["spe-row"];
    if (s.id === activeId) classes.push("spe-row-active");
    if (popoverOpen) classes.push("spe-row-menu-open");
    if (mine?.mode === "rename") classes.push("spe-row-renaming");
    return (
      <li key={s.id} className={classes.join(" ")}>
        {mine?.mode === "rename" ? (
          <RenameInput
            value={mine.draft}
            onChange={(draft) => setBusy({ ...mine, draft })}
            onSave={() => { end(true); }}
            onCancel={() => { setBusy(null); focusTrigger(s.id); }}
          />
        ) : (
          <button type="button" className="spe-row-open" aria-current={s.id === activeId ? "page" : undefined}
            onClick={() => { end(); onOpen(s.id); }} onDoubleClick={() => startRename(s)}>
            {/* The Pinned section shows it; this tells a screen reader too. */}
            {s.pinned && <span className="spe-pin spe-sr-only">Pinned: </span>}
            <span className="spe-row-title">{s.title}</span>
          </button>
        )}
        <button
          type="button"
          className="spe-row-menu"
          ref={(el) => { if (el) triggers.current.set(s.id, el); else triggers.current.delete(s.id); }}
          aria-label={`Menu for ${s.title}`}
          aria-haspopup="menu"
          aria-expanded={popoverOpen}
          aria-disabled={mine?.mode === "rename" || undefined}
          tabIndex={mine?.mode === "rename" ? -1 : undefined}
          onClick={(e) => toggleMenu(s.id, e)}
        ><Ellipsis /></button>
      </li>
    );
  };
  // `sessions` comes ordered, pinned first.
  const pinned = sessions.filter((s) => s.pinned);
  const others = sessions.filter((s) => !s.pinned);

  return (
    <nav className="spe-sidebar" aria-label="Sessions">
      <div className="spe-sidebar-top">
        <span className="spe-brand">SPE agent</span>
        <button type="button" className="spe-icon-button spe-collapse" aria-label="Hide sessions" title="Hide sessions"
          onClick={() => { end(); setCollapsed(true); }}><SidebarToggle /></button>
      </div>
      <div className="spe-sidebar-actions">
        <button type="button" className="spe-new" onClick={newChat}><PencilSquare />New chat</button>
        {/* Title search goes here. */}
      </div>
      <div className="spe-sidebar-list">
        {pinned.length > 0 && (
          <>
            <h2 className="spe-section" id="spe-section-pinned">Pinned</h2>
            <ul className="spe-list" aria-labelledby="spe-section-pinned">{pinned.map(row)}</ul>
          </>
        )}
        {pinned.length > 0 && others.length > 0 && <h2 className="spe-section" id="spe-section-chats">Chats</h2>}
        {others.length > 0 && (
          <ul className="spe-list" aria-labelledby={pinned.length > 0 ? "spe-section-chats" : undefined}>
            {others.map(row)}
          </ul>
        )}
        {sessions.length === 0 && <p className="spe-empty">No sessions yet.</p>}
      </div>
      <p className="spe-note">Deleted sessions are kept in the run archive.</p>

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

type RowMenuProps = {
  session: SessionMeta;
  keyboard: boolean;
  onRename: () => void;
  onPin: () => void;
  onTags: () => void;
  onHide: () => void;
  onDelete: () => void;
};

function RowMenu({ session, keyboard, onRename, onPin, onTags, onHide, onDelete }: RowMenuProps) {
  const menu = useRef<HTMLDivElement>(null);
  const items = () => [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
  // From the keyboard the first item takes focus; from a click the menu itself, so arrows work.
  useEffect(() => {
    if (keyboard) items()[0]?.focus();
    else menu.current?.focus();
  }, [keyboard]);
  const onKeyDown = (e: KeyboardEvent) => {
    const list = items();
    const next = menuIndex(e.key, list.indexOf(document.activeElement as HTMLElement), list.length);
    if (next === null) return;
    e.preventDefault();
    list[next].focus();
  };
  return (
    <div className="spe-menu" role="menu" aria-label={`Menu for ${session.title}`} tabIndex={-1} ref={menu} onKeyDown={onKeyDown}>
      <button type="button" role="menuitem" onClick={onRename}><Pencil />Rename</button>
      <button type="button" role="menuitem" onClick={onPin}>
        {session.pinned ? <><PinSlash />Unpin</> : <><Pin />Pin</>}
      </button>
      <button type="button" role="menuitem" onClick={onTags}><Tag />Tags</button>
      <button type="button" role="menuitem" onClick={onHide}>
        {session.hidden ? <><Eye />Unhide</> : <><EyeSlash />Hide</>}
      </button>
      <div role="separator" className="spe-menu-separator" />
      <button type="button" role="menuitem" className="spe-menu-danger" onClick={onDelete}><Trash />Delete</button>
    </div>
  );
}

// Replaces the row's title in place, focused with the text selected.
function RenameInput({ value, onChange, onSave, onCancel }:
  { value: string; onChange: (v: string) => void; onSave: () => void; onCancel: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <input
      ref={input}
      className="spe-rename"
      aria-label="Session title"
      maxLength={200}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (composing(e)) return;
        if (e.key === "Enter") { e.preventDefault(); onSave(); }
        if (e.key === "Escape") { e.preventDefault(); onCancel(); }
      }}
    />
  );
}
