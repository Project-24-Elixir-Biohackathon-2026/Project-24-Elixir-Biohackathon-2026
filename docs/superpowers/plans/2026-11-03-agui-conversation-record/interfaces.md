# AG-UI conversation record: shared interfaces

Later slices use these names exactly; a slice whose merged code differs records a ruling in its handoff and
rewrites this file in the same PR. Paths are relative to `platform/agui/copilotkit-chat/` unless they say
otherwise. The [plan README](README.md) holds the rulings and constraints these follow.

## `lib/journal.ts` (slice 1, task 2)

```ts
import type { BaseEvent, Message } from "@ag-ui/client";

export type RunStatus = "completed" | "failed" | "cancelled" | "aborted" | "refused";
export type IgnoredKind = "fabricated" | "edited" | "deleted" | "system";
export type Ignored =
  | { kind: "fabricated" | "edited" | "system"; message: Message }
  | { kind: "deleted"; message: string };                 // the deleted message's id (ruling 4)
export type RequestFields = { tools: unknown[]; context: unknown[]; state: unknown; forwardedProps: unknown };
export type MetaFields = { title?: string; tags?: string[]; pinned?: boolean; hidden?: boolean; deleted_at?: string };

export type CreatedLine = { type: "created"; at: string; version: 1; id: string };
export type RunStartLine = {
  type: "run_start"; at: string; run_id: string; anchor: string | null; messages: Message[];
  ignored: Ignored[]; request: RequestFields; source: "chat";
};
export type EventLine = { type: "event"; at: string; run_id: string; event: BaseEvent };
export type RunEndLine = { type: "run_end"; at: string; run_id: string; status: RunStatus; error: string | null };
export type MetaLine = { type: "meta"; at: string } & MetaFields;
export type Line = CreatedLine | RunStartLine | EventLine | RunEndLine | MetaLine;
export type NewLine = Line extends infer L ? (L extends Line ? Omit<L, "at"> : never) : never;

export const JOURNAL_SUFFIX = ".jsonl";
export const FSYNC_INTERVAL_MS = 1000;
export function journalPath(dir: string, id: string): string;     // throws ValidationError unless isSessionId(id)
export function idOfJournal(name: string): string | null;          // "<uuid>.jsonl" → uuid, anything else → null
export function parseJournal(text: string): { lines: Line[]; skipped: number };   // logs each skipped line's number only
// ValidationError and isSessionId are imported from ./sessions.ts, where they live; slice 3's sessions.ts keeps
// exporting both (the import cycle is safe: journal.ts uses them only at call time).

export type Durability = "now" | "soon";                          // "now": fsync before resolving; "soon": within FSYNC_INTERVAL_MS
export type Clock = { now: () => number; setTimeout: (fn: () => void, ms: number) => unknown; clearTimeout: (h: unknown) => void };
export type JournalFs = {                                          // node:fs/promises by default; a test counts sync()
  open: (path: string, flags: "a" | "r") => Promise<{ appendFile(data: string): Promise<void>; sync(): Promise<void>; close(): Promise<void>; stat(): Promise<{ size: number }>; read(buf: Buffer, off: number, len: number, pos: number): Promise<{ bytesRead: number }> }>;
  syncDir?: (dir: string) => Promise<void>;                        // fsync a directory; absent: the real one
};
export class JournalWriter {
  constructor(path: string, opts?: { clock?: Clock; fs?: JournalFs; now?: () => Date });
  append(line: NewLine, durability: Durability): Promise<Line>;  // stamps `at`, appends one line, repairs a torn end before the first append
  close(): Promise<void>;                                          // flushes a pending "soon" fsync
}
// A journal that is empty when the writer first opens it (the writer created it) gets its directory fsynced
// once, so the new file's name is as durable as its first line.
```

## `lib/rebuild.ts` (slice 1, task 3)

```ts
import type { Message } from "@ag-ui/client";
import type { Ignored, Line, MetaFields, RequestFields, RunStatus } from "./journal.ts";

export type Node = { message: Message; parentId: string | null; runId: string };
export type RunView = {
  run_id: string; anchor: string | null; new_messages: Message[]; ignored: Ignored[]; request: RequestFields;
  status: RunStatus | "incomplete"; error: string | null;
  started_at: string; ended_at: string | null; last_at: string;   // last_at: run_end's, else its last event's
  added: string[];                                                  // ids this run added, in order of first appearance (new messages first)
  events: number;
};
export type Conversation = {
  id: string; created_at: string | null;
  meta: Required<Pick<MetaFields, "tags" | "pinned" | "hidden">> & { title: string | null; deleted_at: string | null };
  first_user_text: string | null;
  nodes: Map<string, Node>;
  children: Map<string | null, string[]>;                           // null: the root's children
  runs: RunView[];                                                  // journal order of run_start
  tip: string | null;                                               // decision 9
  tip_run: string | null;
  last_line_at: string | null;
  skipped: number;                                                  // torn or unparsable lines
};
export function rebuild(id: string, lines: Line[]): Promise<Conversation>;     // skipped: 0
export function rebuildText(id: string, text: string): Promise<Conversation>;  // parseJournal + rebuild, skipped filled
export function pathTo(conv: Conversation, id: string | null): Message[];   // root → id, inclusive; [] for null
// A boundary: a user message, or a run's last added message unless it holds a tool call (nothing after it in
// its run answers the call: a run cancelled, failed or cut mid tool call), so no dangling tool call is sent.
export function isBoundary(conv: Conversation, id: string): boolean;
export function branchOfTip(conv: Conversation): Message[];                 // pathTo(conv, conv.tip)
```

## `lib/anchor.ts` (slice 1, task 4)

```ts
import type { Message } from "@ag-ui/client";
import type { Ignored } from "./journal.ts";
import type { Conversation } from "./rebuild.ts";

export type Classification = { anchor: string | null; path: Message[]; newMessages: Message[]; ignored: Ignored[] };
export function canonical(message: Message): string;    // canonical JSON of role, content, toolCalls, toolCallId
export function classify(conv: Conversation | null, client: Message[]): Classification;   // readings: ruling 6
```

## `lib/export.ts` (slice 2, task 1) and `scripts/export-journals.ts` (slice 2, task 2)

```ts
import type { Ignored } from "./journal.ts";
import type { Conversation, RunView } from "./rebuild.ts";

export type ArchiveMode = "live" | "final";
export type OutputItem = Record<string, unknown> & { type: string; id: string };
export type SpeRun = { run_id: string; status: RunView["status"]; started_at: string; ended_at: string | null; error: string | null };
export type ExportedMessage = {                                       // an Open WebUI message, plus the record's fields
  id: string; parentId: string | null; childrenIds: string[]; role: string; content: string; timestamp: number;
  output?: OutputItem[]; spe_run?: SpeRun; spe_ignored?: Ignored[];
};
export type OpenWebUIChat = {
  id: string; title: string; created_at: number; updated_at: number; archived: boolean;
  meta: { tags: string[]; spe_deleted_at?: string };
  chat: { title: string; history: { messages: Record<string, ExportedMessage>; currentId: string | null }; messages: ExportedMessage[] };
};
export type Bundle = { exported_at: number; spe_archive_mode: ArchiveMode; chats: OpenWebUIChat[]; tags: { id: string; name: string }[]; notes: [] };
export type Loose = {                                                 // the fields of an AG-UI message the export reads
  id: string; role: string; content?: unknown; toolCallId?: string; error?: string;
  toolCalls?: { id: string; function: { name: string; arguments: string } }[];
};
export function runMessageId(runId: string): string;                  // "spe-run-<run id>": a run's exported assistant message
export function outputItems(message: Loose): OutputItem[];
export function toOpenWebUIChat(conv: Conversation): OpenWebUIChat;
export function exportJournals(dir: string, mode: ArchiveMode, opts?: { now?: () => Date }): Promise<Bundle>;   // every <uuid>.jsonl via rebuildText, hidden and deleted included
export function bundleJson(bundle: Bundle): string;                   // the file's exact text, shared by the script and the fixtures
```

`node scripts/export-journals.ts <journals dir> <bundle.json> <live|final>`: exit 0 and one line
`N sessions (H hidden, D deleted), <mode> archive`; exit 2 and the usage for wrong arguments; exit 1 on a read or
write failure. In the archive (`roles/run_archive/tasks/export.yml`), slice 3 finds the image with
`docker compose … ps -a --format '{{.Image}}' chat-ui`, registered as **`agui_ui_image`**, the user with `id -u`
and `id -g` (`agui_uid`, `agui_gid`), and runs the exporter with exactly this argv:

```yaml
argv: [docker, run, --rm, --network, none, --read-only, --tmpfs, /tmp, --cap-drop, ALL,
       --security-opt, "no-new-privileges:true", --user, "{{ agui_uid.stdout | trim }}:{{ agui_gid.stdout | trim }}",
       --entrypoint, node, -v, "{{ agui_export_dir.path }}/agui-journals:/in:ro", -v, "{{ agui_export_dir.path }}:/out",
       "{{ agui_ui_image.stdout | trim }}", scripts/export-journals.ts, /in, /out/bundle.json, <mode>]
```

Slice 3 passes `final` (every archive still stops both services); slice 4 changes only the last argument, to
`"{{ 'final' if agui_final else 'live' }}"` from `spe_archive_final`.

## `lib/sessions.ts` (slice 3, task 1)

```ts
export type SessionMeta = { id: string; title: string; tags: string[]; pinned: boolean; hidden: boolean;
  created_at: string; updated_at: string; last_run_at: string | null };          // the browser's shape, unchanged
export type SessionView = Omit<SessionMeta, "last_run_at"> & { messages: Message[] };   // GET one: the tip's branch (§6's row, as slice 3's clarification corrects it)
export type MetaPatch = Partial<Pick<SessionMeta, "title" | "tags" | "pinned" | "hidden">>;
export type RunHandle = { cancel: () => void };
export type Shared = { queue: Map<string, Promise<unknown>>; running: Map<string, RunHandle>; closing: boolean };  // running keyed by runKey(threadId, runId)
export function shared(): Shared;                                  // Symbol.for("spe.sessions.queue")
export function withSession<T>(id: string, fn: () => Promise<T>): Promise<T>;
export class Journals {
  constructor(dir: string, opts?: { clock?: Clock; fs?: JournalFs; now?: () => Date });
  load(id: string): Promise<Conversation | null>;                  // null: no journal
  append(id: string, line: NewLine, durability: Durability): Promise<void>;   // under withSession by the caller; updates the index
  list(): Promise<SessionMeta[]>;                                  // from the index (Symbol.for("spe.sessions.index")), built on first use
  get(id: string): Promise<SessionView | null>;                    // null: missing, deleted, or no run added a message
  patch(id: string, patch: MetaPatch): Promise<SessionMeta | null>;
  softDelete(id: string): Promise<boolean>;
  isDeleted(id: string): Promise<boolean>;
}
export function defaultJournals(): Journals;
```

`normaliseTags`, `parsePatch`, `autoTitle`, `ValidationError` and `isSessionId` keep their names and behaviour.
The index is built once per process: a journal written behind the server's back lists after a restart.
`SPE_SESSIONS_TEST_SAVE_DELAY_MS` stays as the test hook that delays each `run_end` append (decisions 25, 26).

## `lib/recorder.ts` (slice 3, task 2)

`export class SessionRecorder extends Middleware { constructor(journals: () => Journals, now?: () => Date); readonly fetch; run(input, next) }`.
`REFUSAL_MESSAGES` lists the six messages a run is refused or ended with by the recorder: `invalid session`,
`this session was deleted`, `the chat UI is shutting down`, `this session could not be saved`,
`this run carries no new message` (decision 3, journaled) and `this run was already recorded` (a reused `runId`,
no line); `lib/reconcile.ts`'s `REFUSED_RUN_MESSAGES` copies them. `SAVE_FAILED` and the "already running"
refusal are gone. Admission checks `closing` before the journal read, after it, and again once `run_start` is
written; the last ends the run with `run_end` `refused` and the closing refusal.

## Test agents

**`lib/test-agent.ts`** (slice 1, task 1): a user message containing `echo-input` makes the reply's text the JSON
of `[{role, id}]` for every message the agent received. **`platform/dev/fake_agent.py`** (slice 3, task 5): the
same keyword, through `FunctionModel`, answers with the roles and ids pydantic-ai received.

## `write_run.py` (slice 2, task 3)

`is_compaction(item_or_message: dict) -> bool` (id starts with `spe-compaction-`),
`render_ignored(entries: list[dict]) -> str`, `render_status(run: dict) -> str`; `index.md` for a bundle with
`spe_archive_mode` gets `| # | Session | Tags | Created | Runs | Compactions | State |` (the as-built AG-UI
columns, inputs-for-plan, bullet 8) and the live/final line; an Open WebUI bundle (no `spe_archive_mode`) renders
byte-identically to before. `render_status` appends a failed run's `spe_run.error`. A chat file shows the active
branch, then *Other branches* (every message off it, so a refused run's ignored content is in some file; a spec
clarification in slice 2). `write.yml` copies `agui-journals/` and `agent-runs.jsonl` into the run directory
before `write_run.py` runs on `<bundle dir>/bundle.json`.
