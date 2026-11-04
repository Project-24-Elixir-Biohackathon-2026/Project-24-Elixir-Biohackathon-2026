"use client";
// The theme toggle at the chat pane's top right: a pill switch, sun on the left and moon on the right,
// whose knob slides to the theme that renders. Until it is first used the page follows the system
// (`prefers-color-scheme`); a click flips the rendered theme and keeps the choice in localStorage (key
// spe.theme, try/catch: the page works without it). Flipping to the theme the system already prefers
// stores "system" again, so the page goes back to following the system rather than pinning a theme
// that happens to match. Light or Dark sets data-theme on <html> (globals.css holds both palettes
// under it); System removes the attribute, so the dark media query decides. The choice is also applied
// before paint by the inline script in app/layout.tsx, which re-parses the same key by hand; this
// component only has to show the stored choice and react to further changes, never re-apply what
// that script already set.
import { useEffect, useState } from "react";
import { effectiveTheme, parseTheme } from "../lib/theme.ts";
import type { ThemeChoice } from "../lib/theme.ts";
import { Moon, Sun } from "./icons";

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

export function ThemeControl() {
  // "system" and light on the server and on the first client render (no hydration mismatch: the
  // attribute itself is set by the inline script, not by React); the stored choice and the system's
  // preference load right after in an effect. `ready` holds back the knob's slide until then, so a dark
  // page does not animate the knob across on load.
  const [choice, setChoice] = useState<ThemeChoice>("system");
  const [systemDark, setSystemDark] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => setSystemDark(query.matches);
    setChoice(readStoredTheme());
    sync();
    query.addEventListener("change", sync);
    requestAnimationFrame(() => setReady(true));
    return () => query.removeEventListener("change", sync);
  }, []);

  const dark = effectiveTheme(choice, systemDark) === "dark";
  const flip = () => {
    const wantDark = !dark;
    const next: ThemeChoice = wantDark === systemDark ? "system" : wantDark ? "dark" : "light";
    setChoice(next);
    writeStoredTheme(next);
    if (next === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", next);
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="spe-theme-toggle"
      data-dark={dark || undefined}
      data-ready={ready || undefined}
      onClick={flip}
    >
      <Sun className="spe-theme-sun" />
      <Moon className="spe-theme-moon" />
      <span className="spe-theme-knob" aria-hidden="true">{dark ? <Moon /> : <Sun />}</span>
    </button>
  );
}
