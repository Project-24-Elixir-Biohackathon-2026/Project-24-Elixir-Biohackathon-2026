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
