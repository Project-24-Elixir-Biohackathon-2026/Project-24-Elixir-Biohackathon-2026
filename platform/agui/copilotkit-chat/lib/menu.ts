// Geometry and keys of the sidebar's row popover. Browser-safe, no DOM access: the sidebar measures.

export type Rect = { top: number; bottom: number; left: number; right: number };
export type Size = { width: number; height: number };

const GAP = 4; // between the anchor and the popover
const MARGIN = 8; // kept free at the viewport's edges

// Under the anchor with left edges aligned; above it when it would leave the viewport at the bottom
// and fits there; otherwise under it, moved up as far as needed. Always inside the viewport sideways.
export function popoverPosition(anchor: Rect, size: Size, viewport: Size): { top: number; left: number; above: boolean } {
  const below = anchor.bottom + GAP;
  const aboveTop = anchor.top - GAP - size.height;
  let top = below;
  let above = false;
  if (below + size.height > viewport.height - MARGIN) {
    if (aboveTop >= MARGIN) {
      top = aboveTop;
      above = true;
    } else {
      top = Math.max(MARGIN, viewport.height - MARGIN - size.height);
    }
  }
  const left = Math.max(MARGIN, Math.min(anchor.left, viewport.width - MARGIN - size.width));
  return { top, left, above };
}

// The item a key moves focus to in a menu of `count` items (`current` -1: none focused yet),
// or null when the key is not one of the menu's.
export function menuIndex(key: string, current: number, count: number): number | null {
  if (count === 0) return null;
  switch (key) {
    case "ArrowDown":
      return current < 0 ? 0 : (current + 1) % count;
    case "ArrowUp":
      return current <= 0 ? count - 1 : current - 1;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

// The page as far as focus goes: what has it, and the two elements that mean "nothing has".
export type FocusPage = { activeElement: object | null; body: object | null; documentElement: object };

// True when a press left focus nowhere: on the page itself (a click on text or empty space), not on
// anything that takes focus.
export function focusLost(active: object | null, page: Pick<FocusPage, "body" | "documentElement">): boolean {
  return active === null || active === page.body || active === page.documentElement;
}

// After a press outside an open menu has closed it: gives focus back to the menu's `⋯`, as Escape and a
// choice do, but only if the press left focus nowhere, so a press on a field, a button or a link keeps the
// focus it gave. The check waits a task, for the press's own focus change (the `mousedown` after the
// `pointerdown` that closed the menu) to have happened. Callers skip it for touch: a tap's compatibility
// `mousedown` comes after `touchend`, later than the check, and touch has no keyboard focus to keep.
export function refocusIfLost(
  page: FocusPage,
  trigger: () => { focus: (options?: { preventScroll?: boolean }) => void } | undefined | null,
  schedule: (f: () => void) => unknown = (f) => setTimeout(f, 0),
): void {
  schedule(() => {
    if (focusLost(page.activeElement, page)) trigger()?.focus({ preventScroll: true });
  });
}
