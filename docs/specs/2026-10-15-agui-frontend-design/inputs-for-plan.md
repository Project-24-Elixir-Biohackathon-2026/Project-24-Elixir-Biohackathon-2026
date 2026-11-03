# Inputs for the plans

## The conversation record

For the plan that builds the conversation record (decisions 1–18 and what they change in 19–30).

- The live archive (decision 30, clarification 2) is built with the record's journal, not before: until then
  today's barrier stays, since the as-built `<uuid>.json` files are rewritten in place.
- Build decision 5's feasibility check first, in the first slice, before the session API or the archive move.
- One rebuild module (decision 11) shared by the route, the API and the exporter; the exporter runs in the
  `chat-ui` image, so the archive needs no Node on the controller.
- What the agent does with `context`, `state` and `forwardedProps` is not checked here: the plan reads the
  agent's adapter and records the answer, since `run_start` stores them either way.
- The compaction marker's archive rendering moves to `write_run.py` (decision 16) wherever it lives when the
  plan starts.
- The chat's README (*Sessions*) and the getting-started guide describe the storage: the slice that changes it
  rewrites them.
- `@ag-ui/client`'s event application is used as a library on the server; check that its entry point works in
  the Node runtime the image uses, and pin the behaviour with decision 11's test.
- Carry the as-built archive's columns over: `write_agui_run.py`'s `index.md` columns (§14, as built), including
  any compaction counts added before the record ships, go into the record's `index.md` table when that script goes.

## `/compact`

For the plan that builds §15 (decisions 31–39).

- Two slices. (1) The agent: decisions 35 and 36, and `fake_agent.py` scripted to answer a command with a fixed
  summary; it touches only `pydantic-ai-agent/` and `platform/dev/`. (2) `chat-ui` and the archive: decisions
  31–34, 37 and 38, Playwright, and decision 39's model-backed check. Slice 2 starts once the conversation
  record's last slice (the live archive) has merged, since both change `lib/recorder.ts`. Slice 2 builds the
  early output (the README's *Early output*, `/compact`) first, before decisions 34, 37 and 38, so the user's
  judgement of decision 33 comes while it is cheap to change.
- Slice 1 reads how pydantic-ai's AG-UI adapter exposes `forwarded_props` and where `app.py` can answer a run
  without `adapter.run_stream`, and reuses `Compaction._compact`'s summary path rather than a copy of it. That
  path needs a `RunContext` and a `ModelRequestContext` today, counts towards the three per run and appends to
  `pending`: slice 1 splits out a summary function taking the model, the configuration, the history, the focus
  and a usage accumulator, which both the capability and the command path call, and the command path writes its
  usage into the run log's `usage` as `on_complete` does for a model run.
- Decision 39 runs on de.NBI's `qwen3.8-27b`, not on the development VM's model: an instance deployed from the
  slice's worktree, the LLM key and model as the portal's workspaces use them. It is a paid run: the slice asks
  the user before it.
- The chat's README and the getting-started guide gain `/compact`: slice 2 writes them.
- Both slices change files with known defects, fixed there: `platform/dev/fake_agent.py` answers a second
  compaction request in an already compacted session without compacting (its check must require a framed
  summary after the latest real prompt, not anywhere) and guards a request type with a bare `assert` (slice 1);
  `copilotkit-chat/app/compaction-divider.tsx` casts `message.content as string` where `typeof` would narrow
  (slice 2).
