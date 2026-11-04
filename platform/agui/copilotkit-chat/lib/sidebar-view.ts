// What the sidebar shows, as pure functions of the session list: the title search with Open WebUI's
// `tag:<name>` terms, the suggestions for a `tag:` being typed, *Show hidden*, and the order: pinned
// first, then Today / Yesterday / Previous 7 days / Older by `updated_at`, in the browser's time zone.
import type { SessionMeta } from "./sessions.ts";

export type DateGroup = "Today" | "Yesterday" | "Previous 7 days" | "Older";
export type SectionLabel = "Pinned" | DateGroup;
export type Section = { label: SectionLabel; sessions: SessionMeta[] };
export type ViewFilter = { query: string; showHidden: boolean };
export type ParsedQuery = { text: string; tags: string[] };

const GROUPS: readonly DateGroup[] = ["Today", "Yesterday", "Previous 7 days", "Older"];
const TAG_PREFIX = "tag:";

function time(iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? -Infinity : t;
}

/** The query's terms, split on whitespace: each `tag:<name>` is a tag (lower-cased, as the server
 *  stores tags; a bare `tag:` still being typed is ignored), the other words, joined by one space and
 *  lower-cased, are the title text. */
export function parseQuery(query: string): ParsedQuery {
  const words: string[] = [];
  const tags: string[] = [];
  for (const term of query.split(/\s+/)) {
    if (term === "") continue;
    if (term.toLowerCase().startsWith(TAG_PREFIX)) {
      const tag = term.slice(TAG_PREFIX.length).toLowerCase();
      if (tag !== "" && !tags.includes(tag)) tags.push(tag);
    } else {
      words.push(term);
    }
  }
  return { text: words.join(" ").toLowerCase(), tags };
}

/** Sessions the current filter shows: hidden ones only with showHidden; every `tag:` term is on the
 *  session; the title contains the rest of the query (case-insensitive, literally: no pattern). */
export function filterSessions(list: readonly SessionMeta[], filter: ViewFilter): SessionMeta[] {
  const { text, tags } = parseQuery(filter.query);
  return list.filter(
    (s) =>
      (filter.showHidden || !s.hidden) &&
      tags.every((tag) => s.tags.includes(tag)) &&
      (text === "" || s.title.toLowerCase().includes(text)),
  );
}

/** Open WebUI's `tag:` suggestions: when the query's last word (no whitespace after it) starts with
 *  `tag:`, the tags in use (`known`) that start with what follows it, leaving out those the query
 *  already names; at most `max`. Otherwise none. */
export function tagTermSuggestions(known: readonly string[], query: string, max = 8): string[] {
  const last = query.split(/\s/).at(-1) ?? "";
  if (!last.toLowerCase().startsWith(TAG_PREFIX)) return [];
  const typed = last.slice(TAG_PREFIX.length).toLowerCase();
  const named = parseQuery(query.slice(0, query.length - last.length)).tags;
  return known.filter((t) => t.startsWith(typed) && !named.includes(t)).slice(0, max);
}

/** Picking a suggestion: the last word becomes `tag:<tag>` and a space, the rest of the query stays. */
export function withTagTerm(query: string, tag: string): string {
  const last = query.split(/\s/).at(-1) ?? "";
  return `${query.slice(0, query.length - last.length)}${TAG_PREFIX}${tag} `;
}

/** The date group of a timestamp, by local calendar day. A time after `now` (clock skew) is
 *  Today; an unparseable one is Older. */
export function dateGroup(updatedAt: string, now: Date): DateGroup {
  const t = time(updatedAt);
  const day = (back: number) => new Date(now.getFullYear(), now.getMonth(), now.getDate() - back).getTime();
  if (t >= day(0)) return "Today";
  if (t >= day(1)) return "Yesterday";
  if (t >= day(7)) return "Previous 7 days";
  return "Older";
}

/** Pinned first, then the date groups in order; newest `updated_at` first inside each; empty
 *  sections left out. */
export function sections(list: readonly SessionMeta[], now: Date): Section[] {
  const newest = [...list].sort((a, b) => time(b.updated_at) - time(a.updated_at));
  const out: Section[] = [];
  const pinned = newest.filter((s) => s.pinned);
  if (pinned.length > 0) out.push({ label: "Pinned", sessions: pinned });
  for (const label of GROUPS) {
    const sessions = newest.filter((s) => !s.pinned && dateGroup(s.updated_at, now) === label);
    if (sessions.length > 0) out.push({ label, sessions });
  }
  return out;
}
