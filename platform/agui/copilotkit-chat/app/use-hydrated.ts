// True only once the client has rendered at least once after hydration. A server-rendered button
// exists in the DOM, with its disabled state computed from the server's own (pre-hydration) value
// of this flag, before React attaches its event handlers; a click landing in that window would
// otherwise be silently dropped. `useEffect` runs only on the client, after the DOM it describes
// has committed, so it is the first point at which React is known to be interactive.
import { useEffect, useState } from "react";

export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return hydrated;
}
