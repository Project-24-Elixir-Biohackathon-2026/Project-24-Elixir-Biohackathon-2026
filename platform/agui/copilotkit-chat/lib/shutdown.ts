// SIGTERM drain (`docker stop -t 30`, the archive's barrier): refuse new runs, cancel every run in
// progress (each is finalised `cancelled` by the recorder), wait for the session queue to drain, exit.
// Next.js's own SIGTERM handler would exit as soon as its HTTP server closed, possibly before the
// last write, so the image sets NEXT_MANUAL_SIG_HANDLE=true and this handler alone ends the process.
import { shared } from "./sessions.ts";
import type { Shared } from "./sessions.ts";

export const DRAIN_TIMEOUT_MS = 25_000; // inside `docker stop -t 30`, with time left to exit
const INSTALLED = Symbol.for("spe.sessions.shutdown");

function sleep(ms: number): Promise<"timeout"> {
  return new Promise((resolve) => setTimeout(() => resolve("timeout"), ms));
}

function sameMembers(a: Promise<unknown>[], b: Promise<unknown>[]): boolean {
  return a.length === b.length && a.every((p) => b.includes(p));
}

// True once no run is in progress and every queued write has settled; false at the deadline.
export async function drain(state: Shared, timeoutMs: number, pollMs = 50): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const pending = [...state.queue.values()];
    const left = deadline - Date.now();
    if (left <= 0) return false;
    const outcome = await Promise.race([Promise.allSettled(pending).then(() => "settled" as const), sleep(left)]);
    if (outcome === "timeout") return false;
    if (state.running.size === 0 && sameMembers(pending, [...state.queue.values()])) return true;
    await sleep(Math.min(pollMs, Math.max(0, deadline - Date.now())));
  }
}

export async function shutdown(state: Shared, exit: (code: number) => void, timeoutMs = DRAIN_TIMEOUT_MS): Promise<void> {
  state.closing = true;
  const runs = [...state.running.values()];
  for (const handle of runs) {
    try {
      handle.cancel();
    } catch (error) {
      console.error("shutdown: cancelling a run failed:", error instanceof Error ? error.message : String(error));
    }
  }
  const drained = await drain(state, timeoutMs);
  if (drained) {
    console.log(`shutdown: ${runs.length} run(s) cancelled, sessions saved`);
  } else {
    console.error(`shutdown: sessions did not drain within ${timeoutMs} ms; exiting anyway`);
  }
  exit(drained ? 0 : 1);
}

export function installShutdown(): void {
  const g = globalThis as Record<symbol, unknown>;
  if (g[INSTALLED]) return;
  g[INSTALLED] = true;
  if (!process.env.NEXT_MANUAL_SIG_HANDLE) {
    console.warn("shutdown: NEXT_MANUAL_SIG_HANDLE is not set; Next.js may exit before the sessions are saved");
  }
  let started = false;
  process.on("SIGTERM", () => {
    if (started) return;
    started = true;
    void shutdown(shared(), (code) => process.exit(code));
  });
}
