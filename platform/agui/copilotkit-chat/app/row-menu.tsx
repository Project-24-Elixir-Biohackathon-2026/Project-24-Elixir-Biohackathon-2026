"use client";
// A session's `⋯` menu and its in-place rename, shared by the sidebar rows and the chat header.
// Titles are model or participant text: rendered as React text only, never as HTML.
import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import { menuIndex } from "../lib/menu.ts";
import type { SessionMeta } from "../lib/sessions.ts";
import { Eye, EyeSlash, Pencil, Pin, PinSlash, Tag, Trash } from "./icons";
import { composing } from "./keys.ts";

export type RowMenuProps = {
  session: SessionMeta;
  keyboard: boolean;
  onRename: () => void;
  onPin: () => void;
  onTags: () => void;
  onHide: () => void;
  onDelete: () => void;
  /** Delete greyed out: the session is running (its Delete would start a new chat under the run). */
  deleteDisabled?: boolean;
};

// The `⋯` menu of a session, the same for its sidebar row and the chat header.
export function RowMenu({ session, keyboard, onRename, onPin, onTags, onHide, onDelete, deleteDisabled }: RowMenuProps) {
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
      <button type="button" role="menuitem" className="spe-menu-danger" disabled={deleteDisabled}
        onClick={onDelete}><Trash />Delete</button>
    </div>
  );
}

// Replaces a title in place (a row's, or the chat header's), focused with the text selected.
export function RenameInput({ value, onChange, onSave, onCancel, label = "Session title", className = "spe-rename" }:
  { value: string; onChange: (v: string) => void; onSave: () => void; onCancel: () => void; label?: string;
    className?: string }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <input
      ref={input}
      className={className}
      aria-label={label}
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
