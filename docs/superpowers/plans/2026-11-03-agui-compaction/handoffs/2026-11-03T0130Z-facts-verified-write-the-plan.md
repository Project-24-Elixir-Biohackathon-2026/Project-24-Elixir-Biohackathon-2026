# 2026-11-03: AG-UI compaction plan — facts verified, write the plan files

Unit: `plan/agui-compaction`, claimed as draft PR #16 (label `plan`, created for this). Worktree
`.claude/worktrees/plan-agui-compaction`. Nothing of the plan is written yet except this directory. The session
hit the context budget after the research; the research below is the input, so it is not redone. The user's
standing instruction holds (`docs/handoffs/2026-11-02T2351Z-agui-chat-minors-next.md`, *The user's instruction*).

## Next

1. Write `README.md` (layout of `docs/superpowers/plans/2026-10-29-agui-chat-sessions/README.md`: goal, spec
   link, architecture, tech stack, Global Constraints, Shared interfaces, File structure, PR slices table,
   Review Focus, Proposed spec clarifications, Handoffs) and `slice-1-agent.md`, `slice-2-chat-archive.md`,
   `slice-3-denbi-docs.md`, with `superpowers:writing-plans`. Spec:
   `docs/superpowers/specs/2026-11-03-agui-compaction-design.md` (300 lines; decisions table l. 31–45, *Inputs
   for the plan* l. 269).
2. One local review round (correctness + methodology), merge squashed (sign-off address from the last squash,
   `docs/knowledge/gh-squash-signoff.md`), plan row in `docs/README.md`, the track's line in `AGENTS.md`,
   parent pin, handoff to slice 1.

## Ruling: the marker is an assistant message, not an activity message

The spec's fallback applies (*Inputs for the plan*, first bullet), from reading the code; slice 1, task 1 pins
it with a test and folds it as spec clarification 1, rewriting decision 7, §5, §6, §7 and the glossary.

- `@ag-ui/client` 1.0.2 `AbstractAgent.prepareRunAgentInput` does `n.filter(e=>e.role!==\`activity\`)`
  (`node_modules/@ag-ui/client/dist/index.mjs`, minified; checked by hand). It runs in the browser and again in
  the runtime (`@copilotkit/runtime` `handle-run.mjs:40` `setMessages`, `runner/in-memory.mjs:387` `runAgent`).
  So an `ActivityMessage` never reaches the agent again, and since `recordRun` overwrites `messages`
  (`lib/sessions.ts:291`) the stored record would lose earlier ones too.
- An assistant message with string content round-trips unchanged (schema `z.looseObject`, no merging).
- **Design:** the marker is an assistant text message, `messageId` = `spe-compaction-<uuid4>`, content the
  summary (TEXT_MESSAGE_START/CONTENT/END, role assistant; never an empty delta). On input, `Service` rewrites
  each such assistant message in `run_input.messages` into an `ActivityMessage(activity_type=
  COMPACTION_ACTIVITY_TYPE, content=compaction_payload(CompactionPart(content=…, provider_name="spe-agent")))`
  before `run_stream` (`UIAdapter` is a plain dataclass, `run_input` assignable), so pydantic-ai's own input
  conversion yields the `CompactionPart` (`ui/ag_ui/_adapter.py:589-593`). Imports: `compaction_payload` from
  `pydantic_ai.ui._adapter` (private, l. 184; pinned version, comment it), `COMPACTION_ACTIVITY_TYPE` from
  `pydantic_ai.ui.ag_ui._utils` (l. 71).
- Chat: `<CopilotChat messageView={{ assistantMessage: AssistantOrCompaction }}>`; the slot gets `message`
  (`CopilotChatAssistantMessageProps`, react-core `copilotkit-DFMMPW2I.d.mts:801-828`); fall back to
  `CopilotChatAssistantMessage` exported from `@copilotkit/react-core/v2`; module-scope constant so the
  reference is stable. A custom component bypasses the default toolbar (copy button). `renderCustomMessages`
  cannot replace a message. `CopilotChat` is in `app/page.tsx:272-285`.
- Run log: `RunRecorder.observe` must skip `TextMessageContentEvent`s whose `message_id` starts with the
  prefix, or the summary lands in `answer`.
- Archive: `write_agui_run.py` renders an assistant message with the prefix as `## Compacted` (dispatch at
  l. 102–130; `fence` from `write_run.py:46`); index columns `| # | Session | Tags | Created | Runs | State |`
  (l. 226–248) gain `Compactions`.

## pydantic-ai 2.56 facts (venv in the main checkout: `platform/agui/pydantic-ai-agent/.venv/lib/python3.12/site-packages/pydantic_ai`)

- `pydantic_ai.capabilities.AbstractCapability` (`capabilities/abstract.py:178`);
  `async def wrap_model_request(self, ctx: RunContext, *, request_context: ModelRequestContext, handler)`
  (l. 973), handler `(ModelRequestContext) -> Awaitable[ModelResponse]`, callable once. `Agent(...,
  capabilities=[...])`. No streaming variant: streamed runs use the same hook (`request_context.streaming`).
- `ModelRequestContext` (`models/__init__.py:328`): `model`, `messages` (shallow copy, assignable),
  `model_settings`, `model_request_parameters`. `RunContext`: `messages` (the live history list), `usage`,
  `usage_limits`, `agent`, `deps`.
- `ProcessHistory` pattern (`capabilities/process_history.py`): `request_context.messages = msgs.copy();
  ctx.messages[:] = msgs`.
- Order: agent-level capabilities are outermost in `wrap_model_request`; the adapter's
  `ReinjectSystemPrompt(replace_existing=True)` (`ui/_adapter.py:669-675`) is a `before_model_request` that runs
  **inside** the handler and writes both `request_context.messages` and `ctx.messages[:]`. So the proactive path
  needs no system-prompt work; after a handler that raised (reactive), `ctx.messages` already holds the system
  parts. If a test shows it does not, get them as `ReinjectSystemPrompt` does: `await
  ctx.agent.system_prompt_parts(deps=ctx.deps, model=…)` (`capabilities/reinject_system_prompt.py`).
- **Design picked:** in-run, the capability sets `ctx.messages[:]` to *what is sent* (no marker in the
  pydantic-ai history); the marker exists only in the AG-UI stream and, on later runs, in the input. Proposed
  spec clarification (§3 *Making one* says the marker goes into `ctx.messages`).
- Reactive retry: when the handler raises before its stream is ready and the wrap returns a response from a
  direct `model.request`, `_agent_graph.py` takes the branch `wrap_task.done() and not stream_ready.is_set()`
  (≈ l. 1553–1581) and replays it with `CompletedStreamedResponse(..., replay_events=True)`: it reaches the
  AG-UI stream. The direct request's usage is **not** recorded by the graph (`_record_response_usage` only on
  the handler path): the capability counts it (`ctx.usage.requests += 1; ctx.usage.incr(resp.usage)`); a test
  pins `usage.requests` exactly. The test model must raise when the stream is opened (a small `Model` wrapper
  whose `request_stream` raises on entry), since a `FunctionModel` stream may set `stream_ready` first.
- `CompactionPart` (`messages.py:2269`): `content`, kw `id`, `provider_name`, `provider_details`. On input,
  `MessagesBuilder.add` (`ui/_messages_builder.py:31-44`) appends it to the last message if that is a
  `ModelResponse`, else a new one: the **preceding** response, not the following one as spec §3 says (proposed
  clarification; the part-level cut still holds). Output: a `CompactionPart` in a streamed response triggers
  `handle_compaction` → `ActivitySnapshotEvent` (`ui/ag_ui/_event_stream.py:434-444`) — not used now.
- `AnthropicModel._add_compaction_params` (`models/anthropic.py:1487-1506`) adds beta `compact-2026-01-12` for
  any `CompactionPart` in history; `OpenAIChatModel` drops it (`models/openai.py:1822-1824`). Hence strip all.
- `UsageLimits.check_before_request(usage)` (`usage.py:568`); the graph checks before the wrap (`_agent_graph.py:1835`).
  For decision 5's `request_limit - 1` case, check a copy with `requests + 1` before the summary request.
  `RunUsage.incr(RequestUsage)` adds tokens, not `requests`.
- `ModelHTTPError(status_code, model_name, body=None)` in `pydantic_ai.exceptions`. `Model.request(messages,
  model_settings, model_request_parameters)`; `ModelRequestParameters()` = no tools; `ModelSettings(max_tokens=N)`.
- `FunctionModel(function=None, *, stream_function=None)`: the summary request is non-streamed, so test models
  need **both** `function=` and `stream_function=`; `AgentInfo.function_tools` and `.model_settings` show tools
  and `max_tokens`. Emitting `CustomEvent` from a capability raises `UserError` (`_run_context.py:816-823`),
  so the marker goes through a per-run queue in `RunDeps` drained by `Service._events` before each forwarded
  event (spec §5's third option). `RunDeps` is frozen: add `compaction: CompactionRun =
  field(default_factory=CompactionRun)` (mutable inside), defined in `compaction.py` to avoid an import cycle.

## Repo facts for the tasks

- Agent tests: `tests/test_app.py` helpers `config`, `build(tmp_path, model=, **cfg_over)`, `running`,
  `until_status`, `run_body(messages=)`, `post_run`, `terminal`, `log_records`; config tests `tests/test_config.py`
  (`VALID`, `write`). `Config` uses `_Strict` (extra forbid); add `CompactionCfg` with
  `trigger_ratio: float = Field(0.8, gt=0, lt=1)`.
- `fake_agent.py`: `FunctionModel(stream_function=scripted)` (l. 93), behaviour by keyword in the last user
  message (`fail`, `slow`, else tool call then `Turn N: the command ran.`); config inline l. 83–89. Slice 2 adds
  a `compact` keyword, a `function=` for the summary and a small window.
- e2e: `platform/dev/e2e/sessions.py`, `Run.shot()/send()/row()`, `check_*` functions, `--shots`.
- Recorder tests: `lib/recorder.test.ts` (`setup`, `drive`, `onlyRun`; `Scripted` subclass l. 482-490 emits
  `{event, messages, state}`; runtime-path template l. 416-447 with `createCopilotRuntimeHandler` and
  `server.requests[i].body.messages` — the template for task 1's round-trip test). `lib/test-agent.ts` picks
  behaviour by keyword (no custom events). `sessions.ts` has no role validation; `autoTitle` reads user only.
- Ansible: `agent.yaml` is `set_fact agui_agent_config` + `copy` to `{{ spe_frontend_dir }}/agent.yaml`
  (`roles/agui/tasks/main.yml:23-56`); the `limits` dict-expression pattern there handles `null`. Variables in
  `inventory/group_vars/all.yml:182-202` (`spe_webui_model_id` l. 171). `checks.yml` is included by the role and
  by `roles/verify/tasks/main.yml:44-46` (no `agui_agent_config` there: slurp the file).
- Stale texts: agent README *Runs* l. 59–68; ansible README `## Agent frontend (AG-UI)` l. 236–262;
  getting-started `## 4. Configure an instance` table l. 132; chat sessions spec `## 4. The archive` l. 258,
  clarifications l. 422 (bold claim, date and slice, explanation). BACKLOG l. 30–32 already hold the three
  compaction items.

## Slicing (from the spec, with the ruling)

1. Agent: task 1 the round-trip test (chat `npm test`, folds clarification 1); config + Ansible + `checks.yml`;
   `compaction.py` pure parts (estimate, `is_overflow`, transcript, `build_sent`) + `compaction_prompt.md`; the
   capability, proactive + summary + usage + limits; reactive + mocked Anthropic/OpenAI transports; marker
   events, input rewrite, run log, cross-run test, agent README *Runs*; the Haiku summary sample (paid,
   approved) in the handoff.
2. Chat renderer, recorder test, fake agent `compact`, archive `## Compacted` + column, Playwright with
   screenshots, chat sessions spec clarification, early output on the dev VM (window 20000).
3. de.NBI window in `group_vars/all.yml` (vLLM `/v1/models` by hand), docs, decision 13's check.
