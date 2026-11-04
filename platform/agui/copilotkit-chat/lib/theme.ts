// The sidebar's theme choice (kept in `localStorage`, key `spe.theme`) and what it resolves to.
// The inline script in app/layout.tsx applies the choice before paint; it can't import this
// module (it runs as a plain <script>, before any bundle), so it re-parses the same three values
// by hand — keep the two in step if the values ever change.
export type ThemeChoice = "system" | "light" | "dark";

/** The choice `localStorage` held, or "system" if it is missing or not one of the three values. */
export function parseTheme(stored: string | null): ThemeChoice {
  return stored === "light" || stored === "dark" ? stored : "system";
}

/** What actually renders: the explicit choice, or the system's preference when it is "system". */
export function effectiveTheme(choice: ThemeChoice, systemDark: boolean): "light" | "dark" {
  return choice === "system" ? (systemDark ? "dark" : "light") : choice;
}
