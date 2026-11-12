"use client";
// The threat score under the chat input: how much the draft resembles known adversarial prompts, asked for
// while typing (lib/threat-watch.ts) and shown as a chip; a click opens the per-category scores. Advisory:
// it never blocks sending. Absent when the instance has the score switched off, and for commands.
// Labels come from the agent's model file: rendered as React text only.
import { CopilotChatInput } from "@copilotkit/react-core/v2";
import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import type { ComponentProps } from "react";
import { fetchThreatScore } from "../lib/client.ts";
import type { ThreatLevel, ThreatScore } from "../lib/threat.ts";
import { ThreatWatcher, weakness } from "../lib/threat-watch.ts";
import type { ThreatState } from "../lib/threat-watch.ts";

/** The input's current text, from app/command-input.tsx: the disclaimer slot gets no props of the input's. */
const DraftText = createContext("");
export const DraftTextProvider = DraftText.Provider;

const LEVEL_LABEL: Record<ThreatLevel, string> = { low: "low", elevated: "elevated", high: "high" };

function Bar({ score, level }: { score: number; level: ThreatLevel }) {
  return (
    <span className="spe-threat-bar" data-level={level} aria-hidden="true">
      <span style={{ width: `${score}%` }} />
    </span>
  );
}

type Place = { below: boolean; maxHeight: number };

function Details({ score, id, place }: { score: ThreatScore; id: string; place: Place }) {
  return (
    <div className="spe-threat-panel" data-below={place.below ? "" : undefined} style={{ maxHeight: place.maxHeight }}
      id={id} role="region" aria-label="Threat score details">
      <div className="spe-threat-head">
        <strong>Threat score {score.score}</strong>
        <span className="spe-threat-level" data-level={score.level}>{LEVEL_LABEL[score.level]}</span>
      </div>
      <p>How much this draft resembles known adversarial prompts. Advisory only: nothing is blocked.</p>
      <ul>
        {score.categories.map((c) => {
          const weak = weakness(c);
          return (
            <li key={c.id} data-level={c.level}>
              <span className="spe-threat-name">
                {c.label}
                {weak && <span className="spe-threat-weak" title="Treat this number with caution">{weak}</span>}
              </span>
              <Bar score={c.score} level={c.level} />
              <span className="spe-threat-number">{c.score}</span>
            </li>
          );
        })}
      </ul>
      <p className="spe-threat-foot">
        0 to 100 per detector: from 50, only 5% of benign prompts score higher; from 75, 1%. Violations that read
        like ordinary work are often missed. Model of {score.model.trained}, {score.model.embedding_model} embeddings.
      </p>
    </div>
  );
}

export function ThreatIndicator() {
  const text = useContext(DraftText);
  const [state, setState] = useState<ThreatState>({ status: "idle", score: null });
  const [open, setOpen] = useState(false);
  // The details open above the composer, or below it where there is more room (a new chat's centred input),
  // and never taller than that room: they scroll instead.
  const [place, setPlace] = useState<Place>({ below: false, maxHeight: 460 });
  const watcher = useRef<ThreatWatcher | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    const w = new ThreatWatcher(fetchThreatScore, setState);
    watcher.current = w;
    return () => w.dispose();
  }, []);
  useEffect(() => watcher.current?.update(text), [text]);

  const score = state.score;
  const shown = open && score !== null;
  // Escape, or a click outside the indicator and the composer, closes the details: typing on keeps them open,
  // so the categories can be watched while the draft changes.
  useEffect(() => {
    if (!shown) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onDown = (e: MouseEvent) => {
      const target = e.target as Element | null;
      if (root.current?.contains(target) || target?.closest?.('[data-testid="copilot-chat-input"]')) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [shown]);

  if (state.status === "off") return null;
  return (
    // The row keeps its height while empty, so the composer does not jump when a score appears.
    <div className="spe-threat" ref={root}>
      {score && (
        <button
          type="button"
          className="spe-threat-chip"
          data-level={score.level}
          data-stale={state.status === "loading" ? "" : undefined}
          aria-expanded={shown}
          aria-controls={shown ? panelId : undefined}
          title="Show the score per category"
          onClick={() => {
            const composer = root.current?.parentElement?.getBoundingClientRect();
            if (composer) {
              const above = composer.top;
              const under = window.innerHeight - composer.bottom;
              setPlace({ below: under > above, maxHeight: Math.max(160, Math.min(460, Math.max(above, under) - 16)) });
            }
            setOpen((v) => !v);
          }}
        >
          <span className="spe-threat-dot" aria-hidden="true" />
          Threat score <strong>{score.score}</strong>
          <span className="spe-threat-level" data-level={score.level}>{LEVEL_LABEL[score.level]}</span>
        </button>
      )}
      {!score && state.status === "loading" && <span className="spe-threat-wait">Scoring…</span>}
      {!score && state.status === "failed" && <span className="spe-threat-wait">Threat score unavailable</span>}
      {shown && <Details score={score} id={panelId} place={place} />}
    </div>
  );
}

/** The input's disclaimer slot: the indicator, then CopilotKit's own notice. */
export function ThreatDisclaimer(props: ComponentProps<typeof CopilotChatInput.Disclaimer>) {
  return (
    <>
      <ThreatIndicator />
      <CopilotChatInput.Disclaimer {...props} />
    </>
  );
}
