// Chat sessions on disk: one JSON file per session, /data/sessions/<uuid>.json.
// The only module that touches the filesystem. Every id is checked by isSessionId() before a
// path is built from it.
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { Message } from "@ag-ui/client";
import { isSessionId } from "./session-id.ts";
export { isSessionId };

export type RunStatus = "completed" | "failed" | "cancelled";
export type RunEntry = { run_id: string; started_at: string; ended_at: string; status: RunStatus };
export type SessionRecord = {
  version: 1;
  id: string;
  title: string;
  title_source: "auto" | "user";
  tags: string[];
  pinned: boolean;
  hidden: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  messages: Message[];
  runs: RunEntry[];
};
export type SessionMeta = Pick<SessionRecord, "id" | "title" | "tags" | "pinned" | "hidden" | "created_at" | "updated_at">;
export type SessionView = Omit<SessionRecord, "deleted_at" | "runs">;
export type MetaPatch = Partial<Pick<SessionRecord, "title" | "tags" | "pinned" | "hidden">>;

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

function messageText(message: Message): string {
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

// One queue and one running set per process, shared by every route bundle: Next.js bundles each
// route separately, so module state would be per bundle, but globalThis is per process. chat-ui
// is one Node process (`node server.js`); a second process would need a file lock instead.
export type RunHandle = { cancel: () => void };
export type Shared = { queue: Map<string, Promise<unknown>>; running: Map<string, RunHandle>; closing: boolean };
const KEY = Symbol.for("spe.sessions.queue");

export function shared(): Shared {
  const g = globalThis as typeof globalThis & { [KEY]?: Shared };
  g[KEY] ??= { queue: new Map(), running: new Map(), closing: false };
  return g[KEY];
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

function toMeta(r: SessionRecord): SessionMeta {
  return { id: r.id, title: r.title, tags: r.tags, pinned: r.pinned, hidden: r.hidden, created_at: r.created_at, updated_at: r.updated_at };
}

// The one test of a soft-deleted session, for every reader: list, GET and run admission.
export function isDeleted(record: SessionRecord): boolean {
  return record.deleted_at !== null;
}

function checkRecord(value: unknown, id: string): SessionRecord {
  const r = value as SessionRecord;
  const ok =
    typeof r === "object" && r !== null && r.version === 1 && r.id === id &&
    typeof r.title === "string" && Array.isArray(r.tags) && Array.isArray(r.messages) &&
    Array.isArray(r.runs) && typeof r.updated_at === "string" && typeof r.pinned === "boolean" &&
    typeof r.hidden === "boolean" && (r.deleted_at === null || typeof r.deleted_at === "string");
  if (!ok) throw new Error(`session file ${id}.json is not a version-1 session`);
  return r;
}

// Test-only: SPE_SESSIONS_TEST_SAVE_DELAY_MS holds each recorded run's write that long, under the
// session's queue, so end-to-end checks can make a save land late. Unset in production.
function testSaveDelay(): Promise<void> {
  const ms = Number(process.env.SPE_SESSIONS_TEST_SAVE_DELAY_MS) || 0;
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
}

export class SessionStore {
  readonly dir: string;

  constructor(dir: string) {
    this.dir = dir;
  }

  private file(id: string): string {
    if (!isSessionId(id)) throw new ValidationError("invalid session id");
    return path.join(this.dir, `${id}.json`);
  }

  async read(id: string): Promise<SessionRecord | null> {
    let text: string;
    try {
      text = await fs.readFile(this.file(id), "utf8");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
    let value: unknown;
    try {
      value = JSON.parse(text);
    } catch (error) {
      // The parser's message quotes the file's content: never pass it on, not even to a log.
      if (error instanceof SyntaxError) throw new Error(`session file ${id}.json does not parse`);
      throw error;
    }
    return checkRecord(value, id);
  }

  async write(record: SessionRecord): Promise<void> {
    const target = this.file(record.id);
    const tmp = `${target}.tmp-${randomUUID()}`;
    try {
      const handle = await fs.open(tmp, "wx", 0o600);
      try {
        await handle.writeFile(JSON.stringify(record, null, 2) + "\n");
        await handle.sync();
      } finally {
        await handle.close();
      }
      await fs.rename(tmp, target);
    } catch (error) {
      await fs.rm(tmp, { force: true }).catch(() => {});
      throw error;
    }
  }

  async list(): Promise<SessionMeta[]> {
    let names: string[];
    try {
      names = await fs.readdir(this.dir);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }
    const metas: SessionMeta[] = [];
    for (const name of names) {
      const id = name.endsWith(".json") ? name.slice(0, -".json".length) : "";
      if (!isSessionId(id)) continue; // also skips <id>.json.tmp-* leftovers
      try {
        const record = await this.read(id);
        if (record && !isDeleted(record)) metas.push(toMeta(record));
      } catch (error) {
        console.error(`sessions: skipping ${name}:`, error instanceof Error ? error.message : error);
      }
    }
    metas.sort((a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0));
    return metas.slice(0, MAX_LIST);
  }

  async patch(id: string, patch: MetaPatch, now: Date): Promise<SessionMeta | null> {
    this.file(id); // throws ValidationError before anything is queued
    return withSession(id, async () => {
      const record = await this.read(id);
      if (!record || isDeleted(record)) return null;
      if (patch.title !== undefined) {
        record.title = patch.title;
        record.title_source = "user";
      }
      if (patch.tags !== undefined) record.tags = patch.tags;
      if (patch.pinned !== undefined) record.pinned = patch.pinned;
      if (patch.hidden !== undefined) record.hidden = patch.hidden;
      record.updated_at = now.toISOString();
      await this.write(record);
      return toMeta(record);
    });
  }

  async softDelete(id: string, now: Date): Promise<boolean> {
    this.file(id);
    return withSession(id, async () => {
      const record = await this.read(id);
      if (!record || isDeleted(record)) return false;
      record.deleted_at = now.toISOString();
      record.updated_at = record.deleted_at;
      await this.write(record);
      return true;
    });
  }

  // A run's end: re-read under the queue, so metadata changed during the run survives.
  // Queued synchronously when called (an async function runs up to its first await), so a
  // drain of shared().queue started right after sees it.
  async recordRun(id: string, messages: Message[], run: RunEntry, now: Date): Promise<void> {
    this.file(id);
    return withSession(id, async () => {
      const stamp = now.toISOString();
      const record: SessionRecord = (await this.read(id)) ?? {
        version: 1, id, title: autoTitle(messages), title_source: "auto", tags: [], pinned: false,
        hidden: false, created_at: run.started_at, updated_at: stamp, deleted_at: null, messages: [], runs: [],
      };
      await testSaveDelay();
      record.messages = messages;
      record.runs.push(run);
      record.updated_at = stamp;
      await this.write(record);
    });
  }
}

export function defaultStore(): SessionStore {
  return new SessionStore(process.env.SPE_SESSIONS_DIR || "/data/sessions");
}
