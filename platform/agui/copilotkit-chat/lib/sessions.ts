// Chat sessions on disk: one append-only journal per session, /data/sessions/<uuid>.jsonl (lib/journal.ts
// writes and parses it, lib/rebuild.ts rebuilds its conversation). The only module that names a journal by
// session id: every id is checked by isSessionId() before a path is built from it. The session list is served
// from an index in memory, built by one pass over the journals on first use and updated on every append.
// Files in the earlier JSON format (<uuid>.json) are neither read nor migrated.
import fs from "node:fs/promises";
import path from "node:path";
import type { Message } from "@ag-ui/client";
import { EarlierFailure, JournalWriter, idOfJournal, journalPath, parseJournal } from "./journal.ts";
import type { Clock, Durability, JournalFs, Line, NewLine } from "./journal.ts";
import { branchOfTip, rebuildText } from "./rebuild.ts";
import type { Conversation } from "./rebuild.ts";
import { isSessionId } from "./session-id.ts";
export { isSessionId };

// `last_run_at`: the latest run_end's time (null before the first), so a client can tell its run was
// journaled apart from a metadata change, which also moves `updated_at` (the journal's last line).
export type SessionMeta = {
  id: string; title: string; tags: string[]; pinned: boolean; hidden: boolean;
  created_at: string; updated_at: string; last_run_at: string | null;
};
export type SessionView = Omit<SessionMeta, "last_run_at"> & { messages: Message[] };
export type MetaPatch = Partial<Pick<SessionMeta, "title" | "tags" | "pinned" | "hidden">>;

export class ValidationError extends Error {}

const TAG = /^[a-z0-9._-]{1,32}$/;
const MAX_TAGS = 20;
const MAX_TITLE = 200;
const AUTO_TITLE = 60;
const MAX_LIST = 1000;

export function normaliseTags(value: unknown): string[] {
  if (!Array.isArray(value)) throw new ValidationError("tags must be a list");
  const tags: string[] = [];
  for (const raw of value) {
    if (typeof raw !== "string") throw new ValidationError("a tag must be a string");
    const tag = raw.trim().toLowerCase();
    if (!TAG.test(tag)) throw new ValidationError("a tag is 1-32 characters of a-z 0-9 . _ -");
    if (!tags.includes(tag)) tags.push(tag);
  }
  if (tags.length > MAX_TAGS) throw new ValidationError("at most 20 tags");
  return tags;
}

export function parsePatch(body: unknown): MetaPatch {
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw new ValidationError("the body must be a JSON object");
  }
  const input = body as Record<string, unknown>;
  const keys = Object.keys(input);
  if (keys.length === 0) throw new ValidationError("nothing to change");
  const patch: MetaPatch = {};
  for (const key of keys) {
    const value = input[key];
    if (key === "title") {
      if (typeof value !== "string") throw new ValidationError("title must be a string");
      const title = value.replace(/\s+/g, " ").trim();
      if (title.length === 0 || Array.from(title).length > MAX_TITLE) {
        throw new ValidationError("title must be 1-200 characters");
      }
      patch.title = title;
    } else if (key === "tags") {
      patch.tags = normaliseTags(value);
    } else if (key === "pinned" || key === "hidden") {
      if (typeof value !== "boolean") throw new ValidationError(`${key} must be true or false`);
      patch[key] = value;
    } else {
      throw new ValidationError("unknown key");
    }
  }
  return patch;
}

// A message's text: its string content, or its text parts joined.
export function messageText(message: Message): string {
  const content = (message as { content?: unknown }).content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => (part && typeof part === "object" && part.type === "text" ? String(part.text ?? "") : ""))
      .join(" ");
  }
  return "";
}

export function autoTitle(messages: Message[]): string {
  const first = messages.find((m) => m.role === "user");
  const text = first ? messageText(first).replace(/\s+/g, " ").trim() : "";
  // Cut by code point (Array.from), never inside a surrogate pair.
  const title = Array.from(text).slice(0, AUTO_TITLE).join("").trim();
  return title || "Untitled";
}

// One queue and one running set per process, shared by every route bundle: Next.js bundles each route
// separately, so module state would be per bundle, but globalThis is per process. chat-ui is one Node
// process (`node server.js`); a second process would need a file lock instead. `running` is keyed by the
// recorder's runKey(threadId, runId): runs on one session may overlap (decision 9).
export type RunHandle = { cancel: () => void };
export type Shared = { queue: Map<string, Promise<unknown>>; running: Map<string, RunHandle>; closing: boolean };
const QUEUE = Symbol.for("spe.sessions.queue");

export function shared(): Shared {
  const g = globalThis as typeof globalThis & { [QUEUE]?: Shared };
  g[QUEUE] ??= { queue: new Map(), running: new Map(), closing: false };
  return g[QUEUE];
}

// Runs fn after every earlier fn for the same id has settled. The map holds only the tail of
// each chain, which never rejects, and drops it once nothing is queued behind it.
export function withSession<T>(id: string, fn: () => Promise<T>): Promise<T> {
  const { queue } = shared();
  const previous = queue.get(id) ?? Promise.resolve();
  const result = previous.then(fn);
  const tail = result.then(
    () => undefined,
    () => undefined,
  );
  queue.set(id, tail);
  void tail.then(() => {
    if (queue.get(id) === tail) queue.delete(id);
  });
  return result;
}

// The index: per journal, what the list needs. Per directory (tests use many), on globalThis, with the
// journal writers, so every route bundle appends through the same writer and updates the same entry.
type Entry = {
  id: string; created_at: string | null; first_at: string | null; last_line_at: string | null;
  last_run_at: string | null; first_user: Message | null; added: boolean;
  title: string | null; tags: string[]; pinned: boolean; hidden: boolean; deleted_at: string | null;
};
type DirIndex = { entries: Map<string, Entry>; ready: Promise<void> | null; writers: Map<string, JournalWriter> };
const INDEX = Symbol.for("spe.sessions.index");

function sessionIndex(): Map<string, DirIndex> {
  const g = globalThis as typeof globalThis & { [INDEX]?: Map<string, DirIndex> };
  g[INDEX] ??= new Map();
  return g[INDEX];
}

function newEntry(id: string): Entry {
  return {
    id, created_at: null, first_at: null, last_line_at: null, last_run_at: null, first_user: null, added: false,
    title: null, tags: [], pinned: false, hidden: false, deleted_at: null,
  };
}

// A meta line's value is folded only when its type is the one parsePatch accepts for that key: a hand-edited
// line with the wrong type is skipped for that key, not fatal, so list() and get() agree with what parsePatch
// would ever have written.
function fold(entry: Entry, line: Line): void {
  entry.first_at ??= line.at;
  entry.last_line_at = line.at;
  if (line.type === "created") {
    entry.created_at ??= line.at;
  } else if (line.type === "run_start") {
    // A run with new messages added them; a refused run has none (decision 3).
    if (line.messages.length > 0) {
      entry.added = true;
      entry.first_user ??= line.messages.find((m) => m.role === "user") ?? null;
    }
  } else if (line.type === "run_end") {
    entry.last_run_at = line.at;
  } else if (line.type === "meta") {
    if (typeof line.title === "string") entry.title = line.title;
    if (Array.isArray(line.tags) && line.tags.every((t) => typeof t === "string")) {
      entry.tags = line.tags;
    }
    if (typeof line.pinned === "boolean") entry.pinned = line.pinned;
    if (typeof line.hidden === "boolean") entry.hidden = line.hidden;
    if (typeof line.deleted_at === "string") entry.deleted_at = line.deleted_at;
  }
}

// Listed: some run added a message, and not deleted. Hidden sessions are listed (the browser filters).
function listed(entry: Entry): boolean {
  return entry.added && entry.deleted_at === null;
}

function toMeta(e: Entry): SessionMeta {
  return {
    id: e.id, title: e.title ?? autoTitle(e.first_user ? [e.first_user] : []), tags: e.tags, pinned: e.pinned,
    hidden: e.hidden, created_at: e.created_at ?? e.first_at ?? "", updated_at: e.last_line_at ?? "",
    last_run_at: e.last_run_at,
  };
}

const nodeFs: JournalFs = { open: (p, flags) => fs.open(p, flags) };

// The error-code helper, shared by this module and lib/api.ts (and the recorder): a filesystem error's
// `code`, or an ordinary Error's name, or "error" for anything else. Never the error's message, which may
// quote file content or a canary.
export function codeOf(error: unknown): string {
  return (error as NodeJS.ErrnoException)?.code ?? (error instanceof Error ? error.name : "error");
}

// A journal's whole text, or null when there is none.
async function readText(fsx: JournalFs, file: string): Promise<string | null> {
  let handle;
  try {
    handle = await fsx.open(file, "r");
  } catch (error) {
    if (codeOf(error) === "ENOENT") return null;
    throw error;
  }
  try {
    const { size } = await handle.stat();
    const buffer = Buffer.alloc(size);
    let offset = 0;
    while (offset < size) {
      const { bytesRead } = await handle.read(buffer, offset, size - offset, offset);
      if (bytesRead === 0) break;
      offset += bytesRead;
    }
    return buffer.subarray(0, offset).toString("utf8");
  } finally {
    await handle.close();
  }
}

// Test-only: SPE_SESSIONS_TEST_SAVE_DELAY_MS holds each run_end append that long, under the session's queue,
// so end-to-end checks can make a run's end land late. Unset in production.
function testSaveDelay(): Promise<void> {
  const ms = Number(process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS) || 0;
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
}

export class Journals {
  readonly dir: string;
  private readonly fs: JournalFs;
  private readonly clock: Clock | undefined;
  private readonly now: () => Date;

  constructor(dir: string, opts: { clock?: Clock; fs?: JournalFs; now?: () => Date } = {}) {
    this.dir = path.resolve(dir);
    this.fs = opts.fs ?? nodeFs;
    this.clock = opts.clock;
    this.now = opts.now ?? (() => new Date());
  }

  private file(id: string): string {
    if (!isSessionId(id)) throw new ValidationError("invalid session id");
    return journalPath(this.dir, id);
  }

  private state(): DirIndex {
    const index = sessionIndex();
    let d = index.get(this.dir);
    if (!d) {
      d = { entries: new Map(), ready: null, writers: new Map() };
      index.set(this.dir, d);
    }
    return d;
  }

  // The index for this directory, built once; a failed build is retried by the next caller.
  private async ready(): Promise<DirIndex> {
    const d = this.state();
    d.ready ??= this.build(d).catch((error: unknown) => {
      d.ready = null;
      throw error;
    });
    await d.ready;
    return d;
  }

  private async build(d: DirIndex): Promise<void> {
    let names: string[];
    try {
      names = await fs.readdir(this.dir);
    } catch (error) {
      if (codeOf(error) === "ENOENT") return;
      throw error;
    }
    for (const name of names) {
      const id = idOfJournal(name);
      if (id === null || !isSessionId(id)) continue; // <uuid>.json (decision 14) and anything else
      try {
        const text = await readText(this.fs, this.file(id));
        if (text === null) continue;
        const entry = newEntry(id);
        for (const line of parseJournal(text).lines) fold(entry, line);
        d.entries.set(id, entry);
      } catch (error) {
        console.error(`sessions: skipping ${name}: ${codeOf(error)}`);
      }
    }
  }

  private writerOpts(): { clock?: Clock; fs?: JournalFs; now?: () => Date } {
    return { fs: this.fs, now: this.now, ...(this.clock ? { clock: this.clock } : {}) };
  }

  /** The journal's conversation, or null when the session has no journal. With `outsideQueue` (a read not
   *  under withSession(id), so an append may be in flight), a last segment without its "\n" is a line still
   *  being written: dropped without a warning. Otherwise it is a torn line, skipped and logged (§13). */
  async load(id: string, opts: { outsideQueue?: boolean } = {}): Promise<Conversation | null> {
    const text = await readText(this.fs, this.file(id));
    if (text === null) return null;
    return rebuildText(id, opts.outsideQueue ? text.slice(0, text.lastIndexOf("\n") + 1) : text);
  }

  /** Appends one line (stamped by the writer) and folds it into the index. The caller holds
   *  withSession(id); a writer that failed is dropped, so the next append opens the journal again, and an
   *  append that found its writer already failed is retried once on a fresh one. */
  async append(id: string, line: NewLine, durability: Durability): Promise<void> {
    const file = this.file(id);
    const d = await this.ready();
    if (line.type === "run_end") await testSaveDelay();
    let written: Line | null = null;
    // Twice at most: a writer whose earlier call failed (an interval fsync no caller waited on) rejects this
    // line without writing it, so it is dropped and the line goes to a fresh writer once.
    for (let attempt = 0; written === null; attempt++) {
      let writer = d.writers.get(id);
      if (!writer) {
        writer = new JournalWriter(file, this.writerOpts());
        d.writers.set(id, writer);
      }
      try {
        written = await writer.append(line, durability);
      } catch (error) {
        if (d.writers.get(id) === writer) d.writers.delete(id);
        void writer.close().catch(() => {});
        if (!(error instanceof EarlierFailure) || attempt > 0) throw error;
      }
    }
    let entry = d.entries.get(id);
    if (!entry) {
      entry = newEntry(id);
      d.entries.set(id, entry);
    }
    fold(entry, written);
  }

  async list(): Promise<SessionMeta[]> {
    const d = await this.ready();
    const metas = [...d.entries.values()].filter(listed).map(toMeta);
    // Newest updated_at first; a tie (two lines stamped the same instant) breaks by id, so the order never
    // depends on the index's build path (an append's insertion order vs. a fresh build's readdir order).
    metas.sort((a, b) => {
      if (a.updated_at !== b.updated_at) return a.updated_at < b.updated_at ? 1 : -1;
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    });
    return metas.slice(0, MAX_LIST);
  }

  /** The tip's branch with the metadata; null when missing, deleted, or no run added a message. */
  async get(id: string): Promise<SessionView | null> {
    this.file(id);
    const d = await this.ready();
    const entry = d.entries.get(id);
    if (!entry || !listed(entry)) return null;
    const conv = await this.load(id, { outsideQueue: true });
    if (!conv || conv.tip === null) return null;
    const { last_run_at: _lastRun, ...meta } = toMeta(entry);
    return { ...meta, messages: branchOfTip(conv) };
  }

  async patch(id: string, patch: MetaPatch): Promise<SessionMeta | null> {
    this.file(id); // throws ValidationError before anything is queued
    return withSession(id, async () => {
      const entry = (await this.ready()).entries.get(id);
      if (!entry || !listed(entry)) return null;
      await this.append(id, { type: "meta", ...patch }, "now");
      return toMeta(entry);
    });
  }

  /** The metadata, and whether a meta line ever set a title (a rename or an earlier model title: autoTitle
   *  is never journaled); null when missing, deleted, or no run added a message. */
  async meta(id: string): Promise<{ meta: SessionMeta; titled: boolean } | null> {
    this.file(id);
    const entry = (await this.ready()).entries.get(id);
    if (!entry || !listed(entry)) return null;
    return { meta: toMeta(entry), titled: entry.title !== null };
  }

  /** A model-written title, appended as a meta line only if no title is set by then: the check runs under
   *  the session's queue, so a rename made while the model was writing wins. The metadata after (unchanged
   *  when a title was already set); null when missing, deleted, or no run added a message. */
  async titleIfUntitled(id: string, title: string): Promise<SessionMeta | null> {
    this.file(id);
    return withSession(id, async () => {
      const entry = (await this.ready()).entries.get(id);
      if (!entry || !listed(entry)) return null;
      if (entry.title === null) await this.append(id, { type: "meta", title }, "now");
      return toMeta(entry);
    });
  }

  async softDelete(id: string): Promise<boolean> {
    this.file(id);
    return withSession(id, async () => {
      const entry = (await this.ready()).entries.get(id);
      if (!entry || !listed(entry)) return false;
      await this.append(id, { type: "meta", deleted_at: this.now().toISOString() }, "now");
      return true;
    });
  }

  async isDeleted(id: string): Promise<boolean> {
    this.file(id);
    return ((await this.ready()).entries.get(id)?.deleted_at ?? null) !== null;
  }
}

export function defaultJournals(): Journals {
  return new Journals(process.env.SPE_SESSIONS_DIR || "/data/sessions");
}
