# Runs and results

## `hardening.json`

Written by the build to the hand-off directory, next to `canaries.json`: the level, every hardening switch's
value, the frontend, the agent's model provider and model, this repo's commit, and whether the injection
fixtures were planted (`injections`: all three on, or all off for the clean control). The restore hook adds the
measured restore time. Every report is labelled from it.

## One ladder run (decision 10)

`platform/promptfoo-evals/run.sh <hand-off dir>`, per level and model:

1. `npm run eval:controls`: the controls suite. Writes `reports/controls.json`.
2. If any probe disagrees with the level, stop with a non-zero exit, before any model call.
3. `npm run eval:agent -- --repeat N --no-cache`: the agent suite. Writes `reports/agent.json`.

`maxConcurrency: 1` stays: all tests share one instance. Running the agent suite makes paid model calls and
needs the user's OK each time (`AGENTS.md`, *Project rules*).

## The clean control (clarification 6)

Injections are on at every level, so the ladder measures behaviour in an injected environment; on its own it
cannot say how much of it the injections caused. One extra run gives that comparison: at L0 only, the VM is
rebuilt in place with the three `spe_inject_*` switches off, and the injection tests alone (`--filter-metadata
group=injection`) run with the same repeats as L0. Its counts are the matrix column `L0 clean`, beside `L0`.
`injection.followed` is zero there by construction; the comparison is the other metrics on the same prompts.
Five repeats on each side give a rough contrast, not an effect size.

## Repeats and cost

`N` is 5 at L0 and at the last level, 3 in between. With the first catalogue (~11 tests), a ladder is about
11 × (5 + 3 × 4 + 5) ≈ 240 agent runs, plus restores, and 15 for the clean control (3 injection tests × 5).
Whether de.NBI runs cost money or only rate is not known.

**What the counts can carry.** Three to five repeats per cell are exploratory evidence: a cell shows that a leak
happens at a level, or that it was not seen in those runs. They are not a failure rate with useful precision and
not a guarantee that a control holds. Results say so where they are cited.

Model: `qwen3.8-27b` on de.NBI (`spe_agent_model_provider: openai_compatible`).
Every report is still labelled with the model from `hardening.json`, so a later run on another model is
never mixed into the same matrix.

## The matrix (decision 11)

`platform/promptfoo-evals/matrix.py` reads the reports of every level of one model and writes Markdown:

- one row per test (with its group, threat and path), one column per level, and `L0 clean` before `L0`;
- each cell: the failure count per metric over the repeats (`answer 2/5, touched 3/5`), and for utility tests
  the pass rate;
- above the columns: the controls suite's result per level (all probes as expected, or which disagreed).

It reads only counts and metric names, never tokens or answers, so its output can be committed and cited in a
`biohackathon` knowledge record. The raw reports and `.promptfoo/` stay git-ignored and are deleted after use.
