// A session's journal: /data/sessions/<uuid>.jsonl, one JSON object per line, append-only (spec §13,
// *The journal*). This module owns the line format, parsing (a torn or foreign line is skipped, never fatal)
// and JournalWriter, the only code that appends to a journal. Nothing here renames, truncates or rewrites a
// journal: a file is opened for appending ("a") or reading ("r") only.
import fsp from "node:fs/promises";
import path from "node:path";
import type { BaseEvent, Message } from "@ag-ui/client";
import { isSessionId, ValidationError } from "./sessions.ts";

export type RunStatus = "completed" | "failed" | "cancelled" | "aborted" | "refused";
export type IgnoredKind = "fabricated" | "edited" | "deleted" | "system";
export type Ignored =
  | { kind: "fabricated" | "edited" | "system"; message: Message }
  | { kind: "deleted"; message: string }; // the deleted message's id
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
// A line before JournalWriter stamps its `at`.
export type NewLine = Line extends infer L ? (L extends Line ? Omit<L, "at"> : never) : never;

export const JOURNAL_SUFFIX = ".jsonl";
export const FSYNC_INTERVAL_MS = 1000;

export function journalPath(dir: string, id: string): string {
  if (!isSessionId(id)) throw new ValidationError("invalid session id");
  return path.join(dir, `${id}${JOURNAL_SUFFIX}`);
}

export function idOfJournal(name: string): string | null {
  if (!name.endsWith(JOURNAL_SUFFIX)) return null;
  const id = name.slice(0, -JOURNAL_SUFFIX.length);
  return isSessionId(id) ? id : null;
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isString = (v: unknown): v is string => typeof v === "string";

// The fields a reader relies on, per type; anything else on a line is kept as written.
function isLine(v: unknown): v is Line {
  if (!isObject(v) || !isString(v.at)) return false;
  switch (v.type) {
    case "created":
      return isString(v.id);
    case "run_start":
      return isString(v.run_id) && (v.anchor === null || isString(v.anchor)) && Array.isArray(v.messages)
        && v.messages.every((m) => isObject(m) && isString(m.id)) && Array.isArray(v.ignored) && isObject(v.request);
    case "event":
      return isString(v.run_id) && isObject(v.event) && isString(v.event.type);
    case "run_end":
      return isString(v.run_id) && isString(v.status);
    case "meta":
      return true;
    default:
      return false;
  }
}

export function parseJournal(text: string): { lines: Line[]; skipped: number } {
  const lines: Line[] = [];
  let skipped = 0;
  const raw = text.split("\n");
  if (raw.at(-1) === "") raw.pop(); // the newline that ends the last line
  raw.forEach((row, index) => {
    // A blank line is no line, and no skip. JournalWriter never writes one (its torn-end repair adds "\n" only
    // after a last byte that is not "\n"); only an edit by hand leaves one.
    if (row === "") return;
    let value: unknown;
    try {
      value = JSON.parse(row);
    } catch {
      value = undefined;
    }
    if (isLine(value)) {
      lines.push(value);
    } else {
      skipped++;
      console.warn(`journal: line ${index + 1} skipped (not a journal line)`);
    }
  });
  return { lines, skipped };
}

export type Durability = "now" | "soon";
export type Clock = { now: () => number; setTimeout: (fn: () => void, ms: number) => unknown; clearTimeout: (h: unknown) => void };
type Handle = {
  appendFile(data: string): Promise<void>;
  sync(): Promise<void>;
  close(): Promise<void>;
  stat(): Promise<{ size: number }>;
  read(buf: Buffer, off: number, len: number, pos: number): Promise<{ bytesRead: number }>;
};
// syncDir: fsync a directory, so a file just created in it survives a crash; absent, the real one is used.
export type JournalFs = { open: (path: string, flags: "a" | "r") => Promise<Handle>; syncDir?: (dir: string) => Promise<void> };

const realClock: Clock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => {
    const handle = setTimeout(fn, ms);
    handle.unref(); // a pending fsync never keeps the process alive; close() flushes it
    return handle;
  },
  clearTimeout: (handle) => clearTimeout(handle as NodeJS.Timeout),
};
async function syncDirectory(dir: string): Promise<void> {
  const handle = await fsp.open(dir, "r");
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}
const realFs: JournalFs = { open: (file, flags) => fsp.open(file, flags), syncDir: syncDirectory };

// What a JournalWriter's call rejects with when an earlier call had already failed: this call wrote nothing.
// It carries the earlier failure's message and code, so a log line names the same cause.
export class EarlierFailure extends Error {
  readonly code: string | undefined;
  readonly earlier: unknown;
  constructor(earlier: unknown) {
    super(earlier instanceof Error ? earlier.message : String(earlier));
    this.earlier = earlier;
    this.name = "EarlierFailure";
    this.code = (earlier as NodeJS.ErrnoException)?.code;
  }
}

// The only writer of a journal. Appends are chained, so lines are written whole and in call order; a caller
// still serialises appends per session (spec §13, *Concurrency and branches*). "now" resolves after an fsync;
// "soon" resolves after the write and fsyncs within FSYNC_INTERVAL_MS. A failed write or fsync fails that
// append and every later one (decision 8).
export class JournalWriter {
  readonly path: string;
  private readonly clock: Clock;
  private readonly fs: JournalFs;
  private readonly now: () => Date;
  private handle: Handle | null = null;
  private chain: Promise<unknown> = Promise.resolve();
  private timer: unknown = null;
  private failure: unknown = null;
  private closed = false;

  constructor(file: string, opts: { clock?: Clock; fs?: JournalFs; now?: () => Date } = {}) {
    this.path = file;
    this.clock = opts.clock ?? realClock;
    this.fs = opts.fs ?? realFs;
    this.now = opts.now ?? (() => new Date());
  }

  append(line: NewLine, durability: Durability): Promise<Line> {
    return this.enqueue(async () => {
      if (this.closed) throw new Error("journal writer is closed");
      const handle = await this.open();
      // A caller's own `at` (a line typed loosely) is dropped: the writer's stamp is the line's time.
      const { type, at: _ignored, ...rest } = line as NewLine & { at?: unknown };
      const stamped = { type, at: this.now().toISOString(), ...rest } as Line;
      await handle.appendFile(`${JSON.stringify(stamped)}\n`);
      if (durability === "now") {
        this.cancelTimer();
        await handle.sync();
      } else if (this.timer === null) {
        this.timer = this.clock.setTimeout(() => {
          this.timer = null;
          // No caller waits on this fsync: its failure is logged here, and fails every later append. After an
          // earlier failure (already reported to its caller) it does nothing.
          void this.enqueue(async () => {
            if (this.failure === null) await this.handle?.sync();
          }, true).catch((error: unknown) => {
            console.error(`journal ${path.basename(this.path)}: interval fsync failed: ${error instanceof Error ? error.message : String(error)}`);
          });
        }, FSYNC_INTERVAL_MS);
      }
      return stamped;
    });
  }

  close(): Promise<void> {
    return this.enqueue(async () => {
      if (this.closed) return;
      this.closed = true;
      const pending = this.timer !== null;
      this.cancelTimer();
      const handle = this.handle;
      this.handle = null;
      if (!handle) return;
      try {
        if (pending) await handle.sync();
      } finally {
        await handle.close();
      }
    }, true);
  }

  // Runs fn after every earlier call; once one has failed, later ones fail with EarlierFailure, writing nothing
  // (close still runs).
  private enqueue<T>(fn: () => Promise<T>, evenAfterFailure = false): Promise<T> {
    const run = this.chain.then(async () => {
      if (this.failure !== null && !evenAfterFailure) throw new EarlierFailure(this.failure);
      try {
        return await fn();
      } catch (error) {
        this.failure ??= error;
        throw error;
      }
    });
    this.chain = run.catch(() => {});
    return run;
  }

  private cancelTimer(): void {
    if (this.timer !== null) this.clock.clearTimeout(this.timer);
    this.timer = null;
  }

  // Opens for appending; before the first append, a file that does not end in "\n" (a torn last line from a
  // hard kill) gets one, so the next line starts clean. A file that is empty here was just created: its
  // directory is fsynced once, so the journal's name survives a crash as its lines do.
  private async open(): Promise<Handle> {
    if (this.handle) return this.handle;
    const handle = await this.fs.open(this.path, "a");
    try {
      const { size } = await handle.stat();
      if (size === 0) await (this.fs.syncDir ?? syncDirectory)(path.dirname(this.path));
      if (size > 0) {
        const reader = await this.fs.open(this.path, "r");
        const last = Buffer.alloc(1);
        try {
          await reader.read(last, 0, 1, size - 1);
        } finally {
          await reader.close();
        }
        if (last[0] !== 0x0a) await handle.appendFile("\n");
      }
    } catch (error) {
      await handle.close();
      throw error;
    }
    this.handle = handle;
    return handle;
  }
}
