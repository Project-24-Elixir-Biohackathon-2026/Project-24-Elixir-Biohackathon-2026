// The sidebar's resizable width: pure helpers so the drag, keyboard step and persisted value (kept
// per browser, read and written in try/catch by the caller) all agree on the same bounds and default.
export const MIN = 200;
export const MAX = 480;
export const DEFAULT = 260;
export const STEP = 16;
// Left for the chat pane next to the sidebar on a narrow viewport (there is no narrow-screen
// collapse or overlay in this codebase to rely on instead). Matches the margin in the CSS
// `min(var(--sidebar-width), calc(100vw - 48px))` on `.spe-sidebar`, which caps the rendered width
// regardless of what any stored or dragged-to value says; keep the two in sync if either changes.
export const VIEWPORT_MARGIN = 48;

/** Clamped to [MIN, MAX]. */
export function clampWidth(n: number): number {
  return Math.min(MAX, Math.max(MIN, n));
}

/** The widest the sidebar may be on a viewport of this width, so a drag, a keyboard step, or the
 *  separator's reported range never claims more than the viewport actually renders (never above
 *  MAX; never negative on a vanishingly small viewport). A value already in `localStorage` is not
 *  put through this: a desktop width should survive a visit from a phone unchanged. */
export function maxFor(viewportWidth: number): number {
  return Math.min(MAX, Math.max(0, viewportWidth - VIEWPORT_MARGIN));
}

/** The width `localStorage` held, or DEFAULT if it is missing or not a finite number. */
export function parseWidth(stored: string | null): number {
  if (stored === null || stored.trim() === "") return DEFAULT;
  const n = Number(stored);
  return Number.isFinite(n) ? clampWidth(n) : DEFAULT;
}

/** One keyboard step (STEP px) from `current`, clamped. `direction` is -1 (Left, narrower) or 1
 *  (Right, wider). */
export function stepWidth(current: number, direction: -1 | 1): number {
  return clampWidth(current + direction * STEP);
}
