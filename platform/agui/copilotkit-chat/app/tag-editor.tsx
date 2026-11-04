"use client";
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
import { useEffect, useRef, useState } from "react";
import { menuIndex } from "../lib/menu.ts";
import { XMark } from "./icons";
import { composing } from "./keys.ts";

type TagEditorProps = {
  tags: string[];
  draft: string;
  suggestions: string[];
  error: string | null;
  onDraft: (text: string) => void;
  onAdd: (text: string) => void;
  onRemove: (tag: string) => void;
};

// Open WebUI's tag editor: the tags as pills, each removed by a click on it, and an input whose suggestions
// are the tags in use. Enter adds the suggestion picked with the arrow keys, else the typed text; a
// click on a suggestion adds it; leaving the editor adds nothing.
export function TagEditor({ tags, draft, suggestions, error, onDraft, onAdd, onRemove }: TagEditorProps) {
  const input = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState(-1);
  useEffect(() => input.current?.focus(), []);
  useEffect(() => setPicked(-1), [draft, suggestions.length]);
  return (
    <div className="spe-tag-editor" role="group" aria-label="Tags">
      <p className="spe-tag-heading" aria-hidden="true">Tags</p>
      {tags.length > 0 && (
        <div className="spe-tag-list">
          {/* Open WebUI's pill: the whole pill is the remove button, its × always shown. */}
          {tags.map((t) => (
            <button type="button" key={t} className="spe-chip" aria-label={`Remove tag ${t}`} title={`Remove tag ${t}`}
              onClick={() => onRemove(t)}>
              <span className="spe-chip-text">{t}</span>
              <XMark />
            </button>
          ))}
        </div>
      )}
      <input
        ref={input}
        className="spe-tag-input"
        aria-label="Add a tag"
        placeholder="Add a tag…"
        maxLength={32}
        value={draft}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "spe-tag-error" : undefined}
        aria-activedescendant={picked >= 0 ? `spe-tag-suggestion-${picked}` : undefined}
        onChange={(e) => onDraft(e.target.value)}
        onKeyDown={(e) => {
          if (composing(e)) return;
          if (e.key === "Enter") {
            e.preventDefault();
            onAdd(suggestions[picked] ?? draft);
          } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && suggestions.length > 0) {
            e.preventDefault();
            setPicked((i) => menuIndex(e.key, i, suggestions.length) ?? -1);
          }
        }}
      />
      {suggestions.length > 0 && (
        <ul className="spe-tag-suggestions" role="listbox" aria-label="Tags in use">
          {suggestions.map((t, i) => (
            // mousedown, and its default prevented: the input keeps focus.
            <li key={t} id={`spe-tag-suggestion-${i}`} role="option" aria-selected={i === picked}
              className={i === picked ? "spe-tag-suggestion-picked" : undefined}
              onMouseDown={(e) => { e.preventDefault(); onAdd(t); }}>{t}</li>
          ))}
        </ul>
      )}
      {error && <p className="spe-tag-error" id="spe-tag-error">{error}</p>}
    </div>
  );
}
