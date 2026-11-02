"use client";
// The sidebar's filters: the title search with Open WebUI's `tag:<name>` terms and its suggestions,
// above the list; the *Show hidden* toggle and the note on deleted sessions below it. All text is
// React text.
import { useEffect, useState } from "react";
import { menuIndex } from "../lib/menu.ts";
import { tagTermSuggestions, withTagTerm } from "../lib/sidebar-view.ts";
import { composing } from "./keys.ts";

export const DELETED_NOTE = "Deleted sessions are kept in the run archive.";

type SearchProps = { query: string; knownTags: string[]; onChange: (query: string) => void };

// Typing `tag:` lists the tags in use under the box (as the tag editor's suggestions: arrows pick,
// Enter or a click takes one, Escape hides them); taking one completes the word to `tag:<name> `.
export function SearchBox({ query, knownTags, onChange }: SearchProps) {
  const [picked, setPicked] = useState(-1);
  const [dismissed, setDismissed] = useState(false);
  const [focused, setFocused] = useState(false);
  const suggestions = focused && !dismissed ? tagTermSuggestions(knownTags, query) : [];
  useEffect(() => setPicked(-1), [query, suggestions.length]);
  const take = (tag: string) => {
    onChange(withTagTerm(query, tag));
    setDismissed(false);
  };
  return (
    <div className="spe-search-box">
      <input
        type="search"
        className="spe-search"
        aria-label="Search titles"
        placeholder="Search"
        value={query}
        aria-autocomplete="list"
        aria-expanded={suggestions.length > 0}
        aria-controls={suggestions.length > 0 ? "spe-search-suggestions" : undefined}
        aria-activedescendant={picked >= 0 ? `spe-search-suggestion-${picked}` : undefined}
        onFocus={() => setFocused(true)}
        // Escape's dismissal is for this focus only: refocusing the box (a click, or Tab back to
        // it) should show the suggestions again rather than stay dismissed from an earlier visit.
        onBlur={() => { setFocused(false); setDismissed(false); }}
        onChange={(e) => {
          setDismissed(false);
          onChange(e.target.value);
        }}
        onKeyDown={(e) => {
          if (composing(e) || suggestions.length === 0) return;
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setPicked((i) => menuIndex(e.key, i, suggestions.length) ?? -1);
          } else if (e.key === "Enter" && picked >= 0) {
            e.preventDefault();
            take(suggestions[picked]);
          } else if (e.key === "Escape") {
            e.preventDefault(); // the search box's own Escape would clear the query
            setDismissed(true);
          }
        }}
      />
      {suggestions.length > 0 && (
        <ul className="spe-search-suggestions" id="spe-search-suggestions" role="listbox" aria-label="Tags in use">
          {suggestions.map((t, i) => (
            // mousedown, and its default prevented: the input keeps focus.
            <li key={t} id={`spe-search-suggestion-${i}`} role="option" aria-selected={i === picked}
              className={i === picked ? "spe-search-suggestion-picked" : undefined}
              onMouseDown={(e) => { e.preventDefault(); take(t); }}>
              <span className="spe-search-suggestion-prefix">tag:</span>{t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type HiddenProps = { showHidden: boolean; onChange: (showHidden: boolean) => void };

export function HiddenToggle({ showHidden, onChange }: HiddenProps) {
  return (
    <div className="spe-sidebar-foot">
      <label className="spe-hidden-toggle">
        <input type="checkbox" checked={showHidden} onChange={(e) => onChange(e.target.checked)} /> Show hidden
      </label>
      <p className="spe-note">{DELETED_NOTE}</p>
    </div>
  );
}
