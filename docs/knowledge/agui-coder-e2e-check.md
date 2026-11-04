# The AG-UI end-to-end check in a Coder workspace

`agui-coder-e2e-check.py` (next to this note) drives the AG-UI chat of a Coder workspace in two headless tabs:
two sessions at once, the other tab opening a session mid-run, stop and send again at once, new / rename /
delete, long conversations until each has several compactions, `/compact` with and without a focus, then
reload and reopen every session and compare the chat with its journal. Paid model calls: a few dozen.

```bash
coder port-forward theo/agui-e2e --tcp 13001:3000 &        # run_in_background in Claude Code
SPE_URL=http://127.0.0.1:13001/ SPE_WS=theo/agui-e2e python3 docs/knowledge/agui-coder-e2e-check.py <out> --turns 16
# after a crash past step 3: --resume <A>,<B>,<C>,<D> skips steps 1-3 and sessions that already compacted enough
```

- **Lower the window first, in the workspace only**: `sed -i 's/context_window_tokens: 262144/context_window_tokens:
  48000/' ~/spe-frontend/agent.yaml && docker compose -p spe-frontend restart agent`. 24000 is too small: one
  tool-heavy run (about 5.5k tokens of system prompt and tools per request) compacts three times and fails "The
  conversation is still too long after compacting it. Start a new chat." (the guard, not a bug). At 48000 a
  `seq 1 3000` turn compacts about every second turn. `spe-apply all` writes the real window back.
- **`coder ssh` cuts a large output short**: one JSON of every journal (3 MB) came back truncated
  (`JSONDecodeError: Unterminated string`). Read one journal at a time and check `wc -c` against the bytes
  received (`journal()` does), or a cut copy silently loses runs (`read_journal` skips a torn last line).
- **The session id is in the URL only once a run has ended**: mid-run, `?session=` is absent. Take it from the
  `threadId` of the page's `POST …/agent/spe/run` (`track()`), as `platform/dev/e2e/sessions.py`'s `live_run` does.
- **A tab cannot switch sessions during its own run** (New chat and the rows are disabled): "switching mid-run"
  means another tab opening the running session.
- **CopilotChat virtualizes the message list**: only the rows near the viewport are in the DOM (`[data-index]`,
  absolutely placed), so `locator(".copilotKitUserMessage").count()` on a long chat scrolled to the bottom says 0
  (runs 2 and 3 failed "B shows A's whole run" on this, not a chat bug). `chat_rows()` scrolls the list's real
  scroller (the inner `overflow-y-auto` divs fit their content) top to bottom and counts each row once; a short
  chat has no `[data-index]` rows and is counted directly. A vague prompt ("the dataset directory") can also end
  in pydantic-ai's `request_limit of 50` (run `failed`): name the path.
- **`/compact` is a run with no user message** (`run_start` with `messages: []`): count user messages without it.
- **The live archive from inside the workspace** needs the creation hand-off, which lives on the portal VM
  (`archive.yml` says "output/cw-…/hosts.yml missing" and archives nothing). Write a local one first:
  `cd ~/sperange/platform/ansible && mkdir -p output/cw-<user>-<ws> && printf 'ssh_target: localhost\nssh_args: ""\n'
  > output/cw-<user>-<ws>/hosts.yml && ansible-playbook playbooks/archive.yml -e @instances/local.yml </dev/null
  && rm output/cw-<user>-<ws>/hosts.yml` (`<user>-<ws>` lowercased, as Coder names the instance); the run lands in
  `/data-share/runs/<time>_cw-<user>-<ws>/agui/` (journals in `agui-journals/`). Its task list shows the final
  archive's "Stop the chat UI" tasks too: they are skipped in a live archive.
- **Port 13000 may be taken** by another session's SSH tunnel to `agent-service-1`: use another port, never kill it.
- **`pkill -f agui-coder-e2e-check.py` kills its own shell** (`pkill-self-match.md`): kill by the PID.
