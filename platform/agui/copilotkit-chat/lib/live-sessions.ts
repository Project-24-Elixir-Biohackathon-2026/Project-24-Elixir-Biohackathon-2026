// The owner of the page's live sessions (decision 40, spec §6 *A session's agent*, *Leaving a running
// chat*): a session the page shows or streams needs a CopilotKit agent of its own, held by a component the
// page keeps mounted while it is needed. `Live` is that need, as a pure value; every transition returns a
// new one, no mutation, no React. `open` is the session shown; `streaming` is every session this page is
// currently running a stream for, open or not; `seen` is every id a list fetch has ever shown (so leaving
// the list can be told from never having been in it, Review Focus 2 / ruling 4: a session not yet listed,
// e.g. a brand new one, is not "gone" just because a list fetch does not have it yet); `gone` is every seen
// id a later list fetch no longer shows, which is sticky once set (nothing in this module clears it).
export type Live = {
  open: string | null; streaming: ReadonlySet<string>; seen: ReadonlySet<string>; gone: ReadonlySet<string>;
};

export const EMPTY: Live = { open: null, streaming: new Set(), seen: new Set(), gone: new Set() };

export function openSession(live: Live, id: string): Live {
  return { ...live, open: id };
}

export function runStarted(live: Live, id: string): Live {
  if (live.streaming.has(id)) return live;
  return { ...live, streaming: new Set(live.streaming).add(id) };
}

// streaming -= id. startNew: the run that just ended belonged to the session that is open, and that
// session left the list while it was running (spec: "then the agent is dropped and, if it was open, the
// page starts a new session").
export function runEnded(live: Live, id: string): { live: Live; startNew: boolean } {
  const startNew = live.open === id && live.gone.has(id);
  if (!live.streaming.has(id)) return { live, startNew };
  const streaming = new Set(live.streaming);
  streaming.delete(id);
  return { live: { ...live, streaming }, startNew };
}

// seen += ids; gone += each seen id missing from ids. startNew: the open session is gone and this page is
// not streaming it, so nothing keeps its holder mounted (the session was deleted, or its journal is
// otherwise no longer listed, while idle).
export function listed(live: Live, ids: ReadonlySet<string>): { live: Live; startNew: boolean } {
  const seen = new Set(live.seen);
  for (const id of ids) seen.add(id);
  const gone = new Set(live.gone);
  for (const id of seen) if (!ids.has(id)) gone.add(id);
  const next: Live = { ...live, seen, gone };
  const startNew = next.open !== null && next.gone.has(next.open) && !next.streaming.has(next.open);
  return { live: next, startNew };
}

// open (if not gone) ∪ streaming, open first, no duplicate.
export function held(live: Live): string[] {
  const out: string[] = [];
  if (live.open !== null && !live.gone.has(live.open)) out.push(live.open);
  for (const id of live.streaming) if (!out.includes(id)) out.push(id);
  return out;
}

export function isHeld(live: Live, id: string): boolean {
  return (live.open === id && !live.gone.has(id)) || live.streaming.has(id);
}

// The list's own ids marked `running` ∪ the page's streaming ids: the one set the sidebar's running mark,
// Delete's refusal, and (slice 3) the refresh poll all read.
export function runningIds(list: readonly { id: string; running: boolean }[], live: Live): Set<string> {
  const out = new Set<string>();
  for (const item of list) if (item.running) out.add(item.id);
  for (const id of live.streaming) out.add(id);
  return out;
}
