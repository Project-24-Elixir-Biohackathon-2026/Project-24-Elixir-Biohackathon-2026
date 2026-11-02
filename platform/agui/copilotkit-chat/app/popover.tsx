"use client";
import { useLayoutEffect, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { popoverPosition } from "../lib/menu.ts";

// Floats over the list (fixed, so it never moves the rows), under its anchor or above it when it
// would leave the viewport; follows the anchor on scroll and resize.
export function Popover({ anchor, box, children }:
  { anchor: HTMLElement | undefined; box: RefObject<HTMLDivElement | null>; children: ReactNode }) {
  const [place, setPlace] = useState<{ top: number; left: number; above: boolean } | null>(null);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el || !anchor) return;
    const update = () => {
      const next = popoverPosition(anchor.getBoundingClientRect(), { width: el.offsetWidth, height: el.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight });
      setPlace((p) => (p && p.top === next.top && p.left === next.left && p.above === next.above ? p : next));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [anchor, box]);
  // Unmeasured: transparent, not hidden, so its first item can take focus before it is placed.
  return (
    <div
      ref={box}
      className={place?.above ? "spe-popover spe-popover-above" : "spe-popover"}
      style={place ? { top: place.top, left: place.left } : { top: 0, left: 0, opacity: 0 }}
    >
      {children}
    </div>
  );
}
