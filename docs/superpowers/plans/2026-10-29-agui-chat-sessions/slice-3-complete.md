# Slice 3/3: complete — search, tags, groups, header, reconciliation; instance and archive checks

Completes the sidebar of spec §3 (as amended by its clarification 4) on top of slice 2's list, row menu and URL:
the title search with Open WebUI's `tag:<name>` terms and their suggestions, the date groups, *Show hidden*, the
chat header's rename and `⋯` menu, the controls disabled during a run and the list reconciliation after it. Then the checks that need an instance: "Session API answers", `chat-ui`'s hardening as
`docker inspect` reports it and the key scan over the `chat-sessions` volume in `roles/agui/tasks/checks.yml` (run
by `create.yml` and `verify.yml`), the `archive.yml` runs of decision 11 on the dev VM with `fake_agent.py`
standing in for the agent, and the one paid check. The last task closes the track.

**Implements:** spec [`2026-10-29-agui-chat-sessions-design.md`](../../specs/2026-10-29-agui-chat-sessions-design.md),
§3 *The sidebar* (Layout, Chat header, During a run, Refresh), §5 *Key scan as a detector*, §6 *On an instance* and
*One paid check*. Decisions **1** (its `docker inspect` acceptance check: task 3), **9** (the rest of it: task 1,
`lib/sidebar-view.test.ts` and `check_view`; task 2, `check_header`), **10** (task 2, `lib/reconcile.test.ts` and `check_stop` in the runs `all` and `stop`), **11** (task 4, the `archive.yml` runs on the dev VM), **13** (task 3, the key scan), **14**
(task 1: search treats HTML as text, `check_view` searches a seeded `<img …>` title), **15** (task 3, "Session API
answers").

**Branch:** `impl/agui-chat-sessions-3-complete`, from `main` after slice 2 merged. Global constraints, shared
interfaces and Review Focus: [plan README](README.md). Paths are relative to the repository root; `CHAT` is
`platform/agui/copilotkit-chat`.

**What this slice takes from slice 2** ([slice-2-sidebar.md](slice-2-sidebar.md), tasks 1, 2, 6 and 7; its merged
code is authoritative, and a difference found there is recorded as a ruling in the handoff):

- `CHAT/lib/client.ts`: `type Fetch`, `ApiError`, `fetchSessions`, `fetchSession`, `updateSession`, `removeSession`
  (each with an optional `f?: Fetch`), `listOrder` (removed here, task 1), `renamePatch`, `withTag`, `withoutTag`,
  `tagSuggestions(known, current, input, max = 8)` (the tag editor's). `CHAT/lib/menu.ts` (`popoverPosition`,
  `menuIndex(key, current, count)`), `CHAT/lib/session-url.ts` and `CHAT/lib/session-id.ts` are used unchanged.
- `CHAT/app/sidebar.tsx` (slice 2's task 6 and 7, Open WebUI's look, spec clarification 4): `Sidebar({ sessions,
  knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError })`, which owns one `busy` state (the row whose
  menu, rename, tag editor or delete dialog is open; closed on a press outside, Escape, a choice) and renders each
  row inline (`row(s)`: `<li className="spe-row …">`, no row attribute: task 1 adds `data-session-id`), with the
  classes `.spe-row-active`, `.spe-row-menu-open`, `.spe-row-renaming`, `.spe-row-open` (the title button, which
  also renames on double-click), `.spe-row-title`, `.spe-pin` (screen-reader text only), `.spe-row-menu` (the
  `⋯`), `.spe-rename`. Rows show the title only, no tags. Above the list: `.spe-sidebar-top` (`.spe-brand`, the
  collapse `.spe-icon-button`), `.spe-sidebar-actions` with *New chat* `.spe-new` and the comment `{/* Title search
  goes here. */}`; the list `.spe-sidebar-list` with a `.spe-section` heading ("Pinned", "Chats") over each `<ul
  className="spe-list">`; `.spe-empty` ("No sessions yet."); below it `.spe-note` ("Deleted sessions are kept in
  the run archive."). In the same file, `RowMenu` (`.spe-menu`, `role="menu"`, items Rename, Pin/Unpin, Tags,
  Hide/Unhide, Delete `.spe-menu-danger`) and `RenameInput`. Beside it: `app/popover.tsx` (`Popover({ anchor, box,
  children })`, `.spe-popover`), `app/tag-editor.tsx` (`TagEditor({ tags, draft, suggestions, error, onDraft,
  onAdd, onRemove })`: pills `.spe-chip`, `.spe-tag-input`, `.spe-tag-suggestions` with arrow keys and Enter),
  `app/delete-dialog.tsx` (`DeleteDialog({ onCancel, onDelete })`, `role="alertdialog"`), `app/icons.tsx`,
  `app/keys.ts` (`composing(e)`). Labels: `Session title`, `Add a tag`, `Remove tag <t>`, `Menu for <title>`,
  `Hide sessions`, `Show sessions`.
- `CHAT/app/page.tsx`: state `sessions`, `active`, `activeRef`; `refresh()`, `select()`, `startNew()`, `open()`,
  `showInUrl()`, `messageOf()`; passes `listOrder(sessions)` to `Sidebar`; renders task 7's quiet title row
  `<header className="spe-header"><h1 className="spe-header-title">` (the open session's title, else "New
  chat"); the note that this is the SPE agent and every tool call is shown is CopilotKit's disclaimer under the
  composer (`LABELS.chatDisclaimerText`), not in the header. **How it learns a run ended:** an effect subscribes
  `agent.subscribe({ onRunFinalized: ended, onRunFailed: ended })`, where `ended` calls `refresh()` once and then
  puts the open session into the URL if the list has it. Task 2 replaces that effect.
- `CHAT/app/globals.css`, slice 2's whole file: every colour is a token on `:root` with a dark block under
  `@media (prefers-color-scheme: dark)` (`--text`, `--text-muted`, `--text-placeholder`, `--line`, `--line-strong`,
  `--hover`, `--selected`, `--menu-bg`, `--menu-border`, `--menu-hover`, `--button-off-text`, `--radius-row`,
  `--radius-item`, `--radius-menu`, `--shadow-menu`, `--hover-transition`, …), and no rule after the token blocks
  names a colour. This slice's CSS uses those tokens only, so it holds in light and dark.
- `platform/dev/e2e/sessions.py` (Python Playwright; slice 2's ruling 1): `Run` (`page`, `sessions`, `shot`, `ok`,
  `files`, `wait_runs`, `url_session`, `rows`, `row`, `send`, `menu`), `check_list(r) -> ids`, `check_focus(r, ids)`,
  `check_menu(r, ids)`, `check_close_tab(r, ids)`, `BASE`, `XSS`, `main()`, which calls the four checks in that
  order. After
  `check_close_tab` there are three sessions: "List the home directory (exfil try)" (pinned, tags `exfil, dns`, two
  runs), "Read the dataset" (hidden, a second `completed` run from `check_close_tab`), "Try the canary" (deleted).
  Task 2 adds checks after them, and its new `main()` keeps calling all four.
- Slice 2's dev-VM commands (its task 5, steps 5 and 6, ruling 5): `create.yml` from the main checkout with
  `-e spe_agui_source_dir=$W/platform/agui`; `archive.yml` (and here `verify.yml`) from the worktree with the main
  checkout's instance file and `-e spe_output_root=$M/platform/ansible/output`, so the branch's roles run.

**Additions to the README's shared interfaces** (new in this slice, used only inside it):
`lib/sidebar-view.ts`: `type DateGroup`, `type SectionLabel`, `type Section`, `type ViewFilter = { query: string;
showHidden: boolean }`, `type ParsedQuery = { text: string; tags: string[] }`, `parseQuery(query): ParsedQuery`,
`filterSessions(list, filter): SessionMeta[]`, `tagTermSuggestions(known, query, max = 8): string[]`,
`withTagTerm(query, tag): string`, `dateGroup(updatedAt: string, now: Date): DateGroup`, `sections(list, now:
Date): Section[]`. `lib/reconcile.ts`:
`SAVE_FAILED_MESSAGE`, `RECONCILE_RETRIES = 5`, `RECONCILE_DELAY_MS = 500`, `SAVE_FAILED_EVENT` (equal to slice 1's
`SAVE_FAILED`), `REFUSED_RUN_MESSAGES` (equal to slice 1's `REFUSAL_MESSAGES`; `lib/reconcile.ts` is browser code
and does not import `lib/recorder.ts`), `clockOffset(dateHeader, browserNowMs): number`,
`serverRunStart(browserStartMs, serverOffsetMs): number`, `showsRun(list, id, runStartServerMs): boolean`,
`isRefusal(message): boolean`, `isSaveFailed(event: { name: string; value?: unknown }, id: string): boolean`,
`fetchSessionList(f?: Fetch):
Promise<{ list; serverOffsetMs }>`, `reconcile(fetchList, id, browserStartMs, sleep?): Promise<{ list; saved }>`.
`app/session-filters.tsx`: `SearchBox({ query, knownTags, onChange })`, `HiddenToggle`, `DELETED_NOTE`.
`app/row-menu.tsx` (task 2 moves them out of `sidebar.tsx`): `RowMenu` (gains `deleteDisabled?: boolean`),
`RenameInput` (gains `label` and `className`, defaults `"Session title"` and `"spe-rename"`). `app/chat-header.tsx`:
`ChatHeader({ session, knownTags, running, onPatch, onDelete, onError })`. `app/use-run-reconcile.ts`:
`useRunReconcile({ openId, onList, onError }): { busy: boolean; noteRunError(message): void }`. `Sidebar` gains
`running: boolean` (named so, because `busy` is already its row state). `sessions.py` gains
`check_view`, `check_header`, `check_stop`, `check_save_failed`, `slow_loop`, `two_turn`, `InstanceRun` and the options `--scenario`,
`--save-delay-ms`, `--url`, `--compose-file`. `platform/dev/fake_agent.py` gains `--run-log PATH` and reads `--key`
from `SPE_AGENT_API_KEY` when it is not given.

**Tried before writing this plan** (scratch, Node 24.21, the main checkout's `node_modules` read only, slice 2's
task 1–2 code extracted from its plan file with a stub of slice 1's `lib/sessions.ts` types):
- `node --test` over `lib/`: 26 pass, 0 fail (slice 2's 7 without the `listOrder` test, `sidebar-view` 10,
  `reconcile` 9 in its first version), and `sidebar-view` alone under `TZ=UTC`, `Europe/Berlin`, `America/New_York`,
  `Pacific/Kiritimati` and `Australia/Lord_Howe`. With `sidebar-view.ts` absent its test fails with
  `ERR_MODULE_NOT_FOUND`.
- `reconcile.test.ts` as written below, beside slice 1's `lib/recorder.ts` (with `REFUSAL_MESSAGES`) and
  `lib/sessions.ts`: 12 pass. Three mutations fail it: the 1 s slack put back into `serverRunStart` (the 30 s case
  and the 1.5 s case), a refusal message dropped from `REFUSED_RUN_MESSAGES`. `tsc` accepts
  `app/use-run-reconcile.ts` against CopilotKit 1.79's `AgentSubscriber` and rejects a misspelt `onCustomEvent`.
- `tsc --noEmit` (the chat UI's options plus `allowImportingTsExtensions`) clean after task 1 and after task 2. The
  diffs below `git apply` cleanly to slice 2's `page.tsx` and to task 1's `sidebar.tsx` and give exactly the tested
  files. `next build` could not run in scratch (Turbopack refuses a symlinked `node_modules`).
- `sessions.py` with task 2's additions: `py_compile`, `pyflakes` and `--help` clean. It was not run in a browser:
  that needs slices 1 and 2.
- `checks.yml` (task 3) against a stub API and a `node:24-slim` stand-in for `chat-ui`: passes on clean files; fails
  naming `/data/sessions/b.json` when it holds the LLM key; fails on a 200 that is not a list; fails with "could
  not scan" when `/data/sessions` is absent. The hardening check (task 3, step 4) against a compose project with
  `chat-ui`'s `read_only`, tmpfs and volume: passes; fails naming the value with `read_only: false`, an extra bind
  mount, an extra tmpfs; fails with no `chat-ui` container.
- `fake_agent.py` with task 4's change inside the instance's agent image (`spe-agent:ac7fe88374e0`, read-only root,
  the `agent-runs` volume) through `fake-agent.compose.yml`: healthy, a run streams `RUN_FINISHED`, one line lands in
  `/var/lib/spe-agent/runs.jsonl`, and the key is not in the process's argv.
- A stub `destroy.yml` importing a stub `archive.yml` whose export fails: neither the write play nor the destroy
  play runs.

### Task 1: sidebar view — search with `tag:` terms, date groups, *Show hidden*

**Files:** Create: `CHAT/lib/sidebar-view.ts`, `CHAT/lib/sidebar-view.test.ts`, `CHAT/app/session-filters.tsx`.
Modify: `CHAT/app/sidebar.tsx` (diff below), `CHAT/app/page.tsx`, `CHAT/lib/client.ts`, `CHAT/lib/client.test.ts`,
`CHAT/app/globals.css`.

**Interfaces:** Consumes: `SessionMeta` (slice 1); slice 2's `Sidebar` (its inline `row(s)` and `busy` state),
`listOrder`, `menuIndex` (`lib/menu.ts`), `composing` (`app/keys.ts`). Produces: the `lib/sidebar-view.ts` names
above; `SearchBox`, `HiddenToggle`, `DELETED_NOTE`; `data-session-id` on each row, `<section className="spe-group"
data-group="<label>">` around each group's `.spe-section` heading and `.spe-list`, the class `spe-row-hidden`, the
suggestion list `.spe-search-suggestions` (`role="listbox"`, options `tag:<name>`); the labels `Search titles`,
`Tags in use` (the listbox) and `Show hidden`. The page now passes every session; the sidebar filters and orders
them.

**Decisions:** 9 as amended by spec clarification 4 (search; Open WebUI's `tag:<name>` terms, several of which
must all match, the rest of the query filtering titles; suggestions when `tag:` is typed; pinned first then date
groups; *Show hidden*; the deleted note; rows keep showing the title only, no tags), 14 (search treats HTML and
regular-expression characters as text; all React text). The query is split on whitespace: each `tag:<name>` term
is a tag (lower-cased, as the server stores tags, whose names hold no spaces: `a-z 0-9 . _ -`), a bare `tag:` still
being typed is ignored, and the other words, joined by one space, must be a case-insensitive substring of the
title. While the query's last word starts with `tag:`, the box lists the tags in use (all sessions', hidden ones
included: the page's `knownTags`) that start with what follows it, leaving out those the query already names, at
most 8; as the tag editor's suggestions (slice 2, task 6), the arrow keys pick one, Enter or a click takes it, and
Escape hides them; taking one completes the word to `tag:<name> ` (Open WebUI's `SearchInput.svelte`). Groups use
the browser's local calendar day: "Today" since local midnight, "Yesterday" the local day before, "Previous 7 days"
the six days before that, by calendar day, so a daylight-saving change moves nothing. The groups replace slice 2's
"Pinned" / "Chats" headings. A row whose menu is open and that the filter hides is no longer busy (slice 2's rule
for a row that left the list).

- [ ] **Step 1: Write the failing test** `CHAT/lib/sidebar-view.test.ts`

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { SessionMeta } from "./sessions.ts";
import { dateGroup, filterSessions, parseQuery, sections, tagTermSuggestions, withTagTerm } from "./sidebar-view.ts";

// Local wall-clock times, so the tests hold in any time zone (run them with TZ set to check).
const at = (y: number, mo: number, d: number, h = 12, mi = 0) => new Date(y, mo - 1, d, h, mi).toISOString();
const NOW = new Date(2026, 9, 29, 10, 0); // 29 October 2026, 10:00 local

function meta(id: string, over: Partial<SessionMeta> = {}): SessionMeta {
  return { id, title: id, tags: [], pinned: false, hidden: false, created_at: at(2026, 10, 1),
           updated_at: at(2026, 10, 29, 9), ...over };
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `(cd platform/agui/copilotkit-chat && node --test lib/sidebar-view.test.ts)`
Expected: FAIL, `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '…/lib/sidebar-view.ts'`.

- [ ] **Step 3: Write `CHAT/lib/sidebar-view.ts`**

```ts
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
```

- [ ] **Step 4: Run it to see it pass, in several time zones**

Run: `(cd platform/agui/copilotkit-chat && for tz in UTC Europe/Berlin America/New_York Pacific/Kiritimati; do TZ=$tz node --test lib/sidebar-view.test.ts || exit 1; done)`
Expected: `pass 10`, `fail 0` four times.

- [ ] **Step 5: Retire `listOrder`** (`sections()` and `filterSessions()` replace it, as slice 2 announced). In
  `CHAT/lib/client.ts` delete the function `listOrder` and its comment line ("The list as the sidebar shows it: …").
  In `CHAT/lib/client.test.ts` delete the test `"listOrder: hidden out, pinned first, then newest first"` and
  `listOrder, ` from the import of `./client.ts`. `grep -rn listOrder platform/agui` then finds only `page.tsx`,
  changed in step 7.

- [ ] **Step 6: Write `CHAT/app/session-filters.tsx`**

```tsx
"use client";
// The sidebar's filters: the title search with Open WebUI's `tag:<name>` terms and its suggestions,
// above the list; the *Show hidden* toggle and the note on deleted sessions below it. All text is
// React text.
import { useEffect, useState } from "react";
import { menuIndex } from "../lib/menu.ts";
import { tagTermSuggestions, withTagTerm } from "../lib/sidebar-view.ts";
import { composing } from "./keys.ts";

export const DELETED_NOTE = "Deleted sessions are kept in the run archive.";

type SearchProps = { query: string; knownTags: string[]; onChange: (query: string) => void };

// Typing `tag:` lists the tags in use under the box (as the tag editor's suggestions: arrows pick,
// Enter or a click takes one, Escape hides them); taking one completes the word to `tag:<name> `.
export function SearchBox({ query, knownTags, onChange }: SearchProps) {
  const [picked, setPicked] = useState(-1);
  const [dismissed, setDismissed] = useState(false);
  const [focused, setFocused] = useState(false);
  const suggestions = focused && !dismissed ? tagTermSuggestions(knownTags, query) : [];
  useEffect(() => setPicked(-1), [query, suggestions.length]);
  const take = (tag: string) => {
    onChange(withTagTerm(query, tag));
    setDismissed(false);
  };
  return (
    <div className="spe-search-box">
      <input
        type="search"
        className="spe-search"
        aria-label="Search titles"
        placeholder="Search"
        value={query}
        aria-autocomplete="list"
        aria-expanded={suggestions.length > 0}
        aria-controls={suggestions.length > 0 ? "spe-search-suggestions" : undefined}
        aria-activedescendant={picked >= 0 ? `spe-search-suggestion-${picked}` : undefined}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(e) => {
          setDismissed(false);
          onChange(e.target.value);
        }}
        onKeyDown={(e) => {
          if (composing(e) || suggestions.length === 0) return;
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setPicked((i) => menuIndex(e.key, i, suggestions.length) ?? -1);
          } else if (e.key === "Enter" && picked >= 0) {
            e.preventDefault();
            take(suggestions[picked]);
          } else if (e.key === "Escape") {
            e.preventDefault(); // the search box's own Escape would clear the query
            setDismissed(true);
          }
        }}
      />
      {suggestions.length > 0 && (
        <ul className="spe-search-suggestions" id="spe-search-suggestions" role="listbox" aria-label="Tags in use">
          {suggestions.map((t, i) => (
            // mousedown, and its default prevented: the input keeps focus.
            <li key={t} id={`spe-search-suggestion-${i}`} role="option" aria-selected={i === picked}
              className={i === picked ? "spe-search-suggestion-picked" : undefined}
              onMouseDown={(e) => { e.preventDefault(); take(t); }}>
              <span className="spe-search-suggestion-prefix">tag:</span>{t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type HiddenProps = { showHidden: boolean; onChange: (showHidden: boolean) => void };

export function HiddenToggle({ showHidden, onChange }: HiddenProps) {
  return (
    <div className="spe-sidebar-foot">
      <label className="spe-hidden-toggle">
        <input type="checkbox" checked={showHidden} onChange={(e) => onChange(e.target.checked)} /> Show hidden
      </label>
      <p className="spe-note">{DELETED_NOTE}</p>
    </div>
  );
}
```

- [ ] **Step 7: The sidebar and the page.** Apply to `CHAT/app/sidebar.tsx` (slice 2's task 6–7 file; changed: the
  header comment, the imports, the `filter` state with `visible` and `shown`, `busySession` taken from the visible
  rows, the row's `data-session-id` and hidden class, the search box in place of the placeholder comment, the
  list as groups, `HiddenToggle` in place of the note) and to `CHAT/app/page.tsx` (the page passes every session;
  the sidebar decides what shows):

```diff
diff --git a/platform/agui/copilotkit-chat/app/page.tsx b/platform/agui/copilotkit-chat/app/page.tsx
index edc0e58..14e3cef 100644
--- a/platform/agui/copilotkit-chat/app/page.tsx
+++ b/platform/agui/copilotkit-chat/app/page.tsx
@@ -12,7 +12,7 @@ import {
   useDefaultRenderTool,
 } from "@copilotkit/react-core/v2";
 import { useCallback, useEffect, useRef, useState } from "react";
-import { fetchSession, fetchSessions, listOrder } from "../lib/client.ts";
+import { fetchSession, fetchSessions } from "../lib/client.ts";
 import { searchWith, sessionFromSearch } from "../lib/session-url.ts";
 import type { SessionMeta } from "../lib/sessions.ts";
 import { ChevronRight } from "./icons";
@@ -182,6 +182,6 @@ function Chat() {
   return (
     <div className="spe-layout">
       <Sidebar
-        sessions={listOrder(sessions)}
+        sessions={sessions}
         knownTags={[...new Set(sessions.flatMap((s) => s.tags))].sort()}
         activeId={active}
diff --git a/platform/agui/copilotkit-chat/app/sidebar.tsx b/platform/agui/copilotkit-chat/app/sidebar.tsx
index cc46485..2f1fa35 100644
--- a/platform/agui/copilotkit-chat/app/sidebar.tsx
+++ b/platform/agui/copilotkit-chat/app/sidebar.tsx
@@ -1,5 +1,6 @@
 "use client";
-// The sessions sidebar: New chat, the list (pinned first, then newest) and each row's menu.
+// The sessions sidebar: New chat, the title search (with `tag:` terms), the list the search shows
+// (pinned first, then Today / Yesterday / Previous 7 days / Older), each row's menu, and Show hidden.
 // Titles and tags are model or participant text: rendered as React text only, never as HTML.
 //
 // One owner for what a row is doing: `Sidebar` holds which row has its menu, rename, tag editor or
@@ -12,10 +13,13 @@ import type { KeyboardEvent, MouseEvent } from "react";
 import { removeSession, renamePatch, tagSuggestions, updateSession, withTag, withoutTag } from "../lib/client.ts";
 import { menuIndex } from "../lib/menu.ts";
 import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
+import { filterSessions, sections } from "../lib/sidebar-view.ts";
+import type { ViewFilter } from "../lib/sidebar-view.ts";
 import { DeleteDialog } from "./delete-dialog";
 import { Ellipsis, Eye, EyeSlash, PencilSquare, Pencil, Pin, PinSlash, SidebarToggle, Tag, Trash } from "./icons";
 import { composing } from "./keys.ts";
 import { Popover } from "./popover";
+import { HiddenToggle, SearchBox } from "./session-filters";
 import { TagEditor } from "./tag-editor";
 
 type SidebarProps = {
@@ -45,7 +49,11 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
   const [collapsed, setCollapsed] = useState(false);
   const triggers = useRef(new Map<string, HTMLButtonElement>());
   const popover = useRef<HTMLDivElement>(null);
-  const busySession = busy ? sessions.find((s) => s.id === busy.id) : undefined;
+  const [filter, setFilter] = useState<ViewFilter>({ query: "", showHidden: false });
+  // `sessions` is every session the server lists; the filter decides which rows show.
+  const visible = filterSessions(sessions, filter);
+  const shown = sections(visible, new Date());
+  const busySession = busy ? visible.find((s) => s.id === busy.id) : undefined;
   const suggestions = busy?.mode === "tags" && busy.suggest && busySession
     ? tagSuggestions(knownTags, busySession.tags, busy.draft)
     : [];
@@ -184,10 +192,11 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
     const popoverOpen = mine?.mode === "menu" || mine?.mode === "tags";
     const classes = ["spe-row"];
     if (s.id === activeId) classes.push("spe-row-active");
+    if (s.hidden) classes.push("spe-row-hidden");
     if (popoverOpen) classes.push("spe-row-menu-open");
     if (mine?.mode === "rename") classes.push("spe-row-renaming");
     return (
-      <li key={s.id} className={classes.join(" ")}>
+      <li key={s.id} className={classes.join(" ")} data-session-id={s.id}>
         {mine?.mode === "rename" ? (
           <RenameInput
             value={mine.draft}
@@ -217,10 +226,6 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
       </li>
     );
   };
-  // `sessions` comes ordered, pinned first.
-  const pinned = sessions.filter((s) => s.pinned);
-  const others = sessions.filter((s) => !s.pinned);
-
   return (
     <nav className="spe-sidebar" aria-label="Sessions">
       <div className="spe-sidebar-top">
@@ -230,24 +235,21 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
       </div>
       <div className="spe-sidebar-actions">
         <button type="button" className="spe-new" onClick={newChat}><PencilSquare />New chat</button>
-        {/* Title search goes here. */}
+        <SearchBox query={filter.query} knownTags={knownTags} onChange={(query) => setFilter({ ...filter, query })} />
       </div>
       <div className="spe-sidebar-list">
-        {pinned.length > 0 && (
-          <>
-            <h3 className="spe-section" id="spe-section-pinned">Pinned</h3>
-            <ul className="spe-list" aria-labelledby="spe-section-pinned">{pinned.map(row)}</ul>
-          </>
-        )}
-        {pinned.length > 0 && others.length > 0 && <h3 className="spe-section" id="spe-section-chats">Chats</h3>}
-        {others.length > 0 && (
-          <ul className="spe-list" aria-labelledby={pinned.length > 0 ? "spe-section-chats" : undefined}>
-            {others.map(row)}
-          </ul>
+        {shown.map((section, i) => (
+          <section key={section.label} className="spe-group" data-group={section.label}
+            aria-labelledby={`spe-section-${i}`}>
+            <h3 className="spe-section" id={`spe-section-${i}`}>{section.label}</h3>
+            <ul className="spe-list">{section.sessions.map(row)}</ul>
+          </section>
+        ))}
+        {shown.length === 0 && (
+          <p className="spe-empty">{sessions.length === 0 ? "No sessions yet." : "No session matches."}</p>
         )}
-        {sessions.length === 0 && <p className="spe-empty">No sessions yet.</p>}
       </div>
-      <p className="spe-note">Deleted sessions are kept in the run archive.</p>
+      <HiddenToggle showHidden={filter.showHidden} onChange={(showHidden) => { end(); setFilter({ ...filter, showHidden }); }} />
 
       {busySession && busy?.mode === "menu" && (
         <Popover anchor={triggers.current.get(busy.id)} box={popover} key={`menu-${busy.id}`}>
```

- [ ] **Step 8: Styles.** Apply to `CHAT/app/globals.css`: the first group's heading takes the first heading's
  tighter top padding, and a new section before the row popover's; the reduced-motion list gains
  `.spe-search-suggestions`, which also animates in. Tokens only (no colour outside the token blocks), so light
  and dark both hold:

```diff
diff --git a/platform/agui/copilotkit-chat/app/globals.css b/platform/agui/copilotkit-chat/app/globals.css
index 0d9bc5d..fb266e3 100644
--- a/platform/agui/copilotkit-chat/app/globals.css
+++ b/platform/agui/copilotkit-chat/app/globals.css
@@ -210,7 +210,7 @@ body {
   scrollbar-width: thin; scrollbar-color: var(--scrollbar) transparent; }
 .spe-section { margin: 0; padding: 16px 8px 4px; font-size: 12px; line-height: 16px; font-weight: 400;
   color: var(--text-muted); }
-.spe-sidebar-list > .spe-section:first-child { padding-top: 4px; }
+.spe-sidebar-list > .spe-group:first-child > .spe-section { padding-top: 4px; }
 .spe-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1px; }
 .spe-empty { margin: 0; padding: 8px; font-size: 13px; color: var(--text-muted); }
 .spe-note { margin: 0; padding: 8px 8px 0; font-size: 12px; line-height: 16px; color: var(--text-muted); }
@@ -241,6 +241,31 @@ body {
   outline: none; box-shadow: inset 0 0 0 1px var(--line-strong); }
 .spe-rename:focus-visible { outline: none; box-shadow: inset 0 0 0 1.5px var(--focus-ring); }
 
+/* ---------- Sidebar: search with tag: suggestions, Show hidden ---------- */
+
+.spe-search-box { position: relative; }
+.spe-search { width: 100%; height: 32px; box-sizing: border-box; margin: 0; padding: 6px 8px; border: 0;
+  border-radius: var(--radius-row); background: none; color: var(--text); font: inherit; outline: none;
+  box-shadow: inset 0 0 0 1px var(--line); transition: box-shadow var(--hover-transition); }
+.spe-search::placeholder { color: var(--text-placeholder); }
+.spe-search:focus, .spe-search:focus-visible { outline: none; box-shadow: inset 0 0 0 1px var(--line-strong); }
+/* Open WebUI's suggestion panel: under the box, over the list. */
+.spe-search-suggestions { position: absolute; z-index: 40; top: calc(100% + 4px); left: 0; right: 0;
+  max-height: 192px; overflow-y: auto; list-style: none; margin: 0; padding: 4px;
+  border: 1px solid var(--menu-border); border-radius: var(--radius-menu); background: var(--menu-bg);
+  box-shadow: var(--shadow-menu); animation: spe-fade 50ms ease-out; }
+.spe-search-suggestions li { padding: 5px 8px; border-radius: var(--radius-item); font-size: 12px; line-height: 16px;
+  cursor: pointer; overflow-wrap: anywhere; }
+.spe-search-suggestions li:hover, .spe-search-suggestion-picked { background: var(--menu-hover); }
+.spe-search-suggestion-prefix { color: var(--text-muted); }
+.spe-row-hidden .spe-row-title { color: var(--text-muted); font-style: italic; }
+.spe-sidebar-foot { display: flex; flex-direction: column; gap: 4px; padding: 8px 8px 0;
+  border-top: 1px solid var(--line); }
+.spe-sidebar-foot .spe-note { padding: 0; }
+.spe-hidden-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; line-height: 16px;
+  color: var(--text-muted); cursor: pointer; }
+.spe-hidden-toggle input { margin: 0; accent-color: var(--button-strong-bg); }
+
 /* ---------- Row popover: menu and tag editor ---------- */
 
 /* Floats over the list (fixed, placed by the sidebar under or above its ⋯). */
@@ -378,4 +378,4 @@ body {
 @media (prefers-reduced-motion: reduce) {
-  .spe-popover, .spe-dialog, .spe-dialog-backdrop { animation: none; }
+  .spe-popover, .spe-dialog, .spe-dialog-backdrop, .spe-search-suggestions { animation: none; }
   .spe-tool-chevron.spe-icon { transition: none; }
 }
```

- [ ] **Step 9: Run the suites**

Run: `(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)`
Expected: every test passes (slice 1's, slice 2's without the `listOrder` test, the 10 new); `next build` compiles
and type-checks. `grep -rn "dangerouslySetInnerHTML\|listOrder" platform/agui/copilotkit-chat/app platform/agui/copilotkit-chat/lib`
prints nothing. Slice 2's browser run still passes (`python3 platform/dev/e2e/sessions.py`: its `ok - …` lines; the
hidden session is still left out by default, the pinned row still first).

- [ ] **Step 10: Commit**

```bash
git add platform/agui/copilotkit-chat/lib/sidebar-view.ts platform/agui/copilotkit-chat/lib/sidebar-view.test.ts \
  platform/agui/copilotkit-chat/app/session-filters.tsx platform/agui/copilotkit-chat/app/sidebar.tsx \
  platform/agui/copilotkit-chat/app/page.tsx platform/agui/copilotkit-chat/lib/client.ts \
  platform/agui/copilotkit-chat/lib/client.test.ts platform/agui/copilotkit-chat/app/globals.css
git commit -s -m "Chat sidebar: title search with tag: terms, date groups, Show hidden

Pure helpers in lib/sidebar-view.ts (node --test, several time zones) replace listOrder."
```

### Task 2: chat header, controls disabled during a run, reconciliation; the browser checks

**Files:** Create: `CHAT/lib/reconcile.ts`, `CHAT/lib/reconcile.test.ts`, `CHAT/app/use-run-reconcile.ts`,
`CHAT/app/row-menu.tsx` (moved out of `sidebar.tsx`), `CHAT/app/chat-header.tsx`. Modify: `CHAT/app/page.tsx`,
`CHAT/app/sidebar.tsx`, `CHAT/app/globals.css`,
`platform/dev/e2e/sessions.py`, `CHAT/README.md` (*Sessions*).

**Interfaces:** Consumes: task 1; `Fetch`, `updateSession`, `removeSession`, `renamePatch`, `withTag`,
`withoutTag`, `tagSuggestions` (`lib/client.ts`); slice 2's `RowMenu`, `RenameInput`, `Popover`, `TagEditor`,
`DeleteDialog`, `Ellipsis`; slice 1's test hook `SPE_SESSIONS_TEST_SAVE_DELAY_MS` (delays the recorder's finalisation write
by that many ms) and `SPE_SESSIONS_DIR`; the recorder's refusal messages ("invalid session", "this session was
deleted", "this session is already running", "the chat UI is shutting down", "this session could not be read",
spec §2 *Admit*; slice 1's `REFUSAL_MESSAGES`) and its save-failed `CUSTOM` event (`SAVE_FAILED`, value `{session:
id}`, sent before the run's terminal event, spec §5); `fake_agent.py`'s slow run (a user message
containing "slow" streams for about 10 s); `@ag-ui/client`'s subscriber hooks `onRunInitialized`,
`onCustomEvent` (`{ event: CustomEvent }`, `event.name` and `event.value`; the CopilotKit runtime passes every
event of the run through to the browser) and `onRunFinalized` (the latter runs in the run's `finalize`, so on
finish, error and abort alike). Produces:
`useRunReconcile`, `app/row-menu.tsx`, `ChatHeader`, `Sidebar`'s `running`; the header's title `.spe-header-title`
(double-click renames), its rename input `.spe-header-rename` labelled `Chat title` (not the rows' `Session title`,
so slice 2's `get_by_label("Session title")` still finds one element) and its `⋯` `.spe-header-menu` labelled
`Chat actions`, which opens the row's `RowMenu`, whose *Tags* opens the same `TagEditor` (labels `Add a tag`,
`Remove tag <t>`: one popover is open at a time, the header's or a row's, since a press outside closes each); the
`sessions.py` scenarios.

**Decisions:** 10 (both controls disabled during a run; after stop enabled, run recorded `cancelled`, the
session's row appears, also with the save delayed), 9 as amended by spec clarification 4 (the header is slice 2's
quiet title row, renamable in place, with the same `⋯` menu as the rows; tags appear only in that menu's tag editor
and in `tag:` search, never as chips in the header or the rows; no banner sentence: the note stays under the
composer; a reload reopens the session with its tool cards), 14 (header text is React text). The header keeps its
own small state (menu, rename, tags, delete) with the sidebar's close and focus rules rather than sharing the
sidebar's `busy`: the two never hold a popover at once, since a press outside closes each. Its popover and dialog
render inside the header, whose `z-index: 10` stacking context is above the chat. Record this as a ruling (cost if
wrong: lifting the state into one owner).

How the reconciliation decides (spec §3, *Refresh*): after a run ends however it ended, the list is fetched until
it has the run's session with an `updated_at` not older than the run's start, at most once plus 5 retries 500 ms
apart; then the error bar says "this session could not be saved". The run's start is taken on the browser's
clock and converted with each answer's `Date` header, so a browser clock that is off does not lose the run. The
header has whole seconds, rounded down, so the converted start is already up to 1 s early: no further slack, or a
save from the previous run up to 2 s before this one would count. A run the recorder refused at admission writes
nothing, so its own `RUN_ERROR` is the only message. When the recorder reports a failed save itself (the
`spe.session_save_failed` event, spec §5), the error bar says "this session could not be saved" at once and the
list is fetched once after the run, without retries. The hook replaces slice 2's run-end effect: the list it returns also puts the open session into the
URL once listed. The open session's *Delete* is disabled during a run as well (it would start a new chat under the
running one, through slice 2's `onDeleted`), in its row's menu and in the header's; record this as a ruling (cost if wrong: one more click after the run).

The header must never say "New chat" while the page's own "Loading…" still shows: on first load, which
session is open is unknown until the URL's `?session=` is resolved, so `ChatHeader`'s `session` prop is
`undefined` for that span (no title shown) and only `null` once a New chat is actually confirmed (`active`
holds a fresh id with no session file yet).

- [ ] **Step 1: Write the failing test** `CHAT/lib/reconcile.test.ts`

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Fetch } from "./client.ts";
// Node-only: the recorder is never imported by the browser module; the test pins the copies.
import { REFUSAL_MESSAGES, SAVE_FAILED } from "./recorder.ts";
import type { SessionMeta } from "./sessions.ts";
import {
  RECONCILE_DELAY_MS, REFUSED_RUN_MESSAGES, SAVE_FAILED_EVENT, SAVE_FAILED_MESSAGE, clockOffset, fetchSessionList,
  isRefusal, isSaveFailed, reconcile, serverRunStart, showsRun,
} from "./reconcile.ts";

const ID = "6f1c0d2e-4b1a-4c3d-8e9f-0a1b2c3d4e5f";
const START = Date.parse("2026-10-29T10:00:00.000Z");
// The browser's start time; with offset 0 the clocks agree.
const BROWSER_START = START;
const row = (updated: string, id = ID): SessionMeta => ({
  id, title: "t", tags: [], pinned: false, hidden: false, created_at: updated, updated_at: updated,
});

test("showsRun: the session present with updated_at not older than the run's start", () => {
  assert.equal(showsRun([row("2026-10-29T10:00:00.000Z")], ID, START), true);
  assert.equal(showsRun([row("2026-10-29T10:00:05.000Z")], ID, START), true);
  assert.equal(showsRun([row("2026-10-29T09:59:59.999Z")], ID, START), false);
  assert.equal(showsRun([row("2026-10-29T10:00:05.000Z", "other")], ID, START), false);
  assert.equal(showsRun([], ID, START), false);
});

test("clockOffset and serverRunStart: a browser clock 30 s fast does not lose the run", () => {
  const browserNow = Date.parse("2026-10-29T10:00:30.000Z");
  const offset = clockOffset("Thu, 29 Oct 2026 10:00:00 GMT", browserNow);
  assert.equal(offset, -30_000);
  assert.equal(serverRunStart(browserNow, offset), START);
  // The browser saw the run start at 10:00:30 by its clock; the server saved at 10:00:02.
  assert.equal(showsRun([row("2026-10-29T10:00:02.000Z")], ID, serverRunStart(browserNow, offset)), true);
  assert.equal(clockOffset(null, browserNow), 0);
  assert.equal(clockOffset("garbage", browserNow), 0);
});

test("reconcile: a save that lands on the third fetch is found, two sleeps of 500 ms", async () => {
  const answers = [[], [row("2026-10-29T09:00:00.000Z")], [row("2026-10-29T10:00:01.000Z")]];
  const sleeps: number[] = [];
  let calls = 0;
  const result = await reconcile(async () => ({ list: answers[calls++], serverOffsetMs: 0 }), ID, BROWSER_START,
    async (ms) => { sleeps.push(ms); });
  assert.equal(result.saved, true);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [RECONCILE_DELAY_MS, RECONCILE_DELAY_MS]);
  assert.equal(result.list[0].updated_at, "2026-10-29T10:00:01.000Z");
});

test("reconcile: each fetch's own clock offset converts the browser's start", async () => {
  // Browser clock 30 s fast: it saw the run start at 10:00:30; the server saved at 10:00:02.
  const result = await reconcile(async () => ({ list: [row("2026-10-29T10:00:02.000Z")], serverOffsetMs: -30_000 }),
    ID, START + 30_000, async () => assert.fail("no sleep expected"));
  assert.equal(result.saved, true);
});

test("reconcile: the previous run's save, 1.5 s before this run's start, is not this run", async () => {
  // Clocks agree. Second case, the Date header's rounding at its worst: the run starts at
  // 10:00:00.999 and the header says 10:00:00, so the offset is 999 ms too small.
  for (const [browserStart, serverOffsetMs] of [
    [START, 0],
    [START + 999, clockOffset("Thu, 29 Oct 2026 10:00:00 GMT", START + 999)],
  ]) {
    const previous = [row(new Date(browserStart - 1500).toISOString())];
    let calls = 0;
    const result = await reconcile(async () => { calls++; return { list: previous, serverOffsetMs }; }, ID,
      browserStart, async () => {});
    assert.deepEqual([result.saved, calls], [false, 6], previous[0].updated_at);
  }
});

test("reconcile: shown at once, no retry", async () => {
  let calls = 0;
  const result = await reconcile(async () => { calls++; return { list: [row("2026-10-29T10:00:01.000Z")], serverOffsetMs: 0 }; },
    ID, BROWSER_START, async () => assert.fail("no sleep expected"));
  assert.deepEqual([result.saved, calls], [true, 1]);
});

test("reconcile: never shown gives up after one fetch and five retries", async () => {
  let calls = 0;
  const result = await reconcile(async () => { calls++; return { list: [], serverOffsetMs: 0 }; }, ID, BROWSER_START, async () => {});
  assert.deepEqual([result.saved, calls], [false, 6]);
  assert.equal(SAVE_FAILED_MESSAGE, "this session could not be saved");
});

test("reconcile: a failing fetch is the caller's error, not a save failure", async () => {
  await assert.rejects(reconcile(async () => { throw new Error("Loading the sessions failed (500)"); }, ID, BROWSER_START, async () => {}),
    /failed \(500\)/);
});

test("isRefusal: the recorder's admission errors, nothing else", () => {
  for (const m of REFUSED_RUN_MESSAGES) assert.equal(isRefusal(m), true, m);
  assert.equal(isRefusal("scripted model failure (the message asked for it)"), false);
});

test("REFUSED_RUN_MESSAGES are the recorder's refusal messages, all of them", () => {
  assert.deepEqual([...REFUSED_RUN_MESSAGES], [...REFUSAL_MESSAGES]);
});

test("isSaveFailed: the recorder's save-failed event for this run's session only", () => {
  assert.equal(SAVE_FAILED_EVENT, SAVE_FAILED);
  assert.equal(isSaveFailed({ name: SAVE_FAILED_EVENT, value: { session: ID } }, ID), true);
  assert.equal(isSaveFailed({ name: SAVE_FAILED_EVENT, value: { session: "other" } }, ID), false);
  assert.equal(isSaveFailed({ name: SAVE_FAILED_EVENT, value: null }, ID), false);
  assert.equal(isSaveFailed({ name: "something.else", value: { session: ID } }, ID), false);
});

test("fetchSessionList: list and offset from one GET; a non-200 throws", async () => {
  const ok: Fetch = async () => new Response(JSON.stringify([row("2026-10-29T10:00:01.000Z")]), {
    status: 200, headers: { "content-type": "application/json", date: new Date(Date.now() + 60_000).toUTCString() },
  });
  const { list, serverOffsetMs } = await fetchSessionList(ok);
  assert.equal(list.length, 1);
  assert.ok(serverOffsetMs > 58_000 && serverOffsetMs <= 60_000, String(serverOffsetMs));
  const bad: Fetch = async () => new Response('{"error":"x"}', { status: 500 });
  await assert.rejects(fetchSessionList(bad), /failed \(500\)/);
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `(cd platform/agui/copilotkit-chat && node --test lib/reconcile.test.ts)`
Expected: FAIL, `ERR_MODULE_NOT_FOUND` for `lib/reconcile.ts`.

- [ ] **Step 3: Write `CHAT/lib/reconcile.ts`**

```ts
// After a run ends, fetch the session list until it shows that run: a run the server saw
// unsubscribed (the stream dropped before its end) is saved after the client has gone, so its
// save can land after the first fetch. Pure apart
// from the injected fetch and sleep, so `node --test` covers it. Browser code: it must not
// import recorder.ts (Node-only); reconcile.test.ts checks the copies below against it.
import type { Fetch } from "./client.ts";
import type { SessionMeta } from "./sessions.ts";

export const SAVE_FAILED_MESSAGE = "this session could not be saved";
export const RECONCILE_RETRIES = 5;
export const RECONCILE_DELAY_MS = 500;
/** Name of the CUSTOM event the recorder sends, before the run's last event, when the session
 *  file could not be written; its value is `{ session: <id> }`. */
export const SAVE_FAILED_EVENT = "spe.session_save_failed";
/** RUN_ERROR messages of a run the recorder refused at admission: such a run writes nothing. */
export const REFUSED_RUN_MESSAGES: readonly string[] = [
  "invalid session",
  "this session was deleted",
  "this session is already running",
  "the chat UI is shutting down",
  "this session could not be read",
];

export type ListResult = { list: SessionMeta[]; serverOffsetMs: number };
export type FetchList = () => Promise<ListResult>;

/** Server clock minus browser clock, from a response's `Date` header; 0 when absent or invalid.
 *  The header has whole seconds, rounded down, so this is up to 1 s too small. */
export function clockOffset(dateHeader: string | null, browserNowMs: number): number {
  const server = dateHeader === null ? NaN : Date.parse(dateHeader);
  return Number.isNaN(server) ? 0 : server - browserNowMs;
}

/** The run's start in server time, from the browser's clock and the last measured offset. The
 *  offset's rounding makes it up to 1 s early: a save is never missed, and a save older than
 *  that is never taken for this run's. */
export function serverRunStart(browserStartMs: number, serverOffsetMs: number): number {
  return browserStartMs + serverOffsetMs;
}

/** True when the list has the session with an `updated_at` not older than the run's start. */
export function showsRun(list: readonly SessionMeta[], id: string, runStartServerMs: number): boolean {
  const s = list.find((x) => x.id === id);
  return s !== undefined && Date.parse(s.updated_at) >= runStartServerMs;
}

/** True when a run error is the recorder's refusal at admission (nothing to reconcile). */
export function isRefusal(message: string): boolean {
  return REFUSED_RUN_MESSAGES.some((m) => message.includes(m));
}

/** True when a CUSTOM event is the recorder's report that session `id` could not be saved. */
export function isSaveFailed(event: { name: string; value?: unknown }, id: string): boolean {
  const value = event.value as { session?: unknown } | null | undefined;
  return event.name === SAVE_FAILED_EVENT && typeof value === "object" && value !== null && value.session === id;
}

/** GET /api/sessions, as lib/client.ts's fetchSessions, plus the clock offset its `Date` header
 *  gives. Throws on a non-200. */
export async function fetchSessionList(f?: Fetch): Promise<ListResult> {
  const res = await (f ?? ((input, init) => fetch(input, init)))("/api/sessions", { cache: "no-store" });
  if (res.status !== 200) throw new Error(`Loading the sessions failed (${res.status})`);
  const list = (await res.json()) as SessionMeta[];
  return { list, serverOffsetMs: clockOffset(res.headers.get("date"), Date.now()) };
}

/** Fetch the list once, then up to RECONCILE_RETRIES more times RECONCILE_DELAY_MS apart, until
 *  it shows the run that started at `browserStartMs` (the browser's clock; each fetch's `Date`
 *  header converts it to server time). `saved` false: it never did (the page shows
 *  SAVE_FAILED_MESSAGE). The last list fetched is returned either way, for the sidebar. A fetch
 *  that throws ends the loop: the caller shows that error instead. */
export async function reconcile(
  fetchList: FetchList,
  id: string,
  browserStartMs: number,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<{ list: SessionMeta[]; saved: boolean }> {
  for (let retry = 0; ; retry++) {
    const { list, serverOffsetMs } = await fetchList();
    if (showsRun(list, id, serverRunStart(browserStartMs, serverOffsetMs))) return { list, saved: true };
    if (retry === RECONCILE_RETRIES) return { list, saved: false };
    await sleep(RECONCILE_DELAY_MS);
  }
}
```

- [ ] **Step 4: Run it to see it pass**

Run: `(cd platform/agui/copilotkit-chat && node --test lib/reconcile.test.ts)`
Expected: `pass 12`, `fail 0`.

- [ ] **Step 5: Write `CHAT/app/use-run-reconcile.ts`**

```ts
// The agent's run state for the page: `busy` while a run is in progress (the sidebar disables
// switching and New chat), and after each run, however it ended, the list is fetched until it
// shows that run, or the error bar says it was not saved. When the server reports the failed
// save itself (a CUSTOM event during the run), the bar says so at once and the list is fetched
// once, without retries.
import { UseAgentUpdate, useAgent } from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef } from "react";
import type { SessionMeta } from "../lib/sessions.ts";
import { SAVE_FAILED_MESSAGE, fetchSessionList, isRefusal, isSaveFailed, reconcile } from "../lib/reconcile.ts";

type Options = {
  openId: string;
  onList: (list: SessionMeta[]) => void;
  onError: (message: string) => void;
};
type Run = { id: string; startMs: number; refused: boolean; saveFailed: boolean };

const LIST_FAILED = "The session list could not be loaded.";

export function useRunReconcile({ openId, onList, onError }: Options) {
  const { agent } = useAgent({ agentId: "spe", updates: [UseAgentUpdate.OnRunStatusChanged] });
  const latest = useRef({ openId, onList, onError });
  latest.current = { openId, onList, onError };
  const current = useRef<Run | null>(null); // the run in progress
  const last = useRef<Run | null>(null); // the latest run, in progress or ended

  useEffect(() => {
    const sub = agent.subscribe({
      onRunInitialized: () => {
        // The open session is read when a run starts: switching is disabled until it ends.
        current.current = last.current = {
          id: latest.current.openId, startMs: Date.now(), refused: false, saveFailed: false,
        };
      },
      onCustomEvent: ({ event }) => {
        const run = current.current;
        if (run === null || run.saveFailed || !isSaveFailed(event, run.id)) return;
        run.saveFailed = true;
        latest.current.onError(SAVE_FAILED_MESSAGE);
      },
      onRunFinalized: () => {
        const ended = current.current;
        current.current = null;
        if (ended === null) return;
        if (ended.saveFailed) {
          // Already reported; the file will not change, so one fetch for the sidebar is enough.
          fetchSessionList()
            .then(({ list }) => latest.current.onList(list))
            .catch(() => latest.current.onError(LIST_FAILED));
          return;
        }
        reconcile(fetchSessionList, ended.id, ended.startMs)
          .then(({ list, saved }) => {
            latest.current.onList(list);
            // A run refused at admission writes nothing; its own error is already in the bar.
            if (!saved && !ended.refused) latest.current.onError(SAVE_FAILED_MESSAGE);
          })
          .catch(() => latest.current.onError(LIST_FAILED));
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  /** Pass every run error here, so a refusal at admission is not reported as a failed save.
   *  It may arrive just before or after the run ends: the reconciliation takes longer. */
  const noteRunError = useCallback((message: string) => {
    if (last.current !== null && isRefusal(message)) last.current.refused = true;
  }, []);

  return { busy: agent.isRunning, noteRunError };
}
```

- [ ] **Step 6: Move the row menu out of the sidebar, and write `CHAT/app/chat-header.tsx`.** Cut slice 2's
  `RowMenu` and `RenameInput` (from `type RowMenuProps = {` to the end of `CHAT/app/sidebar.tsx`) into
  `CHAT/app/row-menu.tsx`, exported, with `RowMenu`'s new `deleteDisabled` and `RenameInput`'s `label` and
  `className` (defaults keep the rows as they are):

```tsx
"use client";
// A session's `⋯` menu and its in-place rename, shared by the sidebar rows and the chat header.
// Titles are model or participant text: rendered as React text only, never as HTML.
import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import { menuIndex } from "../lib/menu.ts";
import type { SessionMeta } from "../lib/sessions.ts";
import { Eye, EyeSlash, Pencil, Pin, PinSlash, Tag, Trash } from "./icons";
import { composing } from "./keys.ts";

export type RowMenuProps = {
  session: SessionMeta;
  keyboard: boolean;
  onRename: () => void;
  onPin: () => void;
  onTags: () => void;
  onHide: () => void;
  onDelete: () => void;
  /** Delete greyed out: the session is running (its Delete would start a new chat under the run). */
  deleteDisabled?: boolean;
};

// The `⋯` menu of a session, the same for its sidebar row and the chat header.
export function RowMenu({ session, keyboard, onRename, onPin, onTags, onHide, onDelete, deleteDisabled }: RowMenuProps) {
  const menu = useRef<HTMLDivElement>(null);
  const items = () => [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
  // From the keyboard the first item takes focus; from a click the menu itself, so arrows work.
  useEffect(() => {
    if (keyboard) items()[0]?.focus();
    else menu.current?.focus();
  }, [keyboard]);
  const onKeyDown = (e: KeyboardEvent) => {
    const list = items();
    const next = menuIndex(e.key, list.indexOf(document.activeElement as HTMLElement), list.length);
    if (next === null) return;
    e.preventDefault();
    list[next].focus();
  };
  return (
    <div className="spe-menu" role="menu" aria-label={`Menu for ${session.title}`} tabIndex={-1} ref={menu} onKeyDown={onKeyDown}>
      <button type="button" role="menuitem" onClick={onRename}><Pencil />Rename</button>
      <button type="button" role="menuitem" onClick={onPin}>
        {session.pinned ? <><PinSlash />Unpin</> : <><Pin />Pin</>}
      </button>
      <button type="button" role="menuitem" onClick={onTags}><Tag />Tags</button>
      <button type="button" role="menuitem" onClick={onHide}>
        {session.hidden ? <><Eye />Unhide</> : <><EyeSlash />Hide</>}
      </button>
      <div role="separator" className="spe-menu-separator" />
      <button type="button" role="menuitem" className="spe-menu-danger" disabled={deleteDisabled}
        onClick={onDelete}><Trash />Delete</button>
    </div>
  );
}

// Replaces a title in place (a row's, or the chat header's), focused with the text selected.
export function RenameInput({ value, onChange, onSave, onCancel, label = "Session title", className = "spe-rename" }:
  { value: string; onChange: (v: string) => void; onSave: () => void; onCancel: () => void; label?: string;
    className?: string }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <input
      ref={input}
      className={className}
      aria-label={label}
      maxLength={200}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (composing(e)) return;
        if (e.key === "Enter") { e.preventDefault(); onSave(); }
        if (e.key === "Escape") { e.preventDefault(); onCancel(); }
      }}
    />
  );
}
```

  Then `CHAT/app/chat-header.tsx`:

```tsx
"use client";
// The chat header (Open WebUI's navbar): the open session's title, renamable in place (by its menu's
// Rename or a double-click, as a row), and the same `⋯` menu as its sidebar row: RowMenu, the
// TagEditor, the DeleteDialog, with the sidebar's close and focus rules. A session not yet recorded
// (New chat, before its first run ends) shows "New chat" and no menu: PATCH would answer 404. Which
// session is open is still unknown on first load (before the URL's `?session=` is resolved, while
// the page's own "Loading…" shows): `session` is `undefined` then, so the header shows no title at
// all rather than "New chat" while the rest of the page says it is still loading.
// Its rename input is labelled "Chat title", not the rows' "Session title", so a label lookup finds one.
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { renamePatch, tagSuggestions, withTag, withoutTag } from "../lib/client.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
import { DeleteDialog } from "./delete-dialog";
import { Ellipsis } from "./icons";
import { Popover } from "./popover";
import { RenameInput, RowMenu } from "./row-menu";
import { TagEditor } from "./tag-editor";

type Props = {
  /** `undefined`: which session is open is not yet known (first load, still "Loading…"), so
   * nothing is shown. `null`: a confirmed New chat, not yet recorded. */
  session: SessionMeta | null | undefined;
  knownTags: string[];
  /** A run is in progress: Delete is disabled, as in the open session's row. */
  running: boolean;
  /** Saves the change and refreshes the list; rejects with the failure. */
  onPatch: (patch: MetaPatch) => Promise<void>;
  onDelete: () => void;
  onError: (message: string) => void;
};

type Mode =
  | { mode: "menu"; keyboard: boolean }
  | { mode: "rename"; draft: string }
  | { mode: "tags"; draft: string; suggest: boolean; error: string | null }
  | { mode: "delete" };

const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

export function ChatHeader({ session, knownTags, running, onPatch, onDelete, onError }: Props) {
  const [open, setOpen] = useState<Mode | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const header = useRef<HTMLElement>(null);
  const suggestions = open?.mode === "tags" && open.suggest && session
    ? tagSuggestions(knownTags, session.tags, open.draft)
    : [];

  const save = async (patch: MetaPatch | null) => {
    if (!patch) return;
    try {
      await onPatch(patch);
    } catch (e) {
      onError(errorText(e, "Saving the change failed."));
    }
  };
  // As the sidebar's `end`: a rename in progress is saved if it changed the title; a tag typed but
  // not added is dropped.
  const end = (returnFocus = false) => {
    if (!open) return;
    setOpen(null);
    if (open.mode === "rename" && session) void save(renamePatch(open.draft, session.title));
    if (returnFocus) trigger.current?.focus();
  };

  // A press outside ends it: outside the menu and its ⋯, or outside the title for a rename.
  useEffect(() => {
    if (!open || open.mode === "delete") return;
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (open.mode === "rename") {
        if (!header.current?.querySelector(".spe-header-rename")?.contains(target)) end();
        return;
      }
      if (popover.current?.contains(target) || trigger.current?.contains(target)) return;
      end();
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  });

  // Escape: the tag suggestions first, then the menu or editor.
  useEffect(() => {
    if (!open || open.mode === "rename" || open.mode === "delete") return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing) return;
      e.preventDefault();
      if (open.mode === "tags" && suggestions.length > 0) setOpen({ ...open, suggest: false });
      else end(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  if (session === undefined) {
    return <header className="spe-header" />; // which session is open is not yet known
  }
  if (session === null) {
    return (
      <header className="spe-header">
        <h1 className="spe-header-title">New chat</h1>
      </header>
    );
  }

  const toggleMenu = (e: MouseEvent) => {
    if (open?.mode === "rename") return; // `⋯` is aria-disabled while renaming
    if (open?.mode === "menu" || open?.mode === "tags") end();
    else setOpen({ mode: "menu", keyboard: e.detail === 0 });
  };
  const startRename = () => setOpen({ mode: "rename", draft: session.title });
  const choose = (patch: MetaPatch) => {
    end(true);
    void save(patch);
  };
  const setTags = (change: (m: Extract<Mode, { mode: "tags" }>) => Mode) =>
    setOpen((m) => (m && m.mode === "tags" ? change(m) : m));
  // As the sidebar's tag editor: it stays open for the next tag; an add that fails keeps its text
  // and shows why; a removal (`typed` null) leaves the input as it is.
  const tagPatch = async (patch: MetaPatch | null, typed: string | null) => {
    const done = (m: Extract<Mode, { mode: "tags" }>): Mode =>
      typed === null ? { ...m, error: null } : { ...m, draft: "", suggest: false, error: null };
    if (!patch) {
      setTags(done); // already there
      return;
    }
    try {
      await onPatch(patch);
      setTags(done);
    } catch (e) {
      setTags((m) => ({ ...m, draft: typed ?? m.draft, suggest: false, error: errorText(e, "Saving the tag failed.") }));
    }
  };

  const menuOpen = open?.mode === "menu" || open?.mode === "tags";
  return (
    <header className="spe-header" ref={header}>
      {open?.mode === "rename" ? (
        <RenameInput
          label="Chat title"
          className="spe-header-rename"
          value={open.draft}
          onChange={(draft) => setOpen({ ...open, draft })}
          onSave={() => end(true)}
          onCancel={() => { setOpen(null); trigger.current?.focus(); }}
        />
      ) : (
        <h1 className="spe-header-title" title={session.title} onDoubleClick={startRename}>{session.title}</h1>
      )}
      <button
        type="button"
        className="spe-icon-button spe-header-menu"
        ref={trigger}
        aria-label="Chat actions"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        // Not `disabled`: a disabled button cannot take the focus that ending a rename returns to it
        // (React applies `setOpen(null)` after the handler's `focus()`), as slice 2's rows do.
        aria-disabled={open?.mode === "rename" || undefined}
        tabIndex={open?.mode === "rename" ? -1 : undefined}
        onClick={toggleMenu}
      ><Ellipsis /></button>

      {open?.mode === "menu" && (
        <Popover anchor={trigger.current ?? undefined} box={popover} key="menu">
          <RowMenu
            session={session}
            keyboard={open.keyboard}
            onRename={startRename}
            onPin={() => choose({ pinned: !session.pinned })}
            onTags={() => setOpen({ mode: "tags", draft: "", suggest: false, error: null })}
            onHide={() => choose({ hidden: !session.hidden })}
            onDelete={() => setOpen({ mode: "delete" })}
            deleteDisabled={running}
          />
        </Popover>
      )}
      {open?.mode === "tags" && (
        <Popover anchor={trigger.current ?? undefined} box={popover} key="tags">
          <TagEditor
            tags={session.tags}
            draft={open.draft}
            suggestions={suggestions}
            error={open.error}
            onDraft={(draft) => setOpen({ ...open, draft, suggest: true, error: null })}
            onAdd={(text) => { if (text.trim()) void tagPatch(withTag(session.tags, text), text); }}
            onRemove={(tag) => {
              popover.current?.querySelector<HTMLInputElement>(".spe-tag-input")?.focus();
              void tagPatch(withoutTag(session.tags, tag), null);
            }}
          />
        </Popover>
      )}
      {open?.mode === "delete" && (
        <DeleteDialog
          onCancel={() => { setOpen(null); trigger.current?.focus(); }}
          onDelete={() => { setOpen(null); onDelete(); }}
        />
      )}
    </header>
  );
}
```

- [ ] **Step 7: Wire them in.** Apply to `CHAT/app/page.tsx` (the hook and the header in; slice 2's run-end effect
  out; the header's PATCH and DELETE on the open session; run errors passed to the hook):

```diff
diff --git a/platform/agui/copilotkit-chat/app/page.tsx b/platform/agui/copilotkit-chat/app/page.tsx
index 14e3cef..0e1733d 100644
--- a/platform/agui/copilotkit-chat/app/page.tsx
+++ b/platform/agui/copilotkit-chat/app/page.tsx
@@ -12,11 +12,13 @@ import {
   useDefaultRenderTool,
 } from "@copilotkit/react-core/v2";
 import { useCallback, useEffect, useRef, useState } from "react";
-import { fetchSession, fetchSessions } from "../lib/client.ts";
+import { fetchSession, fetchSessions, removeSession, updateSession } from "../lib/client.ts";
 import { searchWith, sessionFromSearch } from "../lib/session-url.ts";
-import type { SessionMeta } from "../lib/sessions.ts";
+import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
+import { ChatHeader } from "./chat-header";
 import { ChevronRight } from "./icons";
 import { Sidebar } from "./sidebar";
+import { useRunReconcile } from "./use-run-reconcile";
 
 const MAX_RESULT_LINES = 40;
 const MAX_RESULT_CHARS = 4000;
@@ -102,6 +104,15 @@ function Chat() {
   const { agent, isReady } = useAgent({ agentId: "spe" });
   useDefaultRenderTool({ render: (props) => <ToolCard {...props} /> });
 
+  // After each run (finished, failed or stopped) the list, fetched until it shows that run; once the
+  // open session is in it (its first run recorded), the URL names it.
+  const onList = useCallback((list: SessionMeta[]) => {
+    setSessions(list);
+    const id = activeRef.current;
+    if (id && list.some((s) => s.id === id)) showInUrl(id);
+  }, []);
+  const { busy, noteRunError } = useRunReconcile({ openId: active ?? "", onList, onError: setError });
+
   // The history goes onto the agent first, then CopilotChat remounts on the new thread
   // (key={id}): a freshly mounted chat on a non-explicit thread keeps the agent's messages,
   // and makes no connect request that would clear them (README, Sessions).
@@ -160,43 +171,55 @@ function Chat() {
     else startNew(); // no parameter, or a malformed one: dropped
   }, [isReady, open, refresh, startNew]);
 
-  // After each run (finished, failed or stopped) the list again; once the open session is in
-  // it (its first run recorded), the URL names it.
-  useEffect(() => {
-    if (!isReady) return;
-    const ended = () => {
-      void refresh().then((list) => {
-        const id = activeRef.current;
-        if (list && id && list.some((s) => s.id === id)) showInUrl(id);
-      });
-    };
-    const subscription = agent.subscribe({ onRunFinalized: ended, onRunFailed: ended });
-    return () => subscription.unsubscribe();
-  }, [agent, isReady, refresh]);
-
   const onDeleted = useCallback((id: string) => {
     if (id === activeRef.current) startNew();
     void refresh();
   }, [refresh, startNew]);
 
+  // The header's menu: the same PATCH and DELETE as the row's, on the open session.
+  const patchOpen = useCallback(async (patch: MetaPatch) => {
+    const id = activeRef.current;
+    if (id === null) return;
+    await updateSession(id, patch);
+    await refresh();
+  }, [refresh]);
+  const deleteOpen = useCallback(async () => {
+    const id = activeRef.current;
+    if (id === null) return;
+    try {
+      await removeSession(id);
+      onDeleted(id);
+    } catch (e) {
+      setError(messageOf(e));
+    }
+  }, [onDeleted]);
+  const knownTags = [...new Set(sessions.flatMap((s) => s.tags))].sort();
+
   return (
     <div className="spe-layout">
       <Sidebar
         sessions={sessions}
-        knownTags={[...new Set(sessions.flatMap((s) => s.tags))].sort()}
+        knownTags={knownTags}
         activeId={active}
         // Switching sessions mid-run would put the new session's history on the agent that is
         // still streaming the old one's run, so both are ignored until the run ends.
         onNew={() => { if (!agent.isRunning) startNew(); }}
         onOpen={(id) => { if (!agent.isRunning) void open(id); }}
         onChanged={refresh}
         onDeleted={onDeleted}
         onError={setError}
+        running={busy}
       />
       <div className="spe-page">
-        <header className="spe-header">
-          <h1 className="spe-header-title">{sessions.find((s) => s.id === active)?.title ?? "New chat"}</h1>
-        </header>
+        <ChatHeader
+          key={active ?? "none"}
+          session={active === null ? undefined : (sessions.find((s) => s.id === active) ?? null)}
+          knownTags={knownTags}
+          running={busy}
+          onPatch={patchOpen}
+          onDelete={() => void deleteOpen()}
+          onError={setError}
+        />
         {error && (
           <div className="spe-error" role="alert">
             <span className="spe-error-text">{error}</span>
@@ -213,7 +236,10 @@ function Chat() {
               className="spe-chat"
               onError={(event) => {
                 // The prop's type also admits a DOM error event; only CopilotKit's carries `error`.
-                if ("error" in event && event.error instanceof Error) setError(event.error.message || "The agent run failed.");
+                if ("error" in event && event.error instanceof Error) {
+                  noteRunError(event.error.message);
+                  setError(event.error.message || "The agent run failed.");
+                }
               }}
             />
           </CopilotChatConfigurationProvider>
```

and to `CHAT/app/sidebar.tsx` (task 1's file, after step 6's cut; `running` disables *New chat* in both the open
and the collapsed sidebar, every row's open button and the open row's *Delete*):

```diff
diff --git a/platform/agui/copilotkit-chat/app/sidebar.tsx b/platform/agui/copilotkit-chat/app/sidebar.tsx
index 2f1fa35..df25c2b 100644
--- a/platform/agui/copilotkit-chat/app/sidebar.tsx
+++ b/platform/agui/copilotkit-chat/app/sidebar.tsx
@@ -9,16 +9,15 @@
 // closes on a press outside it, Escape or a choice, and gives focus back to its ⋯; a rename is saved
 // by Enter or a press outside the row and cancelled by Escape; a tag typed but not added is dropped.
 import { useEffect, useRef, useState } from "react";
-import type { KeyboardEvent, MouseEvent } from "react";
+import type { MouseEvent } from "react";
 import { removeSession, renamePatch, tagSuggestions, updateSession, withTag, withoutTag } from "../lib/client.ts";
-import { menuIndex } from "../lib/menu.ts";
 import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";
 import { filterSessions, sections } from "../lib/sidebar-view.ts";
 import type { ViewFilter } from "../lib/sidebar-view.ts";
 import { DeleteDialog } from "./delete-dialog";
-import { Ellipsis, Eye, EyeSlash, PencilSquare, Pencil, Pin, PinSlash, SidebarToggle, Tag, Trash } from "./icons";
-import { composing } from "./keys.ts";
+import { Ellipsis, PencilSquare, SidebarToggle } from "./icons";
 import { Popover } from "./popover";
+import { RenameInput, RowMenu } from "./row-menu";
 import { HiddenToggle, SearchBox } from "./session-filters";
 import { TagEditor } from "./tag-editor";
 
@@ -31,6 +30,8 @@ type SidebarProps = {
   onChanged: () => Promise<unknown>; // resolves once the list is fetched again
   onDeleted: (id: string) => void;
   onError: (message: string) => void;
+  /** A run is in progress: switching session, New chat and the open session's Delete are disabled. */
+  running: boolean;
 };
 
 // What the one busy row is doing. `keyboard`: the menu was opened from the keyboard, so its first
@@ -44,7 +45,7 @@ type Busy =
 const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);
 
 
-export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError }: SidebarProps) {
+export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError, running }: SidebarProps) {
   const [busy, setBusy] = useState<Busy | null>(null);
   const [collapsed, setCollapsed] = useState(false);
   const triggers = useRef(new Map<string, HTMLButtonElement>());
@@ -182,7 +183,7 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
         <button type="button" className="spe-icon-button" aria-label="Show sessions" title="Show sessions"
           onClick={() => setCollapsed(false)}><SidebarToggle /></button>
         <button type="button" className="spe-icon-button" aria-label="New chat" title="New chat"
-          onClick={newChat}><PencilSquare /></button>
+          disabled={running} onClick={newChat}><PencilSquare /></button>
       </nav>
     );
   }
@@ -206,7 +207,7 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
           />
         ) : (
           <button type="button" className="spe-row-open" aria-current={s.id === activeId ? "page" : undefined}
-            onClick={() => { end(); onOpen(s.id); }} onDoubleClick={() => startRename(s)}>
+            disabled={running} onClick={() => { end(); onOpen(s.id); }} onDoubleClick={() => startRename(s)}>
             {/* The Pinned section shows it; this tells a screen reader too. */}
             {s.pinned && <span className="spe-pin spe-sr-only">Pinned: </span>}
             <span className="spe-row-title">{s.title}</span>
@@ -234,7 +235,7 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
           onClick={() => { end(); setCollapsed(true); }}><SidebarToggle /></button>
       </div>
       <div className="spe-sidebar-actions">
-        <button type="button" className="spe-new" onClick={newChat}><PencilSquare />New chat</button>
+        <button type="button" className="spe-new" disabled={running} onClick={newChat}><PencilSquare />New chat</button>
         <SearchBox query={filter.query} knownTags={knownTags} onChange={(query) => setFilter({ ...filter, query })} />
       </div>
       <div className="spe-sidebar-list">
@@ -261,6 +262,7 @@ export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChange
             onTags={() => setBusy({ id: busySession.id, mode: "tags", draft: "", suggest: false, error: null })}
             onHide={() => choose(busySession, { hidden: !busySession.hidden })}
             onDelete={() => setBusy({ id: busySession.id, mode: "delete" })}
+            deleteDisabled={running && busySession.id === activeId}
           />
         </Popover>
       )}
```

and to `CHAT/app/globals.css` (the header's focus ring, its rename input and `⋯`, the disabled controls; tokens
only, light and dark; slice 2's `.spe-header` and `.spe-header-title` rules gain the new properties in place,
rather than a second rule under the same selector):

```diff
diff --git a/platform/agui/copilotkit-chat/app/globals.css b/platform/agui/copilotkit-chat/app/globals.css
index fb266e3..ad8a85b 100644
--- a/platform/agui/copilotkit-chat/app/globals.css
+++ b/platform/agui/copilotkit-chat/app/globals.css
@@ -159,7 +159,7 @@ body {
 .spe-icon { width: 16px; height: 16px; flex: none; }
 
 /* Visible keyboard focus on our own controls (CopilotKit's carry their own). */
-:where(.spe-sidebar, .spe-popover, .spe-dialog, .spe-error, .spe-tool) :is(button, summary, input):focus-visible {
+:where(.spe-sidebar, .spe-header, .spe-popover, .spe-dialog, .spe-error, .spe-tool) :is(button, summary, input):focus-visible {
   outline: 2px solid var(--focus-ring); outline-offset: 2px;
 }
 
@@ -169,12 +169,21 @@ body {
 /* ---------- Header: the open session's title, nothing else ---------- */
 
-.spe-header { position: relative; z-index: 10; flex: none; display: flex; align-items: center; height: 48px;
-  padding: 0 20px; background: var(--bg); }
+/* Renamable in place (double-click or the menu's Rename), with the rows' ⋯ menu beside it. */
+.spe-header { position: relative; z-index: 10; flex: none; display: flex; align-items: center; gap: 4px;
+  height: 48px; padding: 0 20px; background: var(--bg); }
 /* A soft fade under it, over the chat's top edge, instead of a rule. */
 .spe-header::after { content: ""; position: absolute; left: 0; right: 0; top: 100%; height: 16px;
   background: linear-gradient(var(--bg), transparent); pointer-events: none; }
-.spe-header-title { margin: 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
-  font-size: 15px; line-height: 20px; font-weight: 500; color: var(--text-secondary); }
+.spe-header-title { margin: 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
+  font-size: 15px; line-height: 20px; font-weight: 500; color: var(--text-secondary); cursor: default; }
+.spe-header-rename { flex: 0 1 480px; min-width: 0; height: 32px; box-sizing: border-box; margin: 0 0 0 -8px;
+  padding: 6px 8px; border: 0; border-radius: var(--radius-item); background: none; color: var(--text);
+  font: inherit; font-size: 15px; line-height: 20px; font-weight: 500; outline: none;
+  box-shadow: inset 0 0 0 1px var(--line-strong); }
+.spe-header-rename:focus-visible { outline: none; box-shadow: inset 0 0 0 1.5px var(--focus-ring); }
+.spe-header-menu .spe-icon { width: 18px; height: 18px; }
+.spe-header-menu[aria-expanded="true"] { background: var(--hover); color: var(--text); }
+.spe-header-menu[aria-disabled="true"] { opacity: 0.4; cursor: default; background: none; } /* while renaming */
 
 .spe-chat { flex: 1; min-height: 0; }
 .spe-loading { padding: 16px 20px; color: var(--text-muted); font-size: 13px; }
@@ -266,6 +277,12 @@ body {
   color: var(--text-muted); cursor: pointer; }
 .spe-hidden-toggle input { margin: 0; accent-color: var(--button-strong-bg); }
 
+/* During a run: New chat, the rows and the open session's Delete are disabled. */
+.spe-new:disabled, .spe-icon-button:disabled, .spe-row-open:disabled, .spe-menu > button:disabled {
+  cursor: not-allowed; color: var(--button-off-text); }
+.spe-new:disabled:hover, .spe-icon-button:disabled:hover, .spe-menu > button:disabled:hover { background: none; }
+.spe-row-active .spe-row-open:disabled { color: inherit; }
+
 /* ---------- Row popover: menu and tag editor ---------- */
 
 /* Floats over the list (fixed, placed by the sidebar under or above its ⋯). */
```

- [ ] **Step 8: Run the suites**

Run: `(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)`
Expected: all pass; the build type-checks `page.tsx` with the hook. `grep -n "onRunFailed" platform/agui/copilotkit-chat/app/page.tsx`
prints nothing (slice 2's effect is gone).

- [ ] **Step 9: Add the browser checks** to `platform/dev/e2e/sessions.py`.

1. In the imports, after `import uuid`, add `from datetime import datetime, timedelta, timezone`.
2. In the module docstring, after the usage line, add:
   `    python3 platform/dev/e2e/sessions.py --scenario stop --save-delay-ms 1500` and
   `    python3 platform/dev/e2e/sessions.py --url http://127.0.0.1:3000 --compose-file F --scenario stop|slow-loop|two-turn`.
3. Insert before `def main()`:

```python
# --- search with tag: terms, date groups, Show hidden, header, a stopped run, a failed save --

SAVE_FAILED = "this session could not be saved"


def iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def seed(r: Run, title: str, days_ago: float, **extra) -> str:
    """A session file written directly (local run only): old timestamps cannot come from a run."""
    sid = str(uuid.uuid4())
    when = iso_days_ago(days_ago)
    record = {"version": 1, "id": sid, "title": title, "title_source": "user", "tags": [], "pinned": False,
              "hidden": False, "created_at": when, "updated_at": when, "deleted_at": None,
              "messages": [], "runs": [], **extra}
    (r.sessions / f"{sid}.json").write_text(json.dumps(record))
    return sid


def groups(r: Run) -> list[str]:
    return r.page.locator(".spe-sidebar .spe-group").evaluate_all("els => els.map(e => e.dataset.group)")


def check_view(r: Run) -> None:
    """After check_close_tab: one pinned session updated today, one hidden, one deleted."""
    page = r.page
    seed(r, "Seeded yesterday", 1, tags=["alpha", "beta"])
    seed(r, "Seeded five days ago", 5, tags=["beta"])
    seed(r, "Seeded long ago", 40)
    seed(r, XSS, 41)
    page.goto(BASE + "/")
    expect(r.row("Seeded long ago")).to_have_count(1, timeout=10_000)
    assert groups(r) == ["Pinned", "Yesterday", "Previous 7 days", "Older"], groups(r)
    r.shot("groups")
    r.ok("groups: Pinned, then Yesterday, Previous 7 days, Older (no unpinned session today)")

    search = page.get_by_label("Search titles")
    search.fill("  SEEDED ")
    expect(r.rows()).to_have_count(3)
    search.fill("five")
    expect(r.rows()).to_have_count(1)
    expect(r.row("Seeded five days ago")).to_have_count(1)
    search.fill("<img")
    expect(r.rows()).to_have_count(1)
    assert page.evaluate("window.__speXss") is None
    r.shot("search")
    search.fill("")
    expect(r.rows()).to_have_count(5)
    r.ok("search: case-insensitive title substring; HTML in a title is text")

    options = page.locator(".spe-search-suggestions [role=option]")
    search.fill("tag:")
    expect(options).to_have_text(["tag:alpha", "tag:beta", "tag:dns", "tag:exfil"])
    search.fill("tag:b")
    expect(options).to_have_text(["tag:beta"])
    search.press("ArrowDown")
    search.press("Enter")
    expect(search).to_have_value("tag:beta ")
    expect(options).to_have_count(0)
    expect(r.rows()).to_have_count(2)
    search.press_sequentially("tag:")
    expect(options).to_have_text(["tag:alpha", "tag:dns", "tag:exfil"])  # beta is named already
    options.first.click()
    expect(search).to_have_value("tag:beta tag:alpha ")
    expect(r.rows()).to_have_count(1)
    expect(r.row("Seeded yesterday")).to_have_count(1)
    expect(r.rows().locator(".spe-chip")).to_have_count(0)  # rows show the title only
    r.shot("tag-search")
    search.fill("tag:beta five")
    expect(r.rows()).to_have_count(1)
    expect(r.row("Seeded five days ago")).to_have_count(1)
    search.fill("tag:al")
    expect(options).to_have_count(1)
    search.press("Escape")
    expect(options).to_have_count(0)
    expect(search).to_have_value("tag:al")
    search.fill("tag:nosuch")
    expect(r.rows()).to_have_count(0)
    expect(page.locator(".spe-empty")).to_have_text("No session matches.")
    search.fill("")
    expect(r.rows()).to_have_count(5)
    r.ok("tag: search: typing tag: suggests the tags in use (arrows and Enter, or a click); two tag: terms must "
         "both match; the rest filters titles; rows show no tags")

    expect(r.row("Read the dataset")).to_have_count(0)
    expect(page.get_by_text("Deleted sessions are kept in the run archive.")).to_be_visible()
    page.get_by_label("Show hidden").check()
    expect(r.row("Read the dataset")).to_have_count(1)
    expect(r.row("Read the dataset")).to_have_class("spe-row spe-row-hidden")
    r.shot("show-hidden")
    page.get_by_label("Show hidden").uncheck()
    expect(r.row("Read the dataset")).to_have_count(0)
    r.ok("Show hidden: the hidden session appears only with the toggle; the deleted one never")


def check_header(r: Run, ids: dict[str, str]) -> None:
    """The header: the title row, renamable in place, and the rows' ⋯ menu; tags only in its tag editor."""
    page = r.page
    title = "List the home directory (exfil try)"
    page.goto(f"{BASE}/?session={ids['first']}")
    header = page.locator(".spe-header")
    expect(header.locator(".spe-header-title")).to_have_text(title, timeout=10_000)
    expect(header).not_to_contain_text("tool call")  # the note is the line under the composer
    actions = header.get_by_role("button", name="Chat actions")
    actions.click()
    page.get_by_role("menuitem", name="Rename").click()
    page.get_by_label("Chat title").fill("Renamed in the header")
    page.get_by_label("Chat title").press("Enter")
    expect(header.locator(".spe-header-title")).to_have_text("Renamed in the header", timeout=5_000)
    expect(r.row("Renamed in the header")).to_have_count(1, timeout=5_000)
    expect(actions).to_be_focused()
    header.locator(".spe-header-title").dblclick()
    page.get_by_label("Chat title").fill("Discarded title")
    page.get_by_label("Chat title").press("Escape")
    expect(header.locator(".spe-header-title")).to_have_text("Renamed in the header")

    actions.click()
    page.get_by_role("menuitem", name="Tags").click()
    page.get_by_label("Add a tag").fill("Header")
    page.get_by_label("Add a tag").press("Enter")
    expect(page.locator(".spe-popover .spe-chip", has_text="header")).to_have_count(1, timeout=5_000)
    page.get_by_role("button", name="Remove tag exfil").click()
    expect(page.locator(".spe-popover .spe-chip")).to_have_count(2, timeout=5_000)
    r.shot("header-tags")
    page.get_by_label("Add a tag").press("Escape")
    expect(page.locator(".spe-popover")).to_have_count(0)
    expect(header.locator(".spe-chip")).to_have_count(0)  # the header shows no tags
    rec = r.files()[ids["first"]]
    assert rec["title"] == "Renamed in the header" and rec["title_source"] == "user", rec["title"]
    assert rec["tags"] == ["dns", "header"], rec["tags"]
    r.shot("header")

    actions.click()
    page.get_by_role("menuitem", name="Delete").click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_contain_text("Delete chat?")
    # The dialog renders inside the header, whose z-index: 10 puts it above the chat below;
    # this shot shows the dialog's backdrop covering the chat, not hidden behind it.
    r.shot("header-delete")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(r.row("Renamed in the header")).to_have_count(1)
    assert r.files()[ids["first"]]["deleted_at"] is None

    page.reload()
    expect(header.locator(".spe-header-title")).to_have_text("Renamed in the header", timeout=10_000)
    expect(page.locator(".spe-tool")).to_have_count(2)
    assert r.url_session() == ids["first"]
    page.get_by_role("button", name="New chat").click()
    expect(header.locator(".spe-header-title")).to_have_text("New chat")
    expect(header.get_by_role("button", name="Chat actions")).to_have_count(0)
    r.ok("header: rename by its menu (Enter saves) and double-click (Esc cancels), tags in the menu's tag editor, "
         "Delete opens the same dialog above the chat (Escape cancels, keeps the file); saved to the file; "
         "reload reopens it with its tool cards; New chat has no menu")


def check_stop(r: Run) -> str:
    """A slow run (fake agent: "slow" in the message) stopped from the chat: controls disabled during
    it, enabled after; the row appears, also with the save delayed (the recorder saves before the
    stop's RUN_ERROR reaches the browser); the file ends with a `cancelled` run. Returns the session id."""
    page = r.page
    title = f"slow run to stop {uuid.uuid4().hex[:8]}"
    page.get_by_role("button", name="New chat").click()
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill(title)
    box.press("Enter")
    expect(page.get_by_role("button", name="New chat")).to_be_disabled(timeout=5_000)
    for button in page.locator(".spe-row-open").all():
        expect(button).to_be_disabled()
    r.shot("during-run")
    page.get_by_test_id("copilot-send-button").click()  # the stop button while a run is in progress
    expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=15_000)
    for button in page.locator(".spe-row-open").all():
        expect(button).to_be_enabled()
    expect(r.row(title)).to_have_count(1, timeout=5_000)
    assert SAVE_FAILED not in "".join(page.locator(".spe-error").all_inner_texts())
    r.shot("after-stop")
    until = time.time() + 15
    while time.time() < until:
        found = [(sid, f) for sid, f in r.files().items() if f["title"] == title]
        if found and found[0][1]["runs"]:
            sid, rec = found[0]
            assert rec["runs"][-1]["status"] == "cancelled", rec["runs"]
            r.ok("stopped run: controls disabled then enabled, recorded cancelled (row shown)")
            return sid
        time.sleep(0.5)
    sys.exit(f"FAIL: no session file titled {title!r} with a run")


def check_save_failed(r: Run) -> None:
    """The chat UI cannot write the session (its directory made read-only for the run): the
    server's save-failed event puts the error bar up, and the list is not fetched again and again
    (a retrying reconciliation would fetch it 6 times). Local run only, as a normal user."""
    if os.geteuid() == 0:
        sys.exit("FAIL: check_save_failed needs a normal user (root writes to a read-only directory)")
    page = r.page
    lists: list[str] = []
    page.on("request", lambda req: lists.append(req.url)
            if req.method == "GET" and req.url.split("?")[0].endswith("/api/sessions") else None)
    page.get_by_role("button", name="New chat").click()
    expect(page.locator(".spe-header-title")).to_have_text("New chat")
    title = f"run that cannot be saved {uuid.uuid4().hex[:8]}"
    mode = r.sessions.stat().st_mode & 0o7777
    r.sessions.chmod(0o500)
    try:
        lists.clear()
        r.send(title, 1)
        expect(page.locator(".spe-error")).to_contain_text(SAVE_FAILED, timeout=5_000)
        expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=5_000)
        time.sleep(3.5)  # longer than five retries 500 ms apart
        assert len(lists) <= 2, lists  # the one fetch after the run, and at most one from New chat
    finally:
        r.sessions.chmod(mode)
    assert not any(f["title"] == title for f in r.files().values())
    r.shot("save-failed")
    r.ok("failed save: the server's event shows the error bar; the list is fetched once, not retried")


def slow_loop(r: Run) -> None:
    """Archive check during a run: slow runs back to back, each in a new session (a second run of
    one thread right after the first can be refused while the server finishes it), until the chat
    UI goes away under the archive's barrier or 12 runs have passed. Prints each run's title; the
    last one printed is the run the barrier stopped."""
    page = r.page
    stamp = uuid.uuid4().hex[:8]
    page.goto(BASE + "/")
    for n in range(1, 13):
        title = f"slow run {stamp}-{n}"
        try:
            page.get_by_role("button", name="New chat").click(timeout=10_000)
            box = page.get_by_test_id("copilot-chat-textarea")
            box.fill(title)
            box.press("Enter")
            print(f"title {title}", flush=True)
            expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=60_000)
        except Exception as e:  # the chat UI went away under the barrier
            print(f"stopped at {title}: {type(e).__name__}", flush=True)
            return
        if page.locator(".spe-error").count():
            print(f"stopped at {title}: {page.locator('.spe-error').inner_text()}", flush=True)
            return


def two_turn(r: Run) -> None:
    """The paid check: two turns with the instance's real model; both runs recorded completed."""
    page = r.page
    page.goto(BASE + "/")
    page.get_by_role("button", name="New chat").click()
    first = "Run pwd and tell me the result in one sentence."
    for text in (first, "Now list the files in that directory, briefly."):
        box = page.get_by_test_id("copilot-chat-textarea")
        box.fill(text)
        box.press("Enter")
        expect(page.get_by_role("button", name="New chat")).to_be_disabled(timeout=10_000)
        expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=120_000)
    expect(r.row(first)).to_have_count(1, timeout=10_000)
    r.shot("two-turn")
    rec = next(f for f in r.files().values() if f["title"] == first)
    assert [x["status"] for x in rec["runs"]] == ["completed", "completed"], rec["runs"]
    r.ok(f"two turns with the real model, both completed (session {rec['id']})")


class InstanceRun(Run):
    """Against an instance's chat UI: the session files are read in the chat-ui container."""

    def __init__(self, page: Page, compose_file: str, shots: Path | None):
        super().__init__(page, Path("/nonexistent"), shots)
        self.compose_file = compose_file

    def files(self) -> dict[str, dict]:
        script = ("const fs=require('fs');const d='/data/sessions';const o={};"
                  "for(const f of fs.readdirSync(d))if(f.endsWith('.json'))"
                  "o[f.slice(0,-5)]=JSON.parse(fs.readFileSync(d+'/'+f,'utf8'));"
                  "process.stdout.write(JSON.stringify(o))")
        out = subprocess.run(["docker", "compose", "-p", "spe-frontend", "-f", self.compose_file, "exec", "-T",
                              "chat-ui", "node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(out.stdout)
```

4. Replace `def main()` (the whole function) with:

```python
LOCAL = ("all", "stop")
INSTANCE = ("stop", "slow-loop", "two-turn")


def main() -> None:
    global BASE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", type=Path, help="write numbered screenshots here")
    ap.add_argument("--sessions", type=Path, help="sessions directory to use and keep (default: a temporary one)")
    ap.add_argument("--scenario", default="all", choices=sorted(set(LOCAL + INSTANCE)),
                    help="all: every check (save-failed last); stop: a stopped run whose save is delayed "
                         "(--save-delay-ms); slow-loop, two-turn: --url only")
    ap.add_argument("--save-delay-ms", type=int, default=0,
                    help="SPE_SESSIONS_TEST_SAVE_DELAY_MS for the local chat UI")
    ap.add_argument("--url", help="an instance's chat UI (e.g. http://127.0.0.1:3000) instead of local servers")
    ap.add_argument("--compose-file", help="with --url: the instance's frontend docker-compose.yml")
    args = ap.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    if args.url:
        if args.scenario not in INSTANCE or not args.compose_file:
            sys.exit(f"FAIL: --url takes --compose-file and a scenario of {INSTANCE}")
        BASE = args.url.rstrip("/")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            r = InstanceRun(page, args.compose_file, args.shots)
            if args.scenario == "stop":
                page.goto(BASE + "/")
                print(f"session {check_stop(r)}")
            elif args.scenario == "slow-loop":
                slow_loop(r)
            else:
                two_turn(r)
            browser.close()
        return
    if args.scenario not in LOCAL:
        sys.exit(f"FAIL: {args.scenario} needs --url")
    standalone = APP / ".next" / "standalone"
    if not (standalone / "server.js").exists():
        sys.exit("FAIL: run `npm ci && npm run build` in platform/agui/copilotkit-chat first")
    shutil.copytree(APP / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    data = args.sessions or Path(tempfile.mkdtemp(prefix="spe-e2e-")) / "sessions"
    data.mkdir(parents=True, exist_ok=True)
    procs = [subprocess.Popen(["uv", "run", "--group", "dev", "python", "../../dev/fake_agent.py",
                               "--port", str(AGENT_PORT), "--key", KEY], cwd=AGENT_DIR)]
    try:
        wait_http(f"http://127.0.0.1:{AGENT_PORT}/healthz", "the fake agent")
        env = {**os.environ, "AGENT_URL": f"http://127.0.0.1:{AGENT_PORT}/agent", "AGENT_API_KEY": KEY,
               "PORT": str(UI_PORT), "HOSTNAME": "127.0.0.1", "SPE_SESSIONS_DIR": str(data),
               "NEXT_MANUAL_SIG_HANDLE": "true", "SPE_SESSIONS_TEST_SAVE_DELAY_MS": str(args.save_delay_ms)}
        procs.append(subprocess.Popen(["node", "server.js"], cwd=standalone, env=env))
        wait_http(BASE + "/api/sessions", "the chat UI")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            r = Run(page, data, args.shots)
            if args.scenario == "all":
                ids = check_list(r)
                check_focus(r, ids)
                check_menu(r, ids)
                check_close_tab(r, ids)
                check_view(r)
                check_header(r, ids)
                check_stop(r)
                check_save_failed(r)
            else:
                page.goto(BASE + "/")
                check_stop(r)
            browser.close()
        print(f"sessions: {data}")
    finally:
        for proc in reversed(procs):
            proc.terminate()
            proc.wait(timeout=35)
```

- [ ] **Step 10: Run the full browser run** (no model call: `fake_agent.py`)

```bash
E=docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-3; mkdir -p $E
(cd platform/agui/copilotkit-chat && npm ci && npm run build)
python3 platform/dev/e2e/sessions.py --shots $E
python3 platform/dev/e2e/sessions.py --scenario stop --save-delay-ms 1500
```

Expected: the first run prints slice 2's `ok - …` lines, then `ok - groups: …`, `ok - search: …`, `ok - tag:
search: …`, `ok - Show hidden: …`, `ok - header: …`, `ok - stopped run: … (row shown)`, `ok - failed save: …`; the second `ok - stopped
run: … (row shown)`: the browser's run ends only after the delayed save (the recorder saves before the stop's
`RUN_ERROR` is passed on, spec clarification 1), so the first fetch finds it. A stop therefore never reaches the
error bar after the retries; that path (a save landing late after an unsubscription) is covered by
`reconcile.test.ts` only. Look at every screenshot in `$E` (Read tool): `groups`, `search`, `tag-search`,
`show-hidden`, `header-tags`, `header`, `during-run`, `after-stop`, `save-failed`, beside slice 2's.

- [ ] **Step 11: Docs.** In `CHAT/README.md`, *Sessions* (slice 2's section), add after its sidebar sentence:

```markdown
The sidebar's search filters by title (case-insensitive) and, as in Open WebUI, by `tag:<name>` terms (a
session must have every one; typing `tag:` suggests the tags in use), lists pinned sessions first and then
*Today*, *Yesterday*, *Previous 7 days* and *Older* by last change, and shows hidden sessions only with *Show
hidden*. The chat header shows the open session's title, renamable in place, and the same `⋯` menu as its row. While a run is in progress, switching session and *New chat* are disabled; after a run the list is
fetched until it shows that run (up to 5 retries, 500 ms apart), else the error bar says the session could not
be saved. `platform/dev/e2e/sessions.py` drives all of it in a browser against the scripted agent.
```

Then `grep -rn -i "one-line\|no search\|search.*slice 3\|hidden rows are left out" platform/agui docs/getting-started.md`
and rewrite any current text it finds that this task made stale.

- [ ] **Step 12: Commit**

```bash
git add platform/agui/copilotkit-chat/lib/reconcile.ts platform/agui/copilotkit-chat/lib/reconcile.test.ts \
  platform/agui/copilotkit-chat/app/use-run-reconcile.ts platform/agui/copilotkit-chat/app/row-menu.tsx \
  platform/agui/copilotkit-chat/app/chat-header.tsx \
  platform/agui/copilotkit-chat/app/page.tsx platform/agui/copilotkit-chat/app/sidebar.tsx \
  platform/agui/copilotkit-chat/app/globals.css platform/agui/copilotkit-chat/README.md \
  platform/dev/e2e/sessions.py docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-3
git commit -s -m "Chat UI: header, controls disabled during a run, list reconciled after it

sessions.py covers search with tag: terms, groups, Show hidden, the header's rename and menu, a stopped run and a
save delayed by SPE_SESSIONS_TEST_SAVE_DELAY_MS."
```

### Task 3: instance checks — "Session API answers", `chat-ui`'s hardening, the key scan over the volume

**Files:** Modify: `platform/ansible/roles/agui/tasks/checks.yml`.

**Interfaces:** Consumes: `spe_agui_ui_port`, `spe_agent_api_key`, `spe_frontend_dir` (group vars), the fact
`agui_agent_env` that `checks.yml` already slurps from `agent.env` (`SPE_AGENT_API_KEY`, `SANDBOX_API_KEY`,
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`), the `chat-ui` service with `/data/sessions` (slice 1). Produces: nothing
later tasks call. The checks run in `create.yml` (the `agui` role) and `verify.yml` (the `verify` role already
includes `checks.yml` when `spe_frontend == 'agui'`), so `verify.yml` itself needs no change.

**Decisions:** 1 (`docker inspect` of `chat-ui`: `ReadonlyRootfs: true`, exactly one mount, the volume at `/data`,
and tmpfs exactly `/tmp` and `/app/.next/cache`, as slice 1's compose template sets them), 15 ("Session API
answers": `GET /api/sessions` → 200 and a JSON list), 13 (the key check extended
to the volume as a detector: no file under `/data/sessions` holds the agent, LLM or sandbox key; a hit fails and
names the files, it is never hidden). The answer and the scan's output are `no_log` (titles; the keys go to grep
on stdin, never in argv); the asserts say what was wrong. The scan first asserts all three keys were found,
because grep with an empty pattern list matches nothing and would pass.

The dev-VM commands of tasks 3–5 use (slice 2's task 5, ruling 5: the branch's roles run from the worktree, the
instance file and output stay in the main checkout):

```bash
M=/workspace/biohackathon/biohackathon/elixir-biohackathon-2026-test; W=$(git rev-parse --show-toplevel)
F=/home/ubuntu/spe-frontend/docker-compose.yml
create() { (cd $M/platform/ansible && ansible-playbook playbooks/create.yml -e @instances/dev-local.yml \
  -e spe_agui_source_dir=$W/platform/agui </dev/null); }
play() { (cd $W/platform/ansible && ansible-playbook playbooks/$1.yml -e @$M/platform/ansible/instances/dev-local.yml \
  -e spe_output_root=$M/platform/ansible/output </dev/null); }
latest() { ls -d /data-share/runs/*_dev-local | tail -1; }
git -C $M status --short && git -C $M log --oneline -1     # clean, on main, slice 2 merged
```

- [ ] **Step 1: See the checks missing**

Run: `grep -c "Session API answers\|No session file holds\|chat-ui keeps a read-only root" platform/ansible/roles/agui/tasks/checks.yml`
Expected: `0`.

- [ ] **Step 2: Add "Session API answers"** to `checks.yml`, right after the task "Chat UI answers":

```yaml
- name: Session API answers
  # GET /api/sessions must give 200 and a JSON list. The answer holds participants' titles
  # and tags, so it is not logged; the assertion below says what was wrong.
  ansible.builtin.uri:
    url: "http://127.0.0.1:{{ spe_agui_ui_port }}/api/sessions"
  register: agui_sessions_api
  failed_when: false   # judged below, with a message the censored result could not give
  no_log: true

- name: Session API answered 200 with a JSON list
  ansible.builtin.assert:
    that:
      - agui_sessions_api.status == 200
      - (agui_sessions_api.json | default(none) | type_debug) == 'list'
    fail_msg: >-
      GET /api/sessions answered {{ agui_sessions_api.status }}
      {{ 'with a JSON list' if (agui_sessions_api.json | default(none) | type_debug) == 'list' else 'without a JSON list' }};
      expected 200 and a list
    quiet: true
```

- [ ] **Step 3: Add the key scan** to `checks.yml`, after "The sandbox cannot use the agent without its key" and
  before "Smoke helper":

```yaml
- name: Keys no session file may hold (agent, LLM and sandbox keys)
  ansible.builtin.set_fact:
    agui_session_keys: >-
      {{ ([spe_agent_api_key]
          + ((agui_agent_env.content | b64decode).splitlines()
             | select('match', '^(ANTHROPIC|OPENAI|SANDBOX)_API_KEY=')
             | map('regex_replace', '^[A-Z_]+=', '') | list))
         | map('trim') | reject('equalto', '') | unique | list }}
  no_log: true

- name: All three keys found (grep with no pattern would match nothing and pass)
  ansible.builtin.assert:
    that: agui_session_keys | length == 3
    fail_msg: "expected the agent, LLM and sandbox keys, found {{ agui_session_keys | length }}; see agent.env"
    quiet: true

- name: Session files scanned for the keys
  # A detector: chat-ui never holds the LLM or sandbox key, so a hit means a key
  # reached a conversation through the agent or a tool. Keys go in on stdin, never in argv;
  # grep prints file names only. rc 1: no file holds any key; rc 2: /data/sessions unreadable.
  ansible.builtin.command:
    argv: [docker, compose, -p, spe-frontend, -f, "{{ spe_frontend_dir }}/docker-compose.yml",
           exec, -T, chat-ui, grep, -rlF, -f, -, /data/sessions]
    stdin: "{{ agui_session_keys | join('\n') }}"
  register: agui_session_scan
  changed_when: false
  failed_when: false   # judged below: the censored result would not say why
  no_log: true

- name: Session files could be scanned
  ansible.builtin.assert:
    that: agui_session_scan.rc in [0, 1]
    fail_msg: "could not scan /data/sessions in chat-ui (grep exit {{ agui_session_scan.rc }}); is the chat-sessions volume mounted?"
    quiet: true

- name: No session file holds the agent, LLM or sandbox key
  ansible.builtin.assert:
    that: agui_session_scan.rc == 1
    fail_msg: "a key reached a session file (report it, do not hide it): {{ agui_session_scan.stdout_lines | join(', ') }}"
    quiet: true
```

- [ ] **Step 4: Add the hardening check** to `checks.yml`, right after "Session API answered 200 with a JSON
  list". `docker inspect`'s output holds `chat-ui`'s environment (the agent key), so only the three values are
  kept and shown:

```yaml
- name: chat-ui container
  ansible.builtin.command:
    argv: [docker, compose, -p, spe-frontend, -f, "{{ spe_frontend_dir }}/docker-compose.yml", ps, -q, chat-ui]
  register: agui_ui_container
  changed_when: false
  failed_when: agui_ui_container.rc != 0 or agui_ui_container.stdout_lines | length != 1

- name: chat-ui as Docker runs it
  ansible.builtin.command:
    argv: [docker, inspect, "{{ agui_ui_container.stdout }}"]
  register: agui_ui_inspect
  changed_when: false
  no_log: true   # Config.Env holds the agent key

- name: chat-ui's root filesystem, mounts and tmpfs
  ansible.builtin.set_fact:
    agui_ui_readonly: "{{ (agui_ui_inspect.stdout | from_json | first).HostConfig.ReadonlyRootfs | default(false) }}"
    agui_ui_mounts: >-
      {{ (agui_ui_inspect.stdout | from_json | first).Mounts | default([], true)
         | map(attribute='Type') | zip((agui_ui_inspect.stdout | from_json | first).Mounts | default([], true)
         | map(attribute='Destination')) | map('join', ':') | sort }}
    agui_ui_tmpfs: "{{ ((agui_ui_inspect.stdout | from_json | first).HostConfig.Tmpfs | default({}, true)).keys() | sort }}"

- name: chat-ui keeps a read-only root, one volume at /data and tmpfs only at /tmp and /app/.next/cache
  # The sessions volume is the only writable place that outlives the container; anything
  # else written goes to the two tmpfs. A change to the compose file that loosens this fails here.
  ansible.builtin.assert:
    that:
      - agui_ui_readonly | bool
      - agui_ui_mounts == ['volume:/data']
      - agui_ui_tmpfs == ['/app/.next/cache', '/tmp']
    fail_msg: >-
      chat-ui hardening changed: ReadonlyRootfs {{ agui_ui_readonly }}, mounts {{ agui_ui_mounts }},
      tmpfs {{ agui_ui_tmpfs }}; expected true, ['volume:/data'], ['/app/.next/cache', '/tmp']
    quiet: true
```

- [ ] **Step 5: Check the failure paths locally** (no instance touched), in a scratch directory outside the repo
  (`S=$(mktemp -d /var/tmp/spe-checks-XXXX)`): a compose project `spe-frontend-s3test` with one service `chat-ui`
  (`image: node:24-slim`, `command: ["sleep", "infinity"]`, `user: "1000"`, `read_only: true`, `tmpfs: [/tmp,
  "/app/.next/cache:uid=1000,gid=1000,mode=0700"]`, `volumes: ["chat-sessions:/data"]` with a top-level
  `volumes: {chat-sessions: {}}`; the session files are put there with `docker compose cp`),
  an `agent.env` with three dummy keys, a one-line Python HTTP stub on port 18333 answering `GET` with a given body,
  and a play on `localhost` (`-c local`) with `spe_agui_ui_port: 18333`, `spe_agent_api_key: <the dummy agent key>`,
  `spe_frontend_dir: <S>` that slurps `agent.env` into `agui_agent_env` and includes a copy of the new tasks with
  `-p spe-frontend` replaced by `-p spe-frontend-s3test`. Run it these ways (`docker compose up -d
  --force-recreate` after each change to the compose file):

| Case | Expected |
|---|---|
| stub answers `[]`, files without keys | `failed=0` |
| a file in `/data/sessions` contains the dummy LLM key | fails: "a key reached a session file …: /data/sessions/<file>" |
| stub answers `{"a":1}` | fails: "GET /api/sessions answered 200 without a JSON list" |
| volume mounted elsewhere (`chat-sessions:/data/other`) | fails: "chat-ui hardening changed: … mounts ['volume:/data/other'] …" |
| `read_only: false` | fails: "chat-ui hardening changed: ReadonlyRootfs False, …" |
| a second mount (`./x:/x`) | fails: "… mounts ['bind:/x', 'volume:/data'] …" |
| a third tmpfs (`/run`) | fails: "… tmpfs ['/app/.next/cache', '/run', '/tmp'] …" |
| volume back at `/data` but no `sessions/` in it (`docker compose exec -u 0 chat-ui rm -rf /data/sessions`) | fails: "could not scan /data/sessions in chat-ui (grep exit 2)" |

  The hardening rows were tried while writing this plan against such a project. Then `docker compose -p
  spe-frontend-s3test down -v` and `rm -rf "$S"`. Paste the results into the handoff.

- [ ] **Step 6: Run on the dev VM** (no model call: `dev-local.yml` has `spe_agui_smoke: false`): `play verify`.
  Expected: `ok` for "Session API answers", "Session API answered 200 with a JSON list", "chat-ui keeps a read-only
  root, one volume at /data and tmpfs only at /tmp and /app/.next/cache", "All three keys found",
  "Session files could be scanned", "No session file holds the agent, LLM or sandbox key"; `failed=0`.

- [ ] **Step 7: Commit**

```bash
git add platform/ansible/roles/agui/tasks/checks.yml
git commit -s -m "agui checks: session API answers; chat-ui hardening; no key in a session file

Run by create.yml and verify.yml. docker inspect of chat-ui: read-only root, the
sessions volume at /data as its only mount, tmpfs only at /tmp and /app/.next/cache.
The key scan is a detector: chat-ui never holds the LLM or sandbox key, so a hit
means one reached a conversation."
```

### Task 4: the dev-VM archive checks (decision 11)

**Files:** Create: `platform/dev/fake-agent.compose.yml`. Modify: `platform/dev/fake_agent.py`.

**Interfaces:** Consumes: slice 2's `agui` export in `roles/run_archive` (spec §4 *Export*, step 1 (*Barrier*):
`stop -t 30 chat-ui` then `agent`; copy, restart; `ps -a -q chat-ui` fails the export when the container is
missing; an absent run log is accepted through `docker compose cp`'s `Could not find the file` error, slice 2's
clarification 3; `write_agui_run.py`);
`sessions.py` (task 2) locally and with `--url http://127.0.0.1:3000 --compose-file $F` (scenarios `stop` and
`slow-loop`); the dev VM's instance `dev-local` (`spe_provision: existing`, `spe_frontend: agui`, frontend
directory `/home/ubuntu/spe-frontend`, chat UI on `127.0.0.1:3000`, run directories
`/data-share/runs/<UTC time>_dev-local/`); task 3's shell helpers. Produces: the evidence in the handoff.

**Decisions:** 11, each of its four acceptance checks on the dev VM. No model is called: the instance's `agent`
service runs `platform/dev/fake_agent.py` (scripted model, fake sandbox) inside the agent's own image, with the
agent's key, port and run-log volume, through a compose override; the archive stops, copies and restarts that
container as it would the real agent. `create` puts the real agent back.

- [ ] **Step 1: Let `fake_agent.py` run as the instance's agent**

Change `platform/dev/fake_agent.py` (`--key` from the agent's environment, so it never sits in argv; the run log
at a given path, so it lands on the `agent-runs` volume). The diff is against the file as slice 1 left it (with
`import asyncio` and the slow run); `git apply` it:

```diff
--- a/platform/dev/fake_agent.py
+++ b/platform/dev/fake_agent.py
@@ -7,13 +7,15 @@
 "fail" makes the model raise, so the run ends in RUN_ERROR; a message containing
 "slow" streams its answer in SLOW_STEPS chunks, SLOW_STEP_SECONDS apart (about 10 s),
 for stopping, closing or archiving a run in progress. The run log goes to a
-temporary directory.
+temporary directory, or to --run-log PATH; --key defaults to $SPE_AGENT_API_KEY, so
+the key need not sit in argv.
 """
 from __future__ import annotations
 
 import argparse
 import asyncio
 import json
+import os
 import tempfile
 from pathlib import Path
 
@@ -70,23 +72,28 @@
     ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
     ap.add_argument("--port", type=int, default=18100)
     ap.add_argument("--host", default="127.0.0.1")
-    ap.add_argument("--key", required=True, help="bearer key clients must send")
+    ap.add_argument("--key", default=os.environ.get("SPE_AGENT_API_KEY"),
+                    help="bearer key clients must send (default: $SPE_AGENT_API_KEY)")
+    ap.add_argument("--run-log", type=Path, help="run log path (default: in a temporary directory)")
     args = ap.parse_args()
+    if not args.key:
+        ap.error("--key or SPE_AGENT_API_KEY is required")
     tmp = Path(tempfile.mkdtemp(prefix="fake-agent-"))
+    run_log = args.run_log or tmp / "runs.jsonl"
     (tmp / "prompt.txt").write_text("You are a scripted test agent.")
     config = Config.model_validate({
         # Placeholder only: the scripted model replaces it and no LLM is called.
         "model": {"provider": "anthropic", "name": "claude-haiku-5-5"},
         "prompt": {"file": str(tmp / "prompt.txt")},
         "tools": {"sandbox_url": "http://sandbox:8000"},
-        "run_log": str(tmp / "runs.jsonl"),
+        "run_log": str(run_log),
     })
     secrets = Secrets(agent_api_key=args.key, sandbox_api_key="fake-sandbox-key", llm_api_key="no-llm")
     client = SandboxClient("http://sandbox:8000", "fake-sandbox-key",
                            http=httpx.AsyncClient(transport=httpx.MockTransport(fake_sandbox)))
     app = create_app(config, secrets, model_override=FunctionModel(stream_function=scripted), sandbox_client=client,
                      retry_delay=0.1)
-    print(f"fake agent on http://{args.host}:{args.port}/agent, run log {tmp / 'runs.jsonl'}", flush=True)
+    print(f"fake agent on http://{args.host}:{args.port}/agent, run log {run_log}", flush=True)
     uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
 
 
```

Create `platform/dev/fake-agent.compose.yml`:

```yaml
# Development only: runs platform/dev/fake_agent.py (scripted model, fake sandbox, no LLM
# call) in place of an instance's agent, with the agent's key, port and run-log volume.
#   SPE_DEV_PLATFORM=<checkout>/platform docker compose -p spe-frontend \
#     -f <frontend dir>/docker-compose.yml -f platform/dev/fake-agent.compose.yml up -d agent
# `up -d agent` without this file puts the real agent back.
services:
  agent:
    command: ["python", "/src/platform/dev/fake_agent.py", "--host", "0.0.0.0", "--port", "8100",
              "--run-log", "/var/lib/spe-agent/runs.jsonl"]
    volumes:
      - ${SPE_DEV_PLATFORM:?set SPE_DEV_PLATFORM to a checkout's platform directory}:/src/platform:ro
```

Run: `(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)` and
`(cd platform/agui/pydantic-ai-agent && SPE_AGENT_API_KEY=k uv run --group dev python ../../dev/fake_agent.py --port 18101 --run-log /var/tmp/fa-check.jsonl & sleep 8; curl -fsS http://127.0.0.1:18101/healthz; kill %1)`
Expected: pytest passes; `{"status":"ok","tools":16}`, and the start line names `/var/tmp/fa-check.jsonl`.

- [ ] **Step 2: Commit**

```bash
git add platform/dev/fake_agent.py platform/dev/fake-agent.compose.yml
git commit -s -m "fake_agent: --run-log, key from the environment; compose override for an instance

Lets an instance's agent service run the scripted agent, so archive checks need no model."
```

- [ ] **Step 3: Deploy this branch to the dev VM and swap in the fake agent**

```bash
create
SPE_DEV_PLATFORM=$W/platform docker compose -p spe-frontend -f $F -f $W/platform/dev/fake-agent.compose.yml up -d agent
docker compose -p spe-frontend -f $F logs agent | grep "fake agent on"
```

Expected: `create.yml` ends `failed=0`; the log shows
`fake agent on http://0.0.0.0:8100/agent, run log /var/lib/spe-agent/runs.jsonl`.

- [ ] **Step 4: Archive after the browser run (check 1).** The full local run's sessions are copied onto the
  volume (as slice 2 did), and one stopped run goes through the instance itself, so the agent's run log has it.

```bash
rm -rf /var/tmp/spe-e2e-s3 && python3 $W/platform/dev/e2e/sessions.py --sessions /var/tmp/spe-e2e-s3
docker cp -a /var/tmp/spe-e2e-s3/. spe-frontend-chat-ui-1:/data/sessions/
python3 $W/platform/dev/e2e/sessions.py --url http://127.0.0.1:3000 --compose-file $F --scenario stop
play archive; R=$(latest)
diff <(docker compose -p spe-frontend -f $F exec -T chat-ui ls /data/sessions | grep '\.json$' | sort) \
     <(ls $R/agui-sessions | sort) && echo same-files
test -s $R/agent-runs.jsonl && echo run-log
```

Expected: both browser runs end with their `ok - …` lines (the second prints `session <id>`); `archive.yml`
`failed=0`; `same-files`; `run-log`; `$R/index.md` lists the sessions, hidden and deleted included;
`docker compose -p spe-frontend -f $F ps` shows `chat-ui` and `agent` running again.

- [ ] **Step 5: Archive during a slow run (check 2).** The loop runs in the background; the archive starts once
  the first run is in progress; then the loop is stopped.

```bash
python3 $W/platform/dev/e2e/sessions.py --url http://127.0.0.1:3000 --compose-file $F --scenario slow-loop \
  > /var/tmp/slow-loop.log 2>&1 &
sleep 5; play archive; kill %1
T=$(grep '^title ' /var/tmp/slow-loop.log | tail -1 | cut -d' ' -f2-); R=$(latest)
python3 - "$R" "$T" <<'PY'
import json, pathlib, sys
run, title = pathlib.Path(sys.argv[1]), sys.argv[2]
rec = next(json.loads(p.read_text()) for p in (run / "agui-sessions").glob("*.json")
           if json.loads(p.read_text())["title"] == title)
log = [json.loads(l) for l in (run / "agent-runs.jsonl").read_text().splitlines() if l.strip()]
print("session:", rec["runs"][-1]["status"] if rec["runs"] else "no run",
      "| run log:", [r["status"] for r in log if r.get("thread_id") == rec["id"]])
PY
```

Expected: `session: cancelled | run log: ['cancelled']` (the barrier, spec §4 *Export*, step 1 (*Barrier*),
stopped `chat-ui` mid-run; slice 2's `SIGTERM` drain finalised it `cancelled`; the agent, stopped second, logged the client's disconnect as
`cancelled`). If the barrier fell between two runs (the last title's run `completed`, or no file for it), repeat
the step.

- [ ] **Step 6: Archive with zero runs (check 3).** A fresh instance is not created here (plan README, *Global
  Constraints*): the two volumes are emptied after a backup, archived and restored. Ruling for the handoff:
  *zero runs simulated by emptying `chat-sessions` (`/data/sessions`) and `agent-runs`; why: no instance is created
  or destroyed; cost if wrong: a fresh volume differs from an emptied one only in `/data/sessions`'s creation,
  which slice 1's `docker build` check covers.*

```bash
IMG=$(docker inspect spe-frontend-chat-ui-1 --format '{{.Config.Image}}')
B=$(mktemp -d /var/tmp/spe-zero-run-XXXX); chmod 700 $B          # holds canaries until removed below
docker compose -p spe-frontend -f $F stop -t 30 chat-ui agent
docker run --rm --user 0 --entrypoint sh -v spe-frontend_chat-sessions:/s -v spe-frontend_agent-runs:/r -v $B:/b $IMG \
  -c 'cp -a /s/sessions /b/sessions && cp -a /r /b/runs && find /s/sessions /r -mindepth 1 -delete'
docker compose -p spe-frontend -f $F start agent chat-ui
play archive; R=$(latest)
ls -A $R/agui-sessions | wc -l; test -e $R/agent-runs.jsonl || echo no-run-log; grep -i "no session" $R/index.md
docker compose -p spe-frontend -f $F stop -t 30 chat-ui agent
docker run --rm --user 0 --entrypoint sh -v spe-frontend_chat-sessions:/s -v spe-frontend_agent-runs:/r -v $B:/b $IMG \
  -c 'cp -a /b/sessions/. /s/sessions/ && cp -a /b/runs/. /r/'
docker compose -p spe-frontend -f $F start agent chat-ui
# The copies keep the containers' owners (uid 1000 and the agent's 10001) and mode 0700, so the host
# user cannot delete them: remove them as root in a container, then the empty directory.
docker run --rm --user 0 --entrypoint sh -v $B:/b $IMG -c 'rm -rf /b/sessions /b/runs' && rmdir $B
test -e $B && echo "BACKUP LEFT: $B" || echo backup-removed
```

Expected: `archive.yml` `failed=0` (the emptied `agent-runs` volume has no `runs.jsonl`: the export accepts the
copy's `Could not find the file`, slice 2's clarification 3); `0`; `no-run-log`; the index line saying no session
was recorded;
`backup-removed` (the backup holds a run log and sessions with canaries: if `BACKUP LEFT` prints, remove it before
going on). After the restore `curl -s 127.0.0.1:3000/api/sessions` lists step 4's sessions again.

- [ ] **Step 7: Archive with `chat-ui` removed (check 4) — STOP AND ASK before `destroy.yml`**

First the safe half, without `destroy.yml`:

```bash
before=$(latest)
docker compose -p spe-frontend -f $F rm -sf chat-ui
play archive; echo "rc=$?"
test "$(latest)" = "$before" && echo no-new-run-dir
```

Expected: `archive.yml` fails in the export (slice 2's missing-container check), `rc=2`, `no-new-run-dir`.

Then **stop and ask the user**, in these words: "Decision 11's last check runs `destroy.yml` on the dev VM with
`chat-ui` removed, expecting the archive to fail and nothing to be reset. If the archive wrongly succeeded, the
reset would take every compose stack on this VM down with its volumes. May I run `destroy.yml -e
@instances/dev-local.yml -e spe_confirm_reset=dev-local` (from the worktree, as `play` runs `archive.yml`)?" Do
nothing until the user answers.

- **If the user agrees:** `(cd $W/platform/ansible && ansible-playbook playbooks/destroy.yml -e
  @$M/platform/ansible/instances/dev-local.yml -e spe_output_root=$M/platform/ansible/output -e
  spe_confirm_reset=dev-local </dev/null)`. Expected: it fails in the export; no task of the play *Destroy SPE
  instance* runs; `docker compose -p spe-frontend -f $F ps -a` and `docker volume ls | grep spe-frontend` show
  every other container and every volume still there.
- **If the user declines:** do not run `destroy.yml`. Show the same property without the dev VM: in a scratch
  directory, a stub `archive.yml` (a `localhost` play adding host `vm` with `ansible_connection: local`; an
  *Export* play on `vm` with `any_errors_fatal: true` whose task is `ansible.builtin.command: "false"`; a *Write*
  play on `localhost` printing `WRITE RAN`) and a stub `destroy.yml` that imports it and then prints `DESTROY RAN`;
  `ansible-playbook -i localhost, destroy.yml </dev/null`. Expected: neither `WRITE RAN` nor `DESTROY RAN`
  (checked while writing this plan). With the safe half (the real `archive.yml` fails on the dev VM) and
  `destroy.yml`'s `import_playbook: archive.yml` as its first play, that is the check. Record the ruling: *the user
  declined `destroy.yml` on the dev VM; why: the reset is irreversible if the expectation were wrong; cost if wrong:
  how `destroy.yml` reacts to the real export's failure is shown with the stub only.*

Either way, bring `chat-ui` back and the real agent with it: `create`.

- [ ] **Step 8: Record.** In the slice's handoff: each check's command, expected and actual result, the run
  directories' names (not their contents: they hold canaries), the first lines of check 1's `index.md`, and the
  rulings of steps 6 and 7. Nothing is committed in this step; the handoff rides in task 5's commit.

### Task 5: the paid check and closing the track

**Files:** Modify: `AGENTS.md` (*Current work*, *AG-UI agent frontend*),
`docs/superpowers/plans/2026-10-29-agui-chat-sessions/README.md` (*PR slices* status column), `BACKLOG.md` (the
run-report item's reason; more only if something stays open), `docs/README.md` (the plan's row). Create: `docs/superpowers/plans/2026-10-29-agui-chat-sessions/handoffs/<UTC
time>-slice-3-done.md`.

**Interfaces:** Consumes: `sessions.py --scenario two-turn` (task 2); the dev VM with the real agent
(`claude-haiku-5-5`, pinned by `spe_agent_allowed_models` in `dev-local.yml`); task 3's shell helpers. Produces:
the closing handoff.

**Decisions:** spec §6, *One paid check*: a two-turn chat in the browser on the dev VM, then `archive.yml`; about
$0.01. It is the only model call of the whole plan.

- [ ] **Step 1: Ask the user.** "Slice 3's one paid check: a two-turn chat through the chat UI on the dev VM with
  `claude-haiku-5-5` (two short turns with a tool call each, about $0.01), then `archive.yml` and `verify.yml`. May
  I run it?" Wait for an explicit yes. If the user declines, skip step 2, write in the handoff that the paid check
  was not run and why, and add to `BACKLOG.md`: "Run the AG-UI chat sessions' paid check (spec
  `2026-10-29-agui-chat-sessions-design.md` §6): two turns in the browser on the dev VM, then `archive.yml`."

- [ ] **Step 2: Run it** with the real agent (task 4 ended with `create`, which put it back):

```bash
docker compose -p spe-frontend -f $F logs --tail 20 agent | grep -c "fake agent"      # expect 0
python3 $W/platform/dev/e2e/sessions.py --url http://127.0.0.1:3000 --compose-file $F --scenario two-turn \
  --shots docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-3
play archive; play verify
```

Expected: `ok - two turns with the real model, both completed (session <id>)`; `archive.yml` `failed=0`, the newest
run directory's `chats/` has that session's `.md` with both user messages, both answers and the fenced tool calls,
and `agent-runs.jsonl` has two lines with its `thread_id`; `verify.yml` `failed=0` (no key reached the real
conversation). Note the usage the run log records (tokens) in the handoff. Look at `two-turn.png` before
committing it: it must show no canary value (a `pwd` answer and a file list of the sandbox home); if it does,
leave it out of the evidence.

- [ ] **Step 3: Close the track.** First check nothing is pending (`development-workflow.md`, *A track closes
  with nothing pending*): `grep -rn -i "slice 3\|ruling" docs/superpowers/plans/2026-10-29-agui-chat-sessions/handoffs`
  names nothing undone; anything still open moves to `BACKLOG.md`.
  - `AGENTS.md`, *Current work*: delete the line starting `- **AG-UI chat sessions**`.
  - `AGENTS.md`, *AG-UI agent frontend*: the "Not done yet" sentence names only the run report (slice 2 removed
    the archiving part; fix it if it did not).
  - Plan `README.md`, *PR slices*: the status of 1/3 and 2/3 reads `merged #<n>`, and 3/3 `merged #<this PR>`
    (set when the PR is open; the user merges it).
  - `BACKLOG.md`, the run-report item (`- A run report in the CopilotKit chat, …`): its premise "the chat sessions
    work comes first" is gone. Its last sentence, from `Waits because`, becomes:

    ```markdown
    Waits because no one has asked for it on the AG-UI path yet. The chat sessions (plan
    `docs/superpowers/plans/2026-10-29-agui-chat-sessions/`, done) now record every run per session, on the
    `chat-sessions` volume and in the archive, so a report can be built from them.
    ```

  - `docs/README.md`, the row of `superpowers/plans/2026-10-29-agui-chat-sessions/` becomes:

    ```markdown
    | `superpowers/plans/2026-10-29-agui-chat-sessions/` | plan: AG-UI chat sessions in three slices, done (all three merged); shared interfaces in its `README.md`, handoffs in `handoffs/` | you change the CopilotKit chat's sessions or the agui archive, or look for why they work as they do |
    ```

  - The code this slice changed cites no fork-only document (plan README, *Upstream-clean*); this prints nothing
    (rewrite any hit to state the behaviour instead):

    ```bash
    git diff --name-only origin/main...HEAD -- platform | grep -v '\.md$' \
      | xargs -r grep -nE 'spec §|[Dd]ecision [0-9]|Review Focus|slice [0-9]|clarification [0-9]|plan README'
    ```

  - Handoff `handoffs/$(date -u +%Y-%m-%dT%H%MZ)-slice-3-done.md`, heading `# <date>: slice 3 done, track closed`:
    what was built, the evidence of tasks 2–5 (browser runs, `verify.yml`, the four archive checks, the paid
    check), every ruling as *decision, why, cost if wrong*, links to `evidence/slice-3/` and to any new
    `docs/knowledge/` note, and "Next: none; the track is closed."
  - `python3 .methodology/shared/sync-agents.py --check` passes (`AGENTS.md`, *Overrides*).

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md BACKLOG.md docs/README.md docs/superpowers/plans/2026-10-29-agui-chat-sessions/README.md \
  docs/superpowers/plans/2026-10-29-agui-chat-sessions/handoffs/<file>.md \
  docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-3
git commit -s -m "AG-UI chat sessions: slice 3 done, track closed

Paid check, archive checks and verify.yml evidence in the handoff."
```

The PR body lists what ran (*Running things* suites, the browser runs, `verify.yml`, the archive checks, the paid
check) and links the handoff; after the local review round the user merges it (`AGENTS.md`, *Overrides*).
