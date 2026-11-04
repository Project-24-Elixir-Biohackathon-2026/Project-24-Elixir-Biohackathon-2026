"use client";
// The sidebar footer's theme control: System / Light / Dark, kept in localStorage (key
// spe.theme, try/catch: the page works without it). Light or Dark sets data-theme on <html>
// (globals.css holds both palettes under it); System removes the attribute, so the dark media
// query decides. The choice is also applied before paint by the inline script in
// app/layout.tsx, which re-parses the same key by hand; this component only has to show the
// stored choice and react to further changes, never re-apply what that script already set.
import { useEffect, useState } from "react";
import { parseTheme } from "../lib/theme.ts";
import type { ThemeChoice } from "../lib/theme.ts";

const THEME_KEY = "spe.theme";

const readStoredTheme = (): ThemeChoice => {
  try {
    return parseTheme(localStorage.getItem(THEME_KEY));
  } catch {
    return "system";
  }
};
const writeStoredTheme = (choice: ThemeChoice): void => {
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    // no persistence without storage; the choice still applies for this visit
  }
};

const OPTIONS: Array<{ value: ThemeChoice; label: string }> = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeControl() {
  // "system" on the server and on the first client render (no hydration mismatch: the attribute
  // itself is set by the inline script, not by React); the stored choice, if any, loads right
  // after in an effect, same pattern as the sidebar's stored width.
  const [choice, setChoice] = useState<ThemeChoice>("system");
  useEffect(() => setChoice(readStoredTheme()), []);

  const apply = (next: ThemeChoice) => {
    setChoice(next);
    writeStoredTheme(next);
    if (next === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", next);
  };

  return (
    <div className="spe-theme-control">
      <label htmlFor="spe-theme-select">Theme</label>
      <select
        id="spe-theme-select"
        className="spe-theme-select"
        value={choice}
        onChange={(e) => apply(parseTheme(e.target.value))}
      >
        {OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}
