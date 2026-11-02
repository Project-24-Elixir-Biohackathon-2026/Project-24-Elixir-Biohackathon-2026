"use client";
import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";

// Modal: focus starts on Cancel and stays inside; Escape or the backdrop cancels.
export function DeleteDialog({ onCancel, onDelete }: { onCancel: () => void; onDelete: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => cancel.current?.focus(), []);
  // Escape on the document, so it cancels even when focus has left the dialog (a click on its text
  // moves focus to the page).
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing || e.defaultPrevented) return;
      e.preventDefault();
      onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Tab") {
      const buttons = [...(dialog.current?.querySelectorAll<HTMLElement>("button") ?? [])];
      const at = buttons.indexOf(document.activeElement as HTMLElement);
      e.preventDefault();
      buttons[(at + (e.shiftKey ? buttons.length - 1 : 1)) % buttons.length]?.focus();
    }
  };
  return (
    <div className="spe-dialog-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div className="spe-dialog" role="alertdialog" aria-modal="true" aria-labelledby="spe-delete-title"
        aria-describedby="spe-delete-text" ref={dialog} onKeyDown={onKeyDown}>
        <h2 id="spe-delete-title">Delete chat?</h2>
        <p id="spe-delete-text">This removes it from your list. It is kept in the run archive.</p>
        <div className="spe-dialog-actions">
          <button type="button" ref={cancel} onClick={onCancel}>Cancel</button>
          <button type="button" className="spe-dialog-confirm" onClick={onDelete}>Delete</button>
        </div>
      </div>
    </div>
  );
}
