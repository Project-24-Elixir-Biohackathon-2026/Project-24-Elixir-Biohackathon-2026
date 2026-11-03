# Slice 2/3: the chat and the archive show a compaction (early output)

Delivers what a person sees of a compaction: the chat renders the agent's marker (an assistant text message whose
id starts with `spe-compaction-`) as a divider with the summary in a collapsed `<details>`; the session record
keeps it (pinned by a recorder test); the scripted agent can be made to compact; the archive renders it as a
`## Compacted` section and counts compactions in `index.md`; Playwright checks it live and after a reload, light
and dark. It ends with the **early output**: a dev VM session on Haiku with `context_window_tokens: 20000`, run
until it compacts, whose screenshots, archived `chats/NN-*.md` and run-log `compactions` go into the PR for the
user to look at.

**Implements:** spec [`2026-11-03-agui-compaction-design.md`](../../specs/2026-11-03-agui-compaction-design.md)
§6, §7, *Early output*, *Inputs for the plan* (the chat sessions spec clarification). Decisions **8** (task 4
`check_compaction`, screenshots), **9** (task 1, the recorder test), **10** (task 3 `test_agui_run_compaction_*`),
**12**'s `verify.yml` part (task 5, step 3). Slice 1 already folded clarification 1, so the spec's decision 7, §6
and §7 speak of the assistant-message marker; read them as rewritten there.

**Review Focus** (plan README): item 4's chat half is task 1's second recorder test (a run stopped after the
marker is `cancelled` and keeps it); item 5 is task 3's `SUMMARY` with a backtick run and `## Not a section`.
Items 1–3 are slice 1's; nothing else here needs a case of its own.

**Branch:** `impl/agui-compaction-2-chat-archive`, from `main` after slice 1 merged. Global constraints, shared
interfaces, the ruling and Review Focus: [plan README](README.md). Paths are relative to the repository root
unless a step `cd`s; `CHAT` means `platform/agui/copilotkit-chat`, `AGENT` `platform/agui/pydantic-ai-agent`,
`ARCHIVE` `platform/ansible/roles/run_archive/files`.

**Verified facts this slice builds on** (read in `CHAT/node_modules` and the repo, 2026-11-03):

- `CopilotChat` takes `messageView` as a slot: a component, a class name, or a partial props object
  (`SlotValue`, `@copilotkit/react-core` 1.79 `dist/copilotkit-*.d.mts:669-674`). `CopilotChatMessageView`'s
  slots include `assistantMessage: typeof CopilotChatAssistantMessage` (l. 1211). So
  `messageView={{ assistantMessage: X }}` replaces the component used for every assistant message.
- `typeof CopilotChatAssistantMessage` carries static parts (`MarkdownRenderer`, `Toolbar`, the buttons; its
  `declare namespace`, l. 853-870), so a plain function is not assignable to the slot: the replacement copies
  them with `Object.assign` and is typed as `typeof CopilotChatAssistantMessage`. Its props
  (`CopilotChatAssistantMessageProps`, l. 801-828) include `message: AssistantMessage`.
- The chat's colours are CSS variables on `:root` in `CHAT/app/globals.css` (l. 9 on, dark under
  `@media (prefers-color-scheme: dark)` l. 95): `--text`, `--text-secondary`, `--text-muted`, `--line`.
- `npm test` runs `node --test 'lib/*.test.ts'` with type stripping: only `lib/` is unit-tested; a `.tsx`
  component is checked by `npm run build` and Playwright.
- `lib/test-agent.ts` gains a `compact` keyword in slice 1, task 1: after `RUN_STARTED` it sends the marker
  (`spe-compaction-<runId>`, content `SUMMARY of the earlier turns`) and then continues with the other keywords
  (`hang` returns without a terminal event).
- `fake_agent.py`'s model is `FunctionModel(stream_function=scripted)`; the agent's streamed requests use
  `stream_function`, and the capability's summary request (`request_context.model.request`, not streamed) uses
  `function`, which it lacks today. Its config is inline (`Config.model_validate`, l. 83–89).
- `write_agui_run.py` renders messages in `render_messages` (l. 92–131: text roles, tool calls with results in
  `<details>`, any other role as JSON) and the index rows at l. 220–227, header l. 241; `fence` is
  `write_run.py:46` (one backtick longer than the longest run inside, at least three).
- `platform/dev/e2e/sessions.py`: `Run.shot/send/row/files`, `check_*` functions, `--shots`, `--color-scheme`,
  `--scenario` from `LOCAL = ("all", "stop")` and `INSTANCE` (with `--url` and `--compose-file`), l. 760–761.
- The dev VM's private instance file is `platform/ansible/instances/dev-local.yml` in the main checkout
  (Haiku, `spe_agent_allowed_models: [claude-haiku-5-5]`); slice 1 added `spe_agent_context_window_tokens` with
  default `null` in `inventory/group_vars/all.yml`.

---

### Task 1: the divider in the chat, and the record keeps the marker

**Files:**
- Create: `CHAT/lib/compaction.ts`, `CHAT/lib/compaction.test.ts`, `CHAT/app/compaction-divider.tsx`
- Modify: `CHAT/app/page.tsx` (imports l. 6–22; `<CopilotChat>` l. 272–285), `CHAT/app/globals.css` (append)
- Test: `CHAT/lib/recorder.test.ts` (two tests)

**Interfaces:**
- Consumes: the marker's form (README, *The marker on the wire*); `lib/test-agent.ts`'s `compact` keyword
  (slice 1, task 1); `setup`, `drive`, `input`, `settled`, `onlyRun` in `recorder.test.ts`.
- Produces: `MARKER_PREFIX`, `isCompactionMarker(message)`; `AssistantOrCompaction`,
  `CompactionDivider({ summary })`; CSS classes `.spe-compaction`, `.spe-compaction-rule`,
  `.spe-compaction-label`, `.spe-compaction-summary` (task 4's Playwright selects on them).

- [ ] **Step 1: write the failing unit test.** Create `CHAT/lib/compaction.test.ts`:

```ts
// What counts as the agent's compaction marker: the same rule as the agent's input rewrite.
import { test } from "node:test";
import assert from "node:assert/strict";
import { MARKER_PREFIX, isCompactionMarker } from "./compaction.ts";

test("an assistant text message with the prefix is a marker", () => {
  assert.equal(MARKER_PREFIX, "spe-compaction-");
  assert.equal(isCompactionMarker({ id: "spe-compaction-1", role: "assistant", content: "summary" }), true);
  assert.equal(isCompactionMarker({ id: "spe-compaction-1", role: "assistant", content: "" }), true);
});

test("anything else is an ordinary message", () => {
  for (const message of [
    { id: "a1", role: "assistant", content: "spe-compaction- in the text" },
    { id: "spe-compaction-1", role: "user", content: "a participant's id" },
    { id: "spe-compaction-1", role: "assistant", content: [{ type: "text", text: "parts" }] },
    { id: "spe-compaction-1", role: "assistant", content: "x", toolCalls: [{ id: "c1" }] },
    { id: "spe-compaction-1", role: "assistant" },
    { role: "assistant", content: "no id" },
  ]) {
    assert.equal(isCompactionMarker(message), false, JSON.stringify(message));
  }
  assert.equal(isCompactionMarker({ id: "spe-compaction-1", role: "assistant", content: "x", toolCalls: [] }), true);
});
```

- [ ] **Step 2: write the failing recorder test.** Append to `CHAT/lib/recorder.test.ts`:

```ts
test("a compacting run: the marker is stored in order, the file stays version 1, the title is the user's", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    const out = await drive(recorder, input(id, "compact the conversation"), agent());
    assert.equal(types(out).at(-1), EventType.RUN_FINISHED);
    const [record, run] = await onlyRun(store, id);
    assert.equal(run.status, "completed");
    assert.equal(record.version, 1);
    assert.deepEqual([record.title, record.title_source], ["compact the conversation", "auto"]);
    assert.deepEqual(record.messages.map((m) => [m.role, m.id.startsWith("spe-compaction-"), m.content]), [
      ["user", false, "compact the conversation"],
      ["assistant", true, "SUMMARY of the earlier turns"],
      ["assistant", false, "echo: compact the conversation"],
    ]);
  } finally {
    await server.close();
  }
});

test("a compacting run stopped after the marker: cancelled, the marker kept", async () => {
  const { store, server, recorder, agent } = await setup();
  try {
    const id = randomUUID();
    await drive(recorder, input(id, "compact and hang"), agent(),
      (e) => e.type === EventType.TEXT_MESSAGE_END && String((e as { messageId?: string }).messageId).startsWith("spe-compaction-"));
    await settled(id);
    const [record, run] = await onlyRun(store, id);
    assert.equal(run.status, "cancelled");
    // Only the marker is asserted: a reply's start can arrive in the same chunk as the marker's end.
    assert.ok(record.messages.some((m) => m.role === "assistant" && String(m.id).startsWith("spe-compaction-")
      && m.content === "SUMMARY of the earlier turns"));
  } finally {
    await server.close();
  }
});
```

  The first test's third message is whatever the test agent answers after its keywords; read
  `lib/test-agent.ts` and use its actual reply text (the RUN_FINISHED test at l. 92 shows `echo: <text>`).

- [ ] **Step 3: run them to see them fail.** `(cd CHAT && npm test)`. Expected: `compaction.test.ts` fails on the
  missing module; the recorder tests pass already (the recorder stores what the run ends with; they pin it,
  decision 9). If a recorder test fails, read the failure before going on: the record is the marker's only store.

- [ ] **Step 4: the module.** Create `CHAT/lib/compaction.ts`:

```ts
// The agent marks a compaction with an assistant text message whose id has this prefix; its content is the
// summary the model continues from. The agent rewrites only such plain text messages into its cut point.
export const MARKER_PREFIX = "spe-compaction-";

export function isCompactionMarker(message: {
  id?: string; role?: string; content?: unknown; toolCalls?: unknown[];
}): boolean {
  return message.role === "assistant" && typeof message.id === "string" && message.id.startsWith(MARKER_PREFIX)
    && typeof message.content === "string" && !message.toolCalls?.length;
}
```

- [ ] **Step 5: run the tests.** `(cd CHAT && npm test)`. Expected: all pass.

- [ ] **Step 6: the divider.** Create `CHAT/app/compaction-divider.tsx`:

```tsx
"use client";

import { CopilotChatAssistantMessage } from "@copilotkit/react-core/v2";
import type { ComponentProps } from "react";
import { isCompactionMarker } from "../lib/compaction.ts";

// The summary is React text, never Markdown or HTML: it is model output over tool output.
export function CompactionDivider({ summary }: { summary: string }) {
  return (
    <div className="spe-compaction">
      <div className="spe-compaction-rule">
        <span className="spe-compaction-label">Earlier conversation compacted</span>
      </div>
      <details className="spe-compaction-summary">
        <summary>Summary the model continues from</summary>
        <div>{summary}</div>
      </details>
    </div>
  );
}

function render(props: ComponentProps<typeof CopilotChatAssistantMessage>) {
  if (isCompactionMarker(props.message)) {
    return <CompactionDivider summary={props.message.content as string} />;
  }
  return <CopilotChatAssistantMessage {...props} />;
}

// The slot is typed as CopilotKit's component with its static parts, so ours carries them too.
export const AssistantOrCompaction = Object.assign(render, CopilotChatAssistantMessage) as
  typeof CopilotChatAssistantMessage;
```

  If `ComponentProps<typeof CopilotChatAssistantMessage>` does not type-check, import the props type
  `CopilotChatAssistantMessageProps` from `@copilotkit/react-core/v2` instead (exported in 1.79).

- [ ] **Step 7: use it.** In `CHAT/app/page.tsx`, add `import { AssistantOrCompaction } from "./compaction-divider";`
  beside `./chat-header`, and at module scope, after the imports and before the first function:

```tsx
// A stable object: CopilotChat re-renders its message view when the slot value changes identity.
const MESSAGE_VIEW = { assistantMessage: AssistantOrCompaction };
```

  and pass `messageView={MESSAGE_VIEW}` to `<CopilotChat>` after `className="spe-chat"`.

- [ ] **Step 8: the styles.** Append to `CHAT/app/globals.css`:

```css
/* A compaction: a full-width rule with its label, the summary collapsed under it. */
.spe-compaction {
  margin: 1.5rem 0;
  font-size: 0.8125rem;
  color: var(--text-muted);
}
.spe-compaction-rule {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.spe-compaction-rule::before,
.spe-compaction-rule::after {
  content: "";
  flex: 1;
  border-top: 1px solid var(--line);
}
.spe-compaction-summary {
  margin-top: 0.5rem;
}
.spe-compaction-summary > summary {
  cursor: pointer;
  width: fit-content;
  margin: 0 auto;
}
.spe-compaction-summary > div {
  margin-top: 0.5rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
}
```

- [ ] **Step 9: build and test, then commit.** `(cd CHAT && npm ci && npm test && npm run build)`. Expected: all
  pass, the build's type check included.

```bash
git add platform/agui/copilotkit-chat/lib/compaction.ts platform/agui/copilotkit-chat/lib/compaction.test.ts \
  platform/agui/copilotkit-chat/app/compaction-divider.tsx platform/agui/copilotkit-chat/app/page.tsx \
  platform/agui/copilotkit-chat/app/globals.css platform/agui/copilotkit-chat/lib/recorder.test.ts
git commit -s -m "Chat: render the agent's compaction marker as a divider

The marker is an assistant text message with id prefix spe-compaction-; the
assistant-message slot shows it as a rule and a collapsed summary, as text.
The recorder tests pin that the session record keeps it, also when stopped."
```

---

### Task 2: the scripted agent compacts on `compact`

**Files:**
- Modify: `platform/dev/fake_agent.py`

**Interfaces:**
- Consumes: `spe_agent.compaction.FRAME`, `SUMMARY_PROMPT` (slice 1); the real `Compaction` capability, which
  `create_app` adds when `compaction.enabled`.
- Produces: a user message containing `compact` makes the next model request compact (task 4's Playwright and
  any manual check); the scripted summary is `Scripted summary of N characters of conversation. The latest
  request was: <the transcript's last line holding "compact">`; after the compaction the answer is
  `Turn N: the command ran. The conversation was compacted.`

- [ ] **Step 1: write the change.** In `fake_agent.py`:
  - extend the docstring's behaviour list with: `a message containing "compact" runs a command with a long
    output, so the history passes the scripted window (COMPACT_WINDOW tokens) and the agent compacts it with a
    scripted summary;`
  - imports: add `ModelResponse, SystemPromptPart, TextPart` to the `pydantic_ai.messages` import, and
    `from spe_agent.compaction import FRAME, SUMMARY_PROMPT`;
  - constants beside `SLOW_STEPS`:

```python
# The 16 tool definitions alone estimate ≈ 3,000 tokens (slice 1's verified facts), so an ordinary turn is
# ≈ 3,100, under the trigger (0.8 × 8000 = 6,400). The long output is cut to the agent's 16,384-byte tool cap,
# ≈ 5,460 tokens, which takes the next request to ≈ 8,500, past it.
COMPACT_WINDOW = 8000        # tokens
LONG_OUTPUT_CHARS = 20_000   # more than the tool cap, so the cut, not this number, sets the size
```

  - in `fake_sandbox`, inside `if path == "/execute":`, before the ordinary response:

```python
        if cmd.startswith("print-long-output"):
            return httpx.Response(200, json={"id": "p1", "status": "done", "exit_code": 0,
                                             "output": f"$ {cmd}\n" + "x" * LONG_OUTPUT_CHARS})
```

  - the summary request (non-streamed, so `FunctionModel` calls `function`):

```python
def summarise(messages, info) -> ModelResponse:
    """The compaction's summary request: system prompt SUMMARY_PROMPT, the transcript as the user part."""
    parts = messages[0].parts
    assert isinstance(parts[0], SystemPromptPart) and parts[0].content == SUMMARY_PROMPT, "not a summary request"
    text = str(parts[-1].content)
    latest = next((line for line in reversed(text.splitlines()) if "compact" in line.lower()), "")
    return ModelResponse(parts=[TextPart(
        f"Scripted summary of {len(text)} characters of conversation. The latest request was: {latest.strip()}")])
```

  - in `scripted`, count turns without the framed summary, and answer once the history was compacted:

```python
async def scripted(messages, info):
    users = [str(p.content) for m in messages if isinstance(m, ModelRequest)
             for p in m.parts if isinstance(p, UserPromptPart) and not str(p.content).startswith(FRAME)]
    last_user = users[-1] if users else ""
    if "fail" in last_user.lower():
        raise RuntimeError("scripted model failure (the message asked for it)")
    last = messages[-1].parts[-1]
    compacting = "compact" in last_user.lower()
    if compacting and isinstance(last, UserPromptPart) and any(
            isinstance(p, UserPromptPart) and str(p.content).startswith(FRAME)
            for m in messages if isinstance(m, ModelRequest) for p in m.parts):
        # The agent compacted after the long output: the request holds the summary and the latest request.
        yield f"Turn {len(users)}: the command ran. The conversation was compacted."
        return
    if isinstance(last, ToolReturnPart):
        ...  # unchanged: slow steps, then the "Turn N: the command ran." answer
    else:
        command = f"print-long-output turn {len(users)}" if compacting else f"echo turn {len(users)}"
        yield {0: DeltaToolCall(name="run_command", json_args=json.dumps({"command": command}),
                                tool_call_id=f"call-{len(users)}")}
```

  - in `main`, the config gains `"compaction": {"context_window_tokens": COMPACT_WINDOW},` and the model becomes
    `FunctionModel(summarise, stream_function=scripted)`.

  `len(users)` after an in-run compaction counts only the latest request, so the answer reads `Turn 1` there;
  task 4 matches on the text after the number.

- [ ] **Step 2: try it by hand.** Start it and send one run with `curl`:

```bash
(cd platform/agui/pydantic-ai-agent && uv run --group dev python ../../dev/fake_agent.py --port 18100 --key k \
  --run-log /tmp/fake-runs.jsonl) &
sleep 3
curl -sN http://127.0.0.1:18100/agent -H 'Authorization: Bearer k' -H 'content-type: application/json' \
  -d '{"threadId":"t","runId":"r","state":{},"tools":[],"context":[],"forwardedProps":{},
       "messages":[{"id":"u1","role":"user","content":"compact <b>now</b>"}]}' | grep -o '"type":"[A-Z_]*"\|spe-compaction-[0-9a-f-]*\|Scripted summary[^"]*\|The conversation was compacted' 
tail -1 /tmp/fake-runs.jsonl | python3 -c 'import json,sys; print(json.load(sys.stdin)["compactions"])'
kill %1
```

  Expected: `TOOL_CALL_*`, then `TEXT_MESSAGE_START` with an `spe-compaction-…` id and `Scripted summary of …
  The latest request was: …compact <b>now</b>…`, then the answer `… The conversation was compacted.` and
  `RUN_FINISHED`; the run log's `compactions` has one entry with `trigger: "threshold"`. The latest-request line
  depends on how slice 1's `transcript` labels entries; whatever its form, it must contain the user's text.
  A plain `echo` message (`"content":"hello"`) still gives `Turn 1: the command ran.` with no marker.

- [ ] **Step 3: the existing checks still pass.**
  `(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)` (the agent's tests do not import
  `fake_agent.py`, but its imports come from there). Then commit:

```bash
git add platform/dev/fake_agent.py
git commit -s -m "Fake agent: a message containing 'compact' makes the agent compact

A long command output passes a small scripted window; the summary request gets
a scripted summary that quotes the latest request, so the chat and the archive
can be checked without a model."
```

---

### Task 3: the archive renders `## Compacted` and counts compactions

**Files:**
- Modify: `ARCHIVE/write_agui_run.py` (`render_messages` l. 92–131; index rows l. 220–227 and header l. 241)
- Test: `platform/dev/tests/test_write_agui_run.py`

**Interfaces:**
- Consumes: the marker's form in the session record (README, *The marker on the wire*); `fence` from `write_run`.
- Produces: `is_compaction(message: dict) -> bool`; the section `## Compacted`, the line `From here the model saw
  this summary instead of the messages above.`, the summary in a fence; `index.md` columns
  `| # | Session | Tags | Created | Runs | Compactions | State |`.

- [ ] **Step 1: write the failing tests.** In `platform/dev/tests/test_write_agui_run.py`, update the index test
  for the new column (each row gains `| 0 ` before its state):

```python
    assert "| 01 | [List the home directory](chats/01-list-the-home-directory.md) | exfil, dns " \
           "| 2026-10-29 10:02 UTC | 1 | 0 | active |" in index
    assert "| 02 | [Read <img src=x onerror=alert(1)>](chats/02-read-img-src-x-onerror-alert-1.md) | - " \
           "| 2026-10-29 10:05 UTC | 1 | 0 | hidden |" in index
    assert r"| 03 | [Try \| the \[pipe\]](chats/03-try-the-pipe.md) | - | 2026-10-29 10:09 UTC | 1 " \
           "| 0 | deleted 2026-10-29 10:20 UTC |" in index
```

  and append:

```python
SUMMARY = "The user listed files.\n## Not a section\n````\nfour ticks\n``````\nsix ticks\n<img src=x onerror=alert(1)>"


def marker(n, content=SUMMARY, **extra):
    return {"id": f"spe-compaction-{n}", "role": "assistant", "content": content, **extra}


def compaction_bundle(tmp_path, messages):
    b = tmp_path / "bundle"
    (b / "sessions").mkdir(parents=True)
    (b / "sessions" / f"{ACTIVE}.json").write_text(json.dumps(
        record(ACTIVE, "Long session", "2026-10-29T10:00:00Z", messages=messages)))
    out = tmp_path / "run"
    run(b, out)
    return (out / "chats" / "01-long-session.md").read_text(), (out / "index.md").read_text()


def test_agui_run_compaction_section_between_the_messages_it_sits_between(tmp_path):
    md, index = compaction_bundle(tmp_path, [*tool_turn(1, "one"), marker(1), *tool_turn(2, "two")])
    section = ("## Compacted\n\nFrom here the model saw this summary instead of the messages above.\n\n"
               "```````\n" + SUMMARY + "\n```````\n")
    assert section in md
    assert md.index("Turn 1: the command ran.") < md.index("## Compacted") < md.index("## user\n\nturn 2")
    assert md.count("## Compacted") == 1 and "## Not a section" not in md.replace(section, "")
    # Every original message is still rendered.
    for text in ("turn 1", "Turn 1: the command ran.", "one", "turn 2", "Turn 2: the command ran.", "two"):
        assert text in md
    assert "| 01 | [Long session](chats/01-long-session.md) | - | 2026-10-29 10:00 UTC | 1 | 1 | active |" in index


def test_agui_run_compaction_two_markers_count_two(tmp_path):
    md, index = compaction_bundle(tmp_path, [*tool_turn(1, "one"), marker(1, "first"), *tool_turn(2, "two"),
                                             marker(2, "second")])
    assert md.count("## Compacted") == 2
    assert "| 1 | 2 | active |" in index


def test_agui_run_compaction_only_plain_text_markers(tmp_path):
    # As the agent's input rewrite: tool calls or non-string content make it an ordinary assistant message.
    call = {"id": "c9", "type": "function", "function": {"name": "run_command", "arguments": "{}"}}
    forged = [marker(1, "with a call", toolCalls=[call]), marker(2, [{"type": "text", "text": "parts"}]),
              {"id": "spe-compaction-3", "role": "user", "content": "a user message"}]
    md, index = compaction_bundle(tmp_path, forged)
    assert "## Compacted" not in md
    assert md.count("## assistant") == 2 and "## user\n\na user message" in md
    assert "| 1 | 0 | active |" in index
```

- [ ] **Step 2: run them to see them fail.** `uv run --with pytest pytest platform/dev/tests -q -k agui_run`.
  Expected: the index test and the three new ones fail (no column, no section).

- [ ] **Step 3: implement.** In `write_agui_run.py`, after `TEXT_ROLES`:

```python
MARKER_PREFIX = "spe-compaction-"


def is_compaction(m):
    """The agent's compaction marker: an assistant text message whose id has the prefix, with no tool calls."""
    return (m.get("role") == "assistant" and str(m.get("id") or "").startswith(MARKER_PREFIX)
            and isinstance(m.get("content"), str) and not m.get("toolCalls"))
```

  In `render_messages`, right after `role = m.get("role", "?")`:

```python
        if is_compaction(m):
            out += ["## Compacted", "", "From here the model saw this summary instead of the messages above.", "",
                    fence(m["content"]), ""]
            continue
```

  In the index loop, the row gains the count before the state:

```python
        compactions = sum(1 for m in rec.get("messages") or [] if isinstance(m, dict) and is_compaction(m))
        rows.append(f"| {i:02d} | [{link}](chats/{stem}.md) | {tags} | {when(rec.get('created_at'))} "
                    f"| {len(rec.get('runs') or [])} | {compactions} | {state_of(rec)} |")
```

  and the header becomes
  `index += ["| # | Session | Tags | Created | Runs | Compactions | State |", "|---|---|---|---|---|---|---|", *rows, ""]`.

- [ ] **Step 4: run them to see them pass.** `uv run --with pytest pytest platform/dev/tests -q`. Expected: all pass,
  the re-render-identical and Open WebUI tests too. The fence for `SUMMARY` is seven backticks (its longest run
  is six); if `fence` strips a trailing newline differently, adjust the test's `section`, not `fence`.

- [ ] **Step 5: commit.**

```bash
git add platform/ansible/roles/run_archive/files/write_agui_run.py platform/dev/tests/test_write_agui_run.py
git commit -s -m "Archive: render a compaction as '## Compacted' and count them in index.md"
```

---

### Task 4: Playwright, light and dark, and the chat sessions spec clarification

**Files:**
- Modify: `platform/dev/e2e/sessions.py` (`check_compaction`; `LOCAL`; `main`)
- Create: `docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-2/` (screenshots)
- Modify: `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md` (clarification for §4)

**Interfaces:**
- Consumes: task 1's classes and texts; task 2's `compact` keyword and answer text.
- Produces: `check_compaction(r: Run) -> None`, scenario `compaction` (local) and, for the dev VM,
  `compaction-live` (with `--url`), used by task 5.

- [ ] **Step 1: write the check.** In `sessions.py`, add `import re` to the imports, and after `check_deleted_open`:

```python
COMPACTED = "Earlier conversation compacted"
SUMMARY_LINE = "Summary the model continues from"
XSS = "compact <img src=x onerror=window.__speXss=1>"


def check_compaction(r: Run) -> None:
    """A message that makes the scripted agent compact: the divider appears where the compaction was made,
    live and after a reload; the summary is collapsed, and expanded shows its markup as text."""
    page = r.page
    page.get_by_role("button", name="New chat").click()
    expect(page.locator(".spe-header-title")).to_have_text("New chat")
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill(XSS)
    box.press("Enter")
    expect(page.get_by_text("The conversation was compacted.")).to_be_visible(timeout=20_000)
    divider = page.locator(".spe-compaction")
    expect(divider).to_have_count(1)
    expect(divider.locator(".spe-compaction-label")).to_have_text(COMPACTED)
    summary = divider.locator(".spe-compaction-summary")
    expect(summary.locator("> div")).not_to_be_visible()
    r.shot("compaction")
    summary.locator("summary", has_text=SUMMARY_LINE).click()
    expect(summary.locator("> div")).to_contain_text("<img src=x onerror=window.__speXss=1>")
    assert page.evaluate("window.__speXss") is None, "the summary's markup ran"
    assert summary.locator("img").count() == 0
    r.shot("compaction-open")
    # The divider sits between the user's message and the answer that followed the compaction.
    texts = page.locator(".spe-chat").inner_text()
    assert texts.index(XSS) < texts.index(COMPACTED) < texts.index("The conversation was compacted."), texts
    sid = r.url_session()
    rec = r.wait_runs(sid, 1)
    markers = [m for m in rec["messages"] if m["id"].startswith("spe-compaction-")]
    assert [m["role"] for m in markers] == ["assistant"] and "Scripted summary" in markers[0]["content"], rec
    assert rec["title"] == XSS, rec["title"]
    page.reload()
    expect(page.locator(".spe-compaction")).to_have_count(1, timeout=10_000)
    expect(page.get_by_text("The conversation was compacted.")).to_be_visible()
    # A later run in the same session still answers, and the divider stays where it was.
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill("one more")
    box.press("Enter")
    expect(page.get_by_text(re.compile(r"Turn \d+: the command ran\.$"))).to_have_count(1, timeout=20_000)
    expect(page.locator(".spe-compaction")).to_have_count(1)
    r.wait_runs(sid, 2)
    r.ok("compaction: divider in place live and after a reload, summary collapsed and shown as text, record keeps it")
```

  The `$` anchors the later answer apart from the compacted one (`… the command ran. The conversation was
  compacted.`); if `get_by_text` with a regex matches a container rather than the message, narrow it to the
  assistant message's element as `check_view` and `send` do.

- [ ] **Step 2: wire the scenarios.** `LOCAL = ("all", "stop", "compaction")`; in `main`'s local branch, call
  `check_compaction(r)` in `all` after `check_deleted_open(r)`, and for `--scenario compaction` after
  `page.goto(BASE + "/")` (as `stop` does). Then the live one for the dev VM, after `two_turn`:

```python
def compaction_live(r: Run, turns: int = 8) -> None:
    """On an instance with a small window: commands with long output until the agent compacts."""
    page = r.page
    page.goto(BASE + "/")
    page.get_by_role("button", name="New chat").click()
    box = page.get_by_test_id("copilot-chat-textarea")
    for turn in range(1, turns + 1):
        box.fill(f"Turn {turn}: run `seq 1 3000` and tell me only the last line it printed.")
        box.press("Enter")
        # New chat is disabled while a run is in flight (as two_turn waits for a run's end).
        expect(page.get_by_role("button", name="New chat")).to_be_disabled(timeout=10_000)
        expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=120_000)
        if page.locator(".spe-compaction").count():
            break
    expect(page.locator(".spe-compaction")).to_have_count(1)
    r.shot("live-compaction")
    page.locator(".spe-compaction-summary > summary").click()
    r.shot("live-compaction-open")
    print(f"session {r.url_session()}, compacted after {turn} turns")
```

  `INSTANCE = ("stop", "slow-loop", "two-turn", "compaction-live")`, dispatched in the `--url` branch beside
  `two_turn`. It waits for a run's end the way `two_turn` does (sessions.py l. 727–728): New chat disabled,
  then enabled.

- [ ] **Step 3: run it, light and dark.** `(cd CHAT && npm ci && npm run build)`, then

```bash
E=docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-2
python3 platform/dev/e2e/sessions.py --scenario compaction --shots $E/light --color-scheme light
python3 platform/dev/e2e/sessions.py --scenario compaction --shots $E/dark --color-scheme dark
python3 platform/dev/e2e/sessions.py
```

  Expected: `ok - compaction: …` twice, and the whole `all` run passes. Open the four screenshots
  (`01-compaction.png`, `02-compaction-open.png` per scheme) with the Read tool: the rule and label are legible in
  both schemes, the summary is collapsed, then shows the `<img …>` line as text. Keep only those four files under
  `evidence/slice-2/{light,dark}/`.

- [ ] **Step 4: the chat sessions spec clarification.** In
  `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`, *Clarifications*, add the next number, in
  the existing form:

```markdown
N. **The archive renders the agent's compaction marker as a section, and `index.md` counts them** (2026-11-03;
   AG-UI compaction, slice 2/3). An assistant text message whose id starts with `spe-compaction-` is rendered
   as `## Compacted`, the line "From here the model saw this summary instead of the messages above." and the
   summary in a fence; `index.md`'s columns become `# | Session | Tags | Created | Runs | Compactions | State`.
   *Reason:* the agent compacts a conversation that no longer fits the model's context and marks the point in
   the session's messages (`docs/superpowers/specs/2026-11-03-agui-compaction-design.md`, §7, clarification 1).
   *Amends:* §4 (archive layout, `index.md` columns). *Status:* folded.
```

  and in §4 itself, where `index.md`'s columns are listed (l. 258 on), add `Compactions` before the state and one
  sentence: "A compaction marker is rendered as a `## Compacted` section (clarification N)."

- [ ] **Step 5: commit.**

```bash
git add platform/dev/e2e/sessions.py docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-2 \
  docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md
git commit -s -m "e2e: check the compaction divider live and after a reload, light and dark

Also the chat sessions spec's clarification for the archive's Compacted section."
```

---

### Task 5: the early output on the dev VM, the handoff, the PR

Paid: Haiku on the dev VM, approved for this work (README, *Global Constraints*); about 8 turns of ~10k input
tokens, under $0.10. No cloud instance is created or destroyed.

**Files:**
- Modify (not committed): `platform/ansible/instances/dev-local.yml` in the main checkout
- Create: `docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-2/live/` (screenshots, the archived chat)
- Create: the handoff in `handoffs/`
- Modify: the README's slices table, `AGENTS.md` *Current work*

- [ ] **Step 1: give the dev VM a window.** In the main checkout's `platform/ansible/instances/dev-local.yml`
  (private, ignored by git), add `spe_agent_context_window_tokens: 20000`. Redeploy in place from the main
  checkout with this worktree's agent and chat:

```bash
cd /workspace/biohackathon/biohackathon/elixir-biohackathon-2026-test/platform/ansible
ansible-playbook playbooks/create.yml -e @instances/dev-local.yml \
  -e spe_agui_source_dir=$PWD/../../.claude/worktrees/impl-agui-compaction-2-chat-archive </dev/null
```

- [ ] **Step 2: run the session.** With the chat UI's URL and compose file as `docs/getting-started.md` gives
  them for this instance:

```bash
python3 platform/dev/e2e/sessions.py --url http://127.0.0.1:3000 --compose-file <the frontend's docker-compose.yml> \
  --scenario compaction-live --shots docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-2/live
```

  Expected: `compacted after N turns` with N about 3 (20000 × 0.8 = 16000 tokens; each `seq 1 3000` adds about
  5000). If it never compacts in 8 turns, read the run log's estimates before changing anything: the trigger or
  the estimate is wrong, and that is a slice 1 bug to fix here with a test.

- [ ] **Step 3: verify and archive.**
  `ansible-playbook playbooks/verify.yml -e @instances/dev-local.yml </dev/null`: the new task shows the rendered
  `compaction` block with `context_window_tokens: 20000` (decision 12). Then
  `ansible-playbook playbooks/archive.yml -e @instances/dev-local.yml </dev/null` and, in the output directory it
  prints, read `index.md` (the session's row has `Compactions` 1), the session's `chats/NN-*.md` (the
  `## Compacted` section where the divider was) and `agent-runs.jsonl`'s `compactions` (trigger, estimated tokens,
  messages cut, usage, `next_input_tokens` below 20000). Copy the chat's `.md` into `evidence/slice-2/live/`
  only after checking it holds no canary or key (the session ran `seq` only; the system prompt is not in it);
  never copy `canaries.json` or the `.json` record.

- [ ] **Step 4: put the VM back.** Leave `spe_agent_context_window_tokens: 20000` in `dev-local.yml` until
  slice 3's decision 13 check (it uses the same window), and say so in the handoff.

- [ ] **Step 5: handoff, PR, review, merge.** Write the handoff (`handoffs/<UTC stamp>-slice2-merged-start-slice3.md`):
  the early output (screenshot paths, the summary from the run log, the input tokens before and after), any
  ruling, and slice 3's start. Update the slices table's status and the track's line in `AGENTS.md`, *Current
  work*. Open the PR `Chat and archive show a compaction (2/3)` with `gh pr create --repo
  thodkatz/elixir-biohackathon-2026-test --base main`; the body says what ran (`npm test`, `npm run build`, the
  pytest suites, the three Playwright runs, the dev VM session, `verify.yml`), embeds or links the light, dark and
  live screenshots and the archived chat, and **asks the user to look at the early output**: a change they ask
  for (prompt, ratio, rendering) is rewritten into `slice-3-denbi-docs.md` as a task before its docs, in this PR
  or, if it comes after the merge, a follow-up commit on `main` (README, *PR slices*). Then the local review
  round, the merge and the cleanup (`AGENTS.md`, *Development workflow*); the merge does not wait for the user's
  look.
