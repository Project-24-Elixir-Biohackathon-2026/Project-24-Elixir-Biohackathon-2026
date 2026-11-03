// The run route's hook: AG-UI middleware on the `spe` agent that keeps each session's journal. Per run it
// admits or refuses; classifies the client's history against the journal (lib/anchor.ts); writes run_start,
// fsynced, before the agent is called; sends the agent the journal's path plus the new messages; journals every
// event; and writes run_end before the terminal event is passed on (spec §13, *The run route*). One instance
// serves every clone of the agent, so all per-run state lives in the closure of run().
import { EventType, Middleware } from "@ag-ui/client";
import type { AbstractAgent, BaseEvent, Message, RunAgentInput } from "@ag-ui/client";
import { Observable } from "rxjs";
import type { Subscription } from "rxjs";
import { classify } from "./anchor.ts";
import type { Classification } from "./anchor.ts";
import type { Durability, NewLine, RunStatus } from "./journal.ts";
import { codeOf, isSessionId, shared, withSession } from "./sessions.ts";
import type { Journals, RunHandle } from "./sessions.ts";

// The RUN_ERROR messages of a run the recorder refuses or ends itself. lib/reconcile.ts copies them.
const INVALID = "invalid session";
const DELETED = "this session was deleted";
const CLOSING = "the chat UI is shutting down";
const NOT_SAVED = "this session could not be saved";
const NO_NEW_MESSAGE = "this run carries no new message";
const DUPLICATE_RUN = "this run was already recorded";
const STOPPED = "the run was stopped";
export const REFUSAL_MESSAGES: readonly string[] = Object.freeze([
  INVALID, DELETED, CLOSING, NOT_SAVED, NO_NEW_MESSAGE, DUPLICATE_RUN,
]);

type Admission = { refused: string } | { refused: null; classification: Classification };

// A run's key among the recorder's requests and in shared().running: its session and run id. The client
// supplies the run id, so two sessions could send the same one; runs on one session may overlap.
function runKey(threadId: string, runId: string): string {
  return JSON.stringify([threadId, runId]);
}

function runKeyOf(body: unknown): string | undefined {
  if (typeof body !== "string") return undefined;
  try {
    const { threadId, runId } = JSON.parse(body) as { threadId?: unknown; runId?: unknown };
    return typeof threadId === "string" && typeof runId === "string" ? runKey(threadId, runId) : undefined;
  } catch {
    return undefined;
  }
}

// A run's status from its terminal event: RUN_FINISHED completed; RUN_ERROR failed, or cancelled when it is
// the stop button (HttpAgent.abortRun() turns the aborted fetch into RUN_ERROR with code "abort", but only
// once @ag-ui/client 1.0.2's SSE parser has subscribed, after the agent's response headers; see isAbort()).
function statusOf(event: BaseEvent): RunStatus | null {
  if (event.type === EventType.RUN_FINISHED) return "completed";
  if (event.type === EventType.RUN_ERROR) return (event as { code?: string }).code === "abort" ? "cancelled" : "failed";
  return null;
}

function errorOf(event: BaseEvent): string | null {
  return event.type === EventType.RUN_ERROR ? String((event as { message?: unknown }).message ?? "") : null;
}

// True for a stop clicked before the agent's response headers arrive: it reaches the stream's `error:`
// callback as the fetch's raw AbortError, the only built-in error with this name in this chain.
function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export class SessionRecorder extends Middleware {
  readonly journals: () => Journals;
  // One abort controller per admitted run, by runKey(), for its request to the agent.
  private readonly requests = new Map<string, AbortController>();

  constructor(journals: () => Journals) {
    super();
    this.journals = journals;
  }

  // The agent's fetch: pass it to the HttpAgent (`new HttpAgent({ url, fetch: recorder.fetch })`) so that a
  // run the recorder ends (cancel(), a failed append, the client leaving) also closes its request to the
  // agent. Unsubscribing from the agent's stream does not abort that request in @ag-ui/client 1.0.2, and a
  // middleware's `next` is a wrapper, not the agent. The agent's own signal (abortRun()) still applies.
  readonly fetch = (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const key = runKeyOf(init?.body);
    const controller = key === undefined ? undefined : this.requests.get(key);
    if (!controller) return fetch(url, init);
    const signal = init?.signal ? AbortSignal.any([init.signal, controller.signal]) : controller.signal;
    return fetch(url, { ...init, signal });
  };

  run(input: RunAgentInput, next: AbstractAgent): Observable<BaseEvent> {
    return new Observable<BaseEvent>((out) => {
      const id = input.threadId;
      const runId = input.runId;
      const key = runKey(id, runId);
      const { running } = shared();
      let started = false; // run_start is on disk: every way the run ends writes run_end
      let finalised = false; // run_end is written or being written
      let terminal = false; // a terminal event, a stream end or a cancel has reached the recorder
      let inner: Subscription | undefined;
      let chain: Promise<void> = Promise.resolve();
      const request = new AbortController();
      const disconnect = () => {
        inner?.unsubscribe();
        request.abort();
      };
      const pass = (event: BaseEvent) => {
        if (!out.closed) out.next(event);
      };
      const fail = (text: string, code?: string) => {
        pass({ type: EventType.RUN_ERROR, message: text, ...(code ? { code } : {}) } as BaseEvent);
        if (!out.closed) out.complete();
      };
      const release = () => {
        if (running.get(key) === handle) running.delete(key);
        if (this.requests.get(key) === request) this.requests.delete(key);
      };
      // Every append of this run joins the session's queue, so lines of overlapping runs never interleave
      // within a line.
      const append = (line: NewLine, durability: Durability) =>
        withSession(id, () => this.journals().append(id, line, durability));
      // Exactly once per run: the first end wins. The run_end append joins the queue synchronously, so the
      // run leaves the running set at once and a drain started right after sees the write.
      const finalise = async (status: RunStatus, error: string | null): Promise<boolean> => {
        if (!started || finalised) return true;
        finalised = true;
        const writing = append({ type: "run_end", run_id: runId, status, error }, "now");
        release();
        try {
          await writing;
          return true;
        } catch (failure) {
          console.error(`journal: run_end of run ${runId} of ${id} failed: ${codeOf(failure)}`);
          return false;
        }
      };
      // A terminal event or stream end: run_end first, then the outcome; a run_end that cannot be written
      // turns the outcome into "this session could not be saved".
      const end = async (status: RunStatus, error: string | null, last: () => void) => {
        if (await finalise(status, error)) last();
        else fail(NOT_SAVED);
      };
      // Queues fn after every earlier step of this run. A step that throws is logged without its message.
      const step = (fn: () => void | Promise<void>) => {
        chain = chain.then(fn).catch(() => {
          console.error(`journal: a step of run ${runId} of ${id} threw`);
        });
      };
      const handle: RunHandle = {
        // A run that has seen its terminal event ends with that event, not as cancelled.
        cancel: () => {
          if (finalised || terminal) return;
          terminal = true;
          disconnect();
          step(() => end("cancelled", STOPPED, () => fail(STOPPED, "cancelled")));
        },
      };

      this.admit(input, handle).then((admission) => {
        if (admission.refused !== null) {
          pass({ type: EventType.RUN_STARTED, threadId: id, runId } as BaseEvent);
          fail(admission.refused);
          return;
        }
        started = true;
        if (out.closed) {
          // Unsubscribed while admission was pending: the agent is never called.
          terminal = true;
          step(async () => {
            await finalise("cancelled", null);
          });
          return;
        }
        const { path, newMessages, ignored } = admission.classification;
        const messages: Message[] = [...path, ...newMessages];
        let snapshotDue = ignored.length > 0; // decision 6
        this.requests.set(key, request);
        inner = this.runNext({ ...input, messages }, next).subscribe({
          next: (event) => {
            const status = statusOf(event);
            if (status !== null) terminal = true; // synchronously: a cancel() right after is a no-op
            step(async () => {
              if (finalised) return;
              try {
                await append({ type: "event", run_id: runId, event }, "soon");
              } catch (failure) {
                // Decision 8: a record that silently misses events would be worse than a failed run.
                console.error(`journal: an event of run ${runId} of ${id} could not be appended: ${codeOf(failure)}`);
                terminal = true;
                disconnect();
                await finalise("aborted", NOT_SAVED);
                fail(NOT_SAVED);
                return;
              }
              if (status === null) {
                pass(event);
                if (snapshotDue && event.type === EventType.RUN_STARTED) {
                  snapshotDue = false;
                  pass({ type: EventType.MESSAGES_SNAPSHOT, messages } as BaseEvent);
                }
                return;
              }
              await end(status, errorOf(event), () => pass(event));
            });
          },
          error: (error: unknown) => {
            terminal = true;
            step(() => end(isAbort(error) ? "cancelled" : "failed", messageOf(error), () => {
              if (!out.closed) out.error(error);
            }));
          },
          complete: () => {
            terminal = true;
            step(() => end("failed", "the stream ended without a terminal event", () => {
              if (!out.closed) out.complete();
            }));
          },
        });
      }).catch((error: unknown) => {
        // Admission or starting the agent threw.
        console.error(`journal: starting run ${runId} of ${id} failed`);
        terminal = true;
        disconnect();
        if (!started) {
          if (!out.closed) out.error(error);
          return;
        }
        step(() => end("failed", messageOf(error), () => {
          if (!out.closed) out.error(error);
        }));
      });

      // Unsubscribed (the client left, or the stop before the stream ended): cancelled, journaled after the
      // client has gone. A terminal event already seen keeps its own status (its step writes run_end).
      return () => {
        if (started && !finalised) {
          disconnect();
          if (!terminal) {
            terminal = true;
            step(async () => {
              await finalise("cancelled", null);
            });
          }
        } else {
          inner?.unsubscribe();
        }
      };
    });
  }

  // Admission, under the session's queue so it orders with every append to that session. Refusals before
  // run_start write no line; a run without a new user message is journaled, then refused (decision 3).
  private async admit(input: RunAgentInput, handle: RunHandle): Promise<Admission> {
    const id = input.threadId;
    if (!isSessionId(id)) return { refused: INVALID };
    return withSession(id, async () => {
      if (shared().closing) return { refused: CLOSING };
      const journals = this.journals();
      let conv;
      try {
        if (await journals.isDeleted(id)) return { refused: DELETED };
        conv = await journals.load(id);
      } catch (error) {
        console.error(`journal: reading ${id} failed: ${codeOf(error)}`);
        return { refused: NOT_SAVED };
      }
      if (conv?.runs.some((r) => r.run_id === input.runId)) return { refused: DUPLICATE_RUN };
      // Re-checked: SIGTERM may have landed while the journal was read. A handle registered after
      // shutdown() took its snapshot of `running` would never be cancelled.
      if (shared().closing) return { refused: CLOSING };
      const classification = classify(conv, input.messages);
      const { tools, context, state, forwardedProps } = input;
      // A run journaled but not admitted: its run_end, then the refusal the client sees. A run_end that cannot
      // be written leaves the run incomplete in the journal; the client is refused either way.
      const endHere = async (status: RunStatus, error: string): Promise<Admission> => {
        try {
          await journals.append(id, { type: "run_end", run_id: input.runId, status, error }, "now");
        } catch (failure) {
          console.error(`journal: run_end of run ${input.runId} of ${id} failed: ${codeOf(failure)}`);
        }
        return { refused: error };
      };
      let runStartTried = false;
      try {
        // Inside withSession already: append directly, never through withSession again.
        if (conv === null) await journals.append(id, { type: "created", version: 1, id }, "soon");
        runStartTried = true;
        await journals.append(id, {
          type: "run_start", run_id: input.runId, anchor: classification.anchor, messages: classification.newMessages,
          ignored: classification.ignored, request: { tools, context, state, forwardedProps }, source: "chat",
        }, "now");
      } catch (error) {
        console.error(`journal: run_start of run ${input.runId} of ${id} failed: ${codeOf(error)}`);
        // The line may be in the file although its write or fsync failed: end it, so the run is not left
        // incomplete (Journals.append dropped the failed writer, so this reopens the journal).
        return runStartTried ? endHere("aborted", NOT_SAVED) : { refused: NOT_SAVED };
      }
      if (classification.newMessages.length === 0) return endHere("refused", NO_NEW_MESSAGE);
      // Re-checked once run_start is on disk: SIGTERM may have landed during its fsync, after shutdown() took
      // its snapshot of `running`, so a run admitted now would never be cancelled and drain would time out.
      // Its run_start already carries the new user message, so it ends cancelled, not refused (a refused run
      // adds no message, §13).
      if (shared().closing) return endHere("cancelled", CLOSING);
      shared().running.set(runKey(id, input.runId), handle);
      return { refused: null, classification };
    });
  }
}
