# Inputs for the plan

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
