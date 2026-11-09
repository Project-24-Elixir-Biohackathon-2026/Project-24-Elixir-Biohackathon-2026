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
- **A tab switches sessions freely during its own run** (the living AG-UI spec's clarification 27, built): New chat
  and the rows stay enabled, the left run goes on in its session's agent, and another tab opening the running
  session rejoins it live through `connect`. A check that "switches mid-run" can do either; the rejoin makes one
  `POST …/agent/spe/connect`, which a `track()` of `…/run` alone does not see.
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

## The final archive (step 3), from our checkout

The portal's stop archives from upstream's checkout, which has no AG-UI export yet, so the final archive is tested
on denbi-agui-01 with `create.yml`/`destroy.yml` from our main checkout and `spe_frontends: [openwebui, agui]`
(2026-11-04, #40: 2 Open WebUI chats and 17 AG-UI sessions, 8 with compactions, all agreed).

```bash
# from the repository root of the main checkout
ssh -F ~/.ssh/config -f -N -L 18080:127.0.0.1:8080 -L 13000:127.0.0.1:3000 agent-service-1
python3 docs/knowledge/owui-e2e-chats.py <out>                     # Open WebUI: two chats, one with tools
SPE_HOST=agent-service-1 python3 docs/knowledge/agui-all-features-check.py <out>   # AG-UI: tool run, /compact
# before destroy.yml: what the chat shows (GET /api/sessions/<id>) and the raw journals
mkdir -p <snap>/api <snap>/journals
curl -s http://127.0.0.1:13000/api/sessions > <snap>/sessions.json
for id in $(python3 -c 'import json,sys; print(*[s["id"] for s in json.load(open(sys.argv[1]))])' <snap>/sessions.json); do
  curl -s http://127.0.0.1:13000/api/sessions/$id > <snap>/api/$id.json
  ssh -F ~/.ssh/config agent-service-1 docker exec spe-frontend-chat-ui-1 cat /data/sessions/$id.jsonl > <snap>/journals/$id.jsonl
done
(cd platform/ansible && ansible-playbook playbooks/destroy.yml -e @instances/denbi-agui-01.yml -e spe_confirm_reset=denbi-agui-01 </dev/null)
python3 docs/knowledge/agui-archive-compare.py <snap> /data-share/runs/<run>/agui    # mismatches: 0
```

- **Open WebUI's "what's new" dialog** covers the input on a fresh instance (`<li> … subtree intercepts pointer
  events`, the click retried until the timeout): the driver dismisses it ("Okay, Let's Go!" or Escape).
- **A compaction's summary is in the archived message's `output`**, not its `content` (which is empty); the Markdown
  shows it under `## Compacted`. A comparison of `content` alone reports every compacted session as a mismatch.
  The script compares the `output` message parts (`content` joins them) with the chat's assistant texts, exactly
  and in order; one archived turn holds the several API messages around its tool calls. A substring match
  passes a dropped one-word reply that a later compaction summary quotes.
- **Sessions from earlier deploys stay**: `create.yml` on an existing host keeps the chat's volume, so the archive
  holds them too (17 sessions where this run made 2); the agent's run log counts more runs than the journals (78 vs
  48 here) because it also survives earlier deploys.
- **`destroy.yml` on an existing host left the `spe-frontend` containers** ("No containers left in this instance's
  compose projects"): the reset ran Compose on the resolved compose file, whose directory has no `.env`
  (`COMPOSE_PROFILES`), so `down` saw no service. Fixed in #41 (`compose-symlink-env.md`).
