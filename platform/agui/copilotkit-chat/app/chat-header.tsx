"use client";
// The chat header (Open WebUI's navbar): the open session's title, renamable in place (by its menu's
// Rename or a double-click, as a row), and the same `⋯` menu as its sidebar row: RowMenu, the
// TagEditor, the DeleteDialog, with the sidebar's close and focus rules. A session not yet recorded
// (New chat, before its first run ends) shows "New chat" and no menu: PATCH would answer 404. Which
// session is open is still unknown on first load (before the URL's `?session=` is resolved, while
// the page's own "Loading…" shows): `session` is `undefined` then, so the header shows no title at
// all rather than "New chat" while the rest of the page says it is still loading.
// Its rename input is labelled "Chat title", not the rows' "Session title", so a label lookup finds one.
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { renamePatch, tagSuggestions, withTag, withoutTag } from "../lib/client.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
import { DeleteDialog } from "./delete-dialog";
import { Ellipsis } from "./icons";
import { Popover } from "./popover";
import { RenameInput, RowMenu } from "./row-menu";
import { TagEditor } from "./tag-editor";

type Props = {
  /** `undefined`: which session is open is not yet known (first load, still "Loading…"), so
   * nothing is shown. `null`: a confirmed New chat, not yet recorded. */
  session: SessionMeta | null | undefined;
  knownTags: string[];
  /** A run is in progress: Delete is disabled, as in the open session's row. */
  running: boolean;
  /** False until the page is safe to click: hydrated, the agent ready, and the page's own
   *  first-load `startNew()`/`open()` has actually run. The actions button starts a menu of
   *  actions, so it stays disabled until then, as the sidebar's buttons do. */
  ready: boolean;
  /** Saves the change and refreshes the list; rejects with the failure. */
  onPatch: (patch: MetaPatch) => Promise<void>;
  onDelete: () => void;
  onError: (message: string) => void;
};

type Mode =
  | { mode: "menu"; keyboard: boolean }
  | { mode: "rename"; draft: string }
  | { mode: "tags"; draft: string; suggest: boolean; error: string | null }
  | { mode: "delete" };

const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

export function ChatHeader({ session, knownTags, running, ready, onPatch, onDelete, onError }: Props) {
  const [open, setOpen] = useState<Mode | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const header = useRef<HTMLElement>(null);
  const suggestions = open?.mode === "tags" && open.suggest && session
    ? tagSuggestions(knownTags, session.tags, open.draft)
    : [];

  const save = async (patch: MetaPatch | null) => {
    if (!patch) return;
    try {
      await onPatch(patch);
    } catch (e) {
      onError(errorText(e, "Saving the change failed."));
    }
  };
  // As the sidebar's `end`: a rename in progress is saved if it changed the title; a tag typed but
  // not added is dropped.
  const end = (returnFocus = false) => {
    if (!open) return;
    setOpen(null);
    if (open.mode === "rename" && session) void save(renamePatch(open.draft, session.title));
    if (returnFocus) trigger.current?.focus();
  };

  // A press outside ends it: outside the menu and its ⋯, or outside the title for a rename.
  useEffect(() => {
    if (!open || open.mode === "delete") return;
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (open.mode === "rename") {
        if (!header.current?.querySelector(".spe-header-rename")?.contains(target)) end();
        return;
      }
      if (popover.current?.contains(target) || trigger.current?.contains(target)) return;
      end();
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  });

  // Escape: the tag suggestions first, then the menu or editor.
  useEffect(() => {
    if (!open || open.mode === "rename" || open.mode === "delete") return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing || e.defaultPrevented) return;
      e.preventDefault();
      if (open.mode === "tags" && suggestions.length > 0) setOpen({ ...open, suggest: false });
      else end(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  if (session === undefined) {
    return <header className="spe-header" />; // which session is open is not yet known
  }
  if (session === null) {
    return (
      <header className="spe-header">
        <h1 className="spe-header-title">New chat</h1>
      </header>
    );
  }

  const toggleMenu = (e: MouseEvent) => {
    if (open?.mode === "rename") return; // `⋯` is aria-disabled while renaming
    if (open?.mode === "menu" || open?.mode === "tags") end();
    else setOpen({ mode: "menu", keyboard: e.detail === 0 });
  };
  const startRename = () => setOpen({ mode: "rename", draft: session.title });
  const choose = (patch: MetaPatch) => {
    end(true);
    void save(patch);
  };
  const setTags = (change: (m: Extract<Mode, { mode: "tags" }>) => Mode) =>
    setOpen((m) => (m && m.mode === "tags" ? change(m) : m));
  // As the sidebar's tag editor: it stays open for the next tag; an add that fails keeps its text
  // and shows why; a removal (`typed` null) leaves the input as it is.
  const tagPatch = async (patch: MetaPatch | null, typed: string | null) => {
    const done = (m: Extract<Mode, { mode: "tags" }>): Mode =>
      typed === null ? { ...m, error: null } : { ...m, draft: "", suggest: false, error: null };
    if (!patch) {
      setTags(done); // already there
      return;
    }
    try {
      await onPatch(patch);
      setTags(done);
    } catch (e) {
      setTags((m) => ({ ...m, draft: typed ?? m.draft, suggest: false, error: errorText(e, "Saving the tag failed.") }));
    }
  };

  const menuOpen = open?.mode === "menu" || open?.mode === "tags";
  return (
    <header className="spe-header" ref={header}>
      {open?.mode === "rename" ? (
        <RenameInput
          label="Chat title"
          className="spe-header-rename"
          value={open.draft}
          onChange={(draft) => setOpen({ ...open, draft })}
          onSave={() => end(true)}
          onLeave={() => end()}
          onCancel={() => { setOpen(null); trigger.current?.focus(); }}
        />
      ) : (
        <h1 className="spe-header-title" title={session.title} onDoubleClick={startRename}>{session.title}</h1>
      )}
      <button
        type="button"
        className="spe-icon-button spe-header-menu"
        ref={trigger}
        aria-label="Chat actions"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        disabled={!ready}
        // `disabled` only for `!ready`; renaming uses `aria-disabled` instead, because a disabled
        // button cannot take the focus that ending a rename returns to it (React applies
        // `setOpen(null)` after the handler's `focus()`), the same pattern the sidebar's rows use.
        aria-disabled={open?.mode === "rename" || undefined}
        tabIndex={open?.mode === "rename" ? -1 : undefined}
        onClick={toggleMenu}
      ><Ellipsis /></button>

      {open?.mode === "menu" && (
        <Popover anchor={trigger.current ?? undefined} box={popover} key="menu">
          <RowMenu
            session={session}
            keyboard={open.keyboard}
            onRename={startRename}
            onPin={() => choose({ pinned: !session.pinned })}
            onTags={() => setOpen({ mode: "tags", draft: "", suggest: false, error: null })}
            onHide={() => choose({ hidden: !session.hidden })}
            onDelete={() => setOpen({ mode: "delete" })}
            deleteDisabled={running}
          />
        </Popover>
      )}
      {open?.mode === "tags" && (
        <Popover anchor={trigger.current ?? undefined} box={popover} key="tags">
          <TagEditor
            tags={session.tags}
            draft={open.draft}
            suggestions={suggestions}
            error={open.error}
            onDraft={(draft) => setOpen({ ...open, draft, suggest: true, error: null })}
            onAdd={(text) => { if (text.trim()) void tagPatch(withTag(session.tags, text), text); }}
            onRemove={(tag) => {
              popover.current?.querySelector<HTMLInputElement>(".spe-tag-input")?.focus();
              void tagPatch(withoutTag(session.tags, tag), null);
            }}
          />
        </Popover>
      )}
      {open?.mode === "delete" && (
        <DeleteDialog
          onCancel={() => { setOpen(null); trigger.current?.focus(); }}
          onDelete={() => { setOpen(null); onDelete(); }}
        />
      )}
    </header>
  );
}
