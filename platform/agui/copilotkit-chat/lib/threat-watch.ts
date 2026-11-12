// The browser's side of the threat score: one draft at a time, scored a moment after the typing pauses.
// Browser-safe: types only from threat.ts. The component (app/threat-indicator.tsx) renders `ThreatState`.
import type { ThreatScore } from "./threat.ts";

export type ThreatState = {
  /** `off`: the instance has no threat score (the server said so once); nothing is asked again. */
  status: "idle" | "loading" | "ready" | "failed" | "off";
  /** The last score; while `loading` it belongs to an earlier text and is shown dimmed. */
  score: ThreatScore | null;
};

export const DEBOUNCE_MS = 350;
/** Shorter drafts are not scored: a word or two says nothing, and every keystroke would be a request. */
export const MIN_CHARS = 8;

export type FetchScore = (text: string, signal: AbortSignal) => Promise<ThreatScore | null>;
type Timers = { set: (f: () => void, ms: number) => unknown; clear: (handle: unknown) => void };
const TIMERS: Timers = { set: (f, ms) => setTimeout(f, ms), clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>) };

/** Whether a draft is scored at all: long enough, and not a slash command. */
export function scorable(text: string): boolean {
  const t = text.trim();
  return t.length >= MIN_CHARS && !t.startsWith("/");
}

export class ThreatWatcher {
  private state: ThreatState = { status: "idle", score: null };
  private timer: unknown = null;
  private inFlight: AbortController | null = null;
  private wanted = "";   // the text the next answer is for
  private scored = "";   // the text `state.score` belongs to

  private readonly fetchScore: FetchScore;
  private readonly onChange: (state: ThreatState) => void;
  private readonly delayMs: number;
  private readonly timers: Timers;

  constructor(fetchScore: FetchScore, onChange: (state: ThreatState) => void, delayMs = DEBOUNCE_MS, timers: Timers = TIMERS) {
    this.fetchScore = fetchScore;
    this.onChange = onChange;
    this.delayMs = delayMs;
    this.timers = timers;
  }

  private set(state: ThreatState): void {
    if (state.status === this.state.status && state.score === this.state.score) return;
    this.state = state;
    this.onChange(state);
  }

  private cancel(): void {
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = null;
    this.inFlight?.abort();
    this.inFlight = null;
  }

  /** The input's text changed. */
  update(text: string): void {
    if (this.state.status === "off") return;
    const t = text.trim();
    if (t === this.wanted) return;
    this.wanted = t;
    this.cancel();
    if (!scorable(t)) {
      this.scored = "";
      return this.set({ status: "idle", score: null });
    }
    if (t === this.scored && this.state.score) return this.set({ status: "ready", score: this.state.score });
    this.set({ status: "loading", score: this.state.score });
    this.timer = this.timers.set(() => void this.ask(t), this.delayMs);
  }

  private async ask(text: string): Promise<void> {
    this.timer = null;
    const controller = new AbortController();
    this.inFlight = controller;
    try {
      const score = await this.fetchScore(text, controller.signal);
      if (controller.signal.aborted || text !== this.wanted) return;
      this.inFlight = null;
      if (score === null) return this.set({ status: "off", score: null });
      this.scored = text;
      this.set({ status: "ready", score });
    } catch {
      if (controller.signal.aborted || text !== this.wanted) return;
      // Unavailable for this draft: the indicator says so, and the next change asks again.
      this.inFlight = null;
      this.scored = "";
      this.wanted = "";
      this.set({ status: "failed", score: null });
    }
  }

  dispose(): void {
    this.cancel();
  }
}

/** Why a category's number deserves less trust, or null: few examples, or a head that barely separates. */
export function weakness(category: { examples: number; auc: number | null }): string | null {
  if (category.examples < 5) return `only ${category.examples} example${category.examples === 1 ? "" : "s"}`;
  if (category.auc !== null && category.auc < 0.8) return "weak detector";
  return null;
}
