import assert from "node:assert/strict";
import { test } from "node:test";
import type { SessionMeta } from "./sessions.ts";
import { dateGroup, filterSessions, parseQuery, sections, tagTermSuggestions, withTagTerm } from "./sidebar-view.ts";

// Local wall-clock times, so the tests hold in any time zone (run them with TZ set to check).
const at = (y: number, mo: number, d: number, h = 12, mi = 0) => new Date(y, mo - 1, d, h, mi).toISOString();
const NOW = new Date(2026, 9, 29, 10, 0); // 29 October 2026, 10:00 local

function meta(id: string, over: Partial<SessionMeta> = {}): SessionMeta {
  return { id, title: id, tags: [], pinned: false, hidden: false, created_at: at(2026, 10, 1),
           updated_at: at(2026, 10, 29, 9), last_run_at: null, ...over };
}

const LIST: SessionMeta[] = [
  meta("a", { title: "List the HOME directory", tags: ["exfil", "dns"] }),
  meta("b", { title: "dns lookups", tags: ["dns"] }),
  meta("c", { title: "hidden one", tags: ["exfil"], hidden: true }),
  meta("d", { title: "Plain", tags: [] }),
];
const ids = (query: string, showHidden = false) => filterSessions(LIST, { query, showHidden }).map((s) => s.id);

test("search is a case-insensitive substring of the title, spaces around it ignored", () => {
  assert.deepEqual(ids("  home "), ["a"]);
  assert.deepEqual(ids("DNS"), ["b"]);
  assert.deepEqual(ids("the   home"), ["a"]);
  assert.deepEqual(ids(""), ["a", "b", "d"]);
});

test("search treats regex and HTML characters literally", () => {
  const list = [meta("x", { title: "<img src=x onerror=alert(1)>" }), meta("y", { title: "a.b" })];
  assert.deepEqual(filterSessions(list, { query: "<img", showHidden: false }).map((s) => s.id), ["x"]);
  assert.deepEqual(filterSessions(list, { query: ".", showHidden: false }).map((s) => s.id), ["y"]);
});

test("parseQuery: tag: terms are tags (lower-cased, a bare tag: ignored), the rest is the title text", () => {
  assert.deepEqual(parseQuery("  tag:DNS list  Tag:exfil the tag: "), { text: "list the", tags: ["dns", "exfil"] });
  assert.deepEqual(parseQuery("tag:dns tag:dns"), { text: "", tags: ["dns"] });
  assert.deepEqual(parseQuery(""), { text: "", tags: [] });
});

test("several tag: terms: a session must have all of them; the rest filters titles", () => {
  assert.deepEqual(ids("tag:dns"), ["a", "b"]);
  assert.deepEqual(ids("tag:dns tag:exfil"), ["a"]);
  assert.deepEqual(ids("tag:exfil", true), ["a", "c"]);
  assert.deepEqual(ids("tag:dns lookups"), ["b"]);
  assert.deepEqual(ids("tag:nosuch"), []);
  assert.deepEqual(ids("tag:"), ["a", "b", "d"]);
});

test("hidden sessions only with Show hidden", () => {
  assert.equal(filterSessions(LIST, { query: "", showHidden: false }).some((s) => s.hidden), false);
  assert.deepEqual(ids("hidden", true), ["c"]);
});

test("tag: suggestions: the last word's prefix, tags already named left out, none without tag:", () => {
  const known = ["alpha", "beta", "dns", "exfil"];
  assert.deepEqual(tagTermSuggestions(known, "tag:"), known);
  assert.deepEqual(tagTermSuggestions(known, "home TAG:b"), ["beta"]);
  assert.deepEqual(tagTermSuggestions(known, "tag:beta tag:"), ["alpha", "dns", "exfil"]);
  assert.deepEqual(tagTermSuggestions(known, "tag:beta "), []);
  assert.deepEqual(tagTermSuggestions(known, "beta"), []);
  assert.deepEqual(tagTermSuggestions(known, "tag:", 2), ["alpha", "beta"]);
});

test("withTagTerm replaces the last word and keeps the rest", () => {
  assert.equal(withTagTerm("tag:b", "beta"), "tag:beta ");
  assert.equal(withTagTerm("home tag:beta tag:a", "alpha"), "home tag:beta tag:alpha ");
});

test("date groups by local calendar day", () => {
  assert.equal(dateGroup(at(2026, 10, 29, 0, 0), NOW), "Today");
  assert.equal(dateGroup(at(2026, 10, 28, 23, 59), NOW), "Yesterday");
  assert.equal(dateGroup(at(2026, 10, 28, 0, 0), NOW), "Yesterday");
  assert.equal(dateGroup(at(2026, 10, 27, 23, 59), NOW), "Previous 7 days");
  assert.equal(dateGroup(at(2026, 10, 22, 0, 0), NOW), "Previous 7 days"); // across the end of summer time (25 Oct) in Europe
  assert.equal(dateGroup(at(2026, 10, 21, 23, 59), NOW), "Older");
});

test("a future timestamp is Today, an unparseable one Older", () => {
  assert.equal(dateGroup(at(2026, 10, 30, 1), NOW), "Today");
  assert.equal(dateGroup("not a date", NOW), "Older");
});

test("pinned first, then the date groups in order, newest first, empty groups left out", () => {
  const list = [
    meta("old", { updated_at: at(2026, 9, 1) }),
    meta("today-1", { updated_at: at(2026, 10, 29, 8) }),
    meta("pinned-old", { pinned: true, updated_at: at(2026, 1, 1) }),
    meta("today-2", { updated_at: at(2026, 10, 29, 9) }),
    meta("week", { updated_at: at(2026, 10, 24) }),
    meta("pinned-new", { pinned: true, updated_at: at(2026, 10, 29, 9, 30) }),
  ];
  assert.deepEqual(
    sections(list, NOW).map((s) => [s.label, s.sessions.map((x) => x.id)]),
    [
      ["Pinned", ["pinned-new", "pinned-old"]],
      ["Today", ["today-2", "today-1"]],
      ["Previous 7 days", ["week"]],
      ["Older", ["old"]],
    ],
  );
  assert.deepEqual(sections([], NOW), []);
});
