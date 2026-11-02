// The session recorder: AG-UI middleware on the `spe` agent that records each run's
// conversation into its session file. One instance serves every clone of the agent, so all
// per-run state lives in the closure of run().
import { EventType, Middleware } from "@ag-ui/client";
import type { AbstractAgent, BaseEvent, Message, RunAgentInput } from "@ag-ui/client";
import { Observable } from "rxjs";
import type { Subscription } from "rxjs";
import { isDeleted, isSessionId, shared, withSession } from "./sessions.ts";
import type { RunHandle, RunStatus, SessionStore } from "./sessions.ts";

export const SAVE_FAILED = "spe.session_save_failed";

// Why a run is refused before it reaches the agent: the RUN_ERROR message of a refused run.
const INVALID = "invalid session";
const DELETED = "this session was deleted";
const RUNNING = "this session is already running";
const CLOSING = "the chat UI is shutting down";
const UNREADABLE = "this session could not be read";
export const REFUSAL_MESSAGES: readonly string[] = Object.freeze([INVALID, DELETED, RUNNING, CLOSING, UNREADABLE]);

type Admission = { refused: string } | { refused: null };

function runIdOf(body: unknown): string | undefined {
  if (typeof body !== "string") return undefined;
  try {
    const runId = (JSON.parse(body) as { runId?: unknown }).runId;
    return typeof runId === "string" ? runId : undefined;
  } catch {
    return undefined;
  }
}

// A run's status from its terminal event: RUN_FINISHED completed; RUN_ERROR failed, or cancelled
// when it is the stop button (HttpAgent.abortRun() turns the aborted fetch into RUN_ERROR with
// code "abort"). A stream that errors or ends without a terminal event is failed; one the client
// leaves first is cancelled.
function statusOf(event: BaseEvent): RunStatus | null {
  if (event.type === EventType.RUN_FINISHED) return "completed";
  if (event.type === EventType.RUN_ERROR) return (event as { code?: string }).code === "abort" ? "cancelled" : "failed";
  return null;
}

export class SessionRecorder extends Middleware {
  readonly store: () => SessionStore;
  readonly now: () => Date;
  // One abort controller per admitted run, by run id, for its request to the agent.
  private readonly requests = new Map<string, AbortController>();

  constructor(store: () => SessionStore, now: () => Date = () => new Date()) {
    super();
    this.store = store;
    this.now = now;
  }

  // The agent's fetch: pass it to the HttpAgent (`new HttpAgent({ url, fetch: recorder.fetch })`)
  // so that a run the recorder ends (cancel(), or the client leaving) also closes its request
  // to the agent. Unsubscribing from the agent's stream does not abort that request in
  // @ag-ui/client 1.0.2, and a middleware's `next` is a wrapper, not the agent, so the recorder
  // cannot call abortRun() itself. The agent's own signal (abortRun(), the stop button) still
  // applies.
  readonly fetch = (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const runId = runIdOf(init?.body);
    const controller = runId === undefined ? undefined : this.requests.get(runId);
    if (!controller) return fetch(url, init);
    const signal = init?.signal ? AbortSignal.any([init.signal, controller.signal]) : controller.signal;
    return fetch(url, { ...init, signal });
  };

  run(input: RunAgentInput, next: AbstractAgent): Observable<BaseEvent> {
    return new Observable<BaseEvent>((out) => {
      const id = input.threadId;
      const { running } = shared();
      const startedAt = this.now().toISOString();
      let messages: Message[] = input.messages;
      let admitted = false;
      let finalised = false;
      let terminal: RunStatus | null = null; // status of the first terminal event seen
      let inner: Subscription | undefined;
      let chain: Promise<void> = Promise.resolve();
      const request = new AbortController();
      // Stops listening to the agent and closes the request to it.
      const disconnect = () => {
        inner?.unsubscribe();
        request.abort();
      };

      const pass = (event: BaseEvent) => {
        if (!out.closed) out.next(event);
      };
      // Leaves the running set only if this run is still the one in it.
      const release = () => {
        if (running.get(id) === handle) running.delete(id);
        if (this.requests.get(input.runId) === request) this.requests.delete(input.runId);
      };
      // Exactly once per run: the first termination wins, every later one does nothing.
      // recordRun joins the session's queue synchronously, so the run leaves the running set as
      // soon as its write is queued: the next admission of this session queues behind the write
      // and is never refused by a run that has already ended.
      // Returns false when the write failed (logged here, without message content).
      const finalise = async (status: RunStatus): Promise<boolean> => {
        if (!admitted || finalised) return true;
        finalised = true;
        try {
          const run = { run_id: input.runId, started_at: startedAt, ended_at: this.now().toISOString(), status };
          const saving = this.store().recordRun(id, messages, run, this.now());
          release();
          await saving;
          return true;
        } catch (error) {
          console.error(`sessions: saving run ${input.runId} of ${id} failed:`, error instanceof Error ? error.message : error);
          return false;
        } finally {
          release();
        }
      };
      const saveFailed = (): BaseEvent =>
        ({ type: EventType.CUSTOM, name: SAVE_FAILED, value: { session: id } }) as BaseEvent;
      // A terminal event or stream end: write first, then pass the outcome on.
      const end = async (status: RunStatus, last: () => void) => {
        if (!(await finalise(status))) pass(saveFailed());
        last();
      };
      // Queues fn after every earlier step of this run. A step that throws is logged (without
      // its message, which may quote the conversation) and the chain goes on.
      const step = (fn: () => void | Promise<void>) => {
        chain = chain.then(fn).catch(() => {
          console.error(`sessions: a step of run ${input.runId} of ${id} threw`);
        });
      };
      const handle: RunHandle = {
        // A run that has seen its terminal event ends with that event, not as cancelled.
        cancel: () => {
          if (finalised || terminal !== null) return;
          disconnect();
          step(() =>
            end("cancelled", () => {
              pass({ type: EventType.RUN_ERROR, message: "the run was stopped", code: "cancelled" } as BaseEvent);
              out.complete();
            }),
          );
        },
      };

      this.admit(id, handle).then((admission) => {
        if (admission.refused !== null) {
          pass({ type: EventType.RUN_STARTED, threadId: id, runId: input.runId } as BaseEvent);
          pass({ type: EventType.RUN_ERROR, message: admission.refused } as BaseEvent);
          out.complete();
          return;
        }
        admitted = true;
        if (out.closed) {
          // Unsubscribed while admission was pending: nothing reached the agent.
          finalised = true;
          release();
          return;
        }
        this.requests.set(input.runId, request);
        inner = this.runNextWithState(input, next).subscribe({
          next: ({ event, messages: latest }) => {
            // Synchronously, so a teardown right after a terminal event still records it.
            if (!finalised && terminal === null) messages = latest;
            terminal ??= statusOf(event);
            step(async () => {
              const status = statusOf(event);
              if (finalised || status === null) return pass(event);
              await end(status, () => pass(event));
            });
          },
          error: (error: unknown) => {
            step(() => end("failed", () => out.error(error)));
          },
          complete: () => {
            step(() => end("failed", () => out.complete()));
          },
        });
      }).catch((error: unknown) => {
        // Admission or starting the agent threw: fail the run, so the session leaves the running set.
        console.error(`sessions: starting run ${input.runId} of ${id} failed`);
        disconnect();
        step(() => end("failed", () => { if (!out.closed) out.error(error); }));
      });

      // Unsubscribed before a terminal event: cancelled, saved after the client has gone.
      return () => {
        if (admitted && !finalised) {
          disconnect();
          void finalise(terminal ?? "cancelled");
        } else {
          inner?.unsubscribe();
        }
      };
    });
  }

  // Admission: under the session's queue, so it orders with every write to that session.
  private async admit(id: string, handle: RunHandle): Promise<Admission> {
    if (!isSessionId(id)) return { refused: INVALID };
    const { running } = shared();
    return withSession(id, async () => {
      if (shared().closing) return { refused: CLOSING };
      if (running.has(id)) return { refused: RUNNING };
      let record;
      try {
        record = await this.store().read(id);
      } catch (error) {
        console.error(`sessions: reading ${id} failed:`, error instanceof Error ? error.message : error);
        return { refused: UNREADABLE };
      }
      if (record && isDeleted(record)) return { refused: DELETED };
      // Re-checked: SIGTERM may have landed while the read above was pending. Without this,
      // a handle registered after shutdown() has taken its snapshot of `running` is never
      // cancelled, and drain() waits for it to end by itself.
      if (shared().closing) return { refused: CLOSING };
      running.set(id, handle);
      return { refused: null };
    });
  }
}
