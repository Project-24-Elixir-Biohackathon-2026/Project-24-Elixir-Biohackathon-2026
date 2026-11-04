# 2026-11-04: the upstream package branch, start (after the AG-UI via Coder e2e)

**Unit:** `BACKLOG.md` *Next*, *Upstream PR for the AG-UI package*. Starts only once the *AG-UI via Coder* item
(#38 and its step 3) is done: the user, 2026-11-04, "after the tests pass … let's continue".

**Decided with the user (2026-11-04):**
- **One PR, superseding kraatz #9.** `bc5d944` (token cap optional) is part of `main`, so the package carries
  it; two open PRs would conflict on `config.py`, `group_vars/all.yml` and the agent README. The body says
  "Supersedes #9". Order: the user opens the new PR, *then* closes #9 with a pointer to it (our `gh` token
  can't act on kraatz). Then `docs/upstream-ports.md` moves `bc5d944` to the new PR, *Current work*'s #9 line
  becomes the new PR's, and `contrib/agui-token-cap-optional` is deleted.
- The body says testing ran from the fork (the portal builds from kraatz `main` only) and how a reviewer tries
  it before merge: fetch the branch into `~/sperange`, `git checkout FETCH_HEAD`, `spe-apply all`.

**How the branch is cut (checked 2026-11-04 at `62f8458`).** `upstream/main` is an ancestor of our `main` (#39),
so no replay: from `upstream/main`, `git checkout origin/main -- <paths>` for the project files that differ
(`git diff --name-only upstream/main origin/main` minus the guide's exclude list and `AGENTS.md`: 155 files then;
`platform/agui` 90, `platform/dev` 27, `docs/specs` 20, `platform/ansible` 11, the rest 7, incl. three
`__pycache__/*.pyc` deletions). Hand edits: fork-only references in `docs/getting-started.md` (1, the
`denbi-llm-key` note) and the spec's `README.md` (3) and `clarifications.md` (11) — `git grep -nE "the fork's|thodkatz|docs/superpowers|BACKLOG|docs/knowledge|\.methodology|fork PR"`;
upstream `AGENTS.md`'s project rules by hand; the rest of the BACKLOG item's list (stale lines, compaction doc
rewrite, the guide's package-port path). Then the test commands, the e2e checklist on the branch's checkout,
screenshots, push.

**PR text draft** (below): fill the TODOs (screenshots on neutral prompts, never canary names — the de.NBI
check's screenshots show them; the e2e result; test counts), adjust to what the branch carries, then post it
as a fork issue (`docs/guides/contributing-upstream.md`, step 5).

---

<!-- DRAFT 2026-11-04. Not posted yet. TODO markers: fill once the contrib branch is cut and re-tested.
Compare link (once pushed):
https://github.com/kraatz/elixir-biohackathon-2026-test/compare/main...thodkatz:elixir-biohackathon-2026-test:contrib/agui-chat-record-compaction?expand=1
-->

# Title

AG-UI chat: sessions, a server-side conversation record, compaction and /compact

# Body

This brings the AG-UI frontend (`agui` in `spe_frontends`) up to the feature set participants know from
Open WebUI: a sidebar of chat sessions, model-written titles, readable tool calls, and long conversations
that no longer hit the model's context window. Behind the chat, `chat-ui` now **owns the conversation
history**, so a participant can no longer forge earlier turns through the client, and the run archive holds
every AG-UI chat in the same layout as an Open WebUI run.

**Supersedes #9.** Its change (the agent's per-run token cap optional, off by default) is part of this
branch, so the two would conflict; #9 can be closed.

## What changes

### Chat sessions (`copilotkit-chat`)

An Open WebUI-style sidebar: New chat, title search with `tag:` filters, pinned chats first then date
groups, a row menu (rename, pin, tags, hide, delete with confirmation), *Show hidden*, and the open session
in the URL (`?session=`), so a reload reopens it. The sidebar is resizable, and a light/dark toggle sits at
the chat's top right. After a session's first run, the agent writes a 2–4 word title, unless the user has
already renamed the session (`spe_agent_title_generation`).

![Sidebar with sessions, a model-written title and the row menu](https://raw.githubusercontent.com/thodkatz/elixir-biohackathon-2026-test/pr-assets/agui-chat-record-compaction/01-sessions.png)

<!-- TODO shot 01: three or four sessions on neutral prompts, row menu open; light theme -->

### Tool calls shown as in Open WebUI

Each tool call is a card with a status icon, its arguments, and `run_command`'s command as a `$` line.
A failed call has its own state. One model response's calls are grouped under an "Explored …" header.

![Tool-call cards grouped under one header](https://raw.githubusercontent.com/thodkatz/elixir-biohackathon-2026-test/pr-assets/agui-chat-record-compaction/02-tool-calls.png)

<!-- TODO shot 02: e.g. "Run uname -a and df -h /, then summarise in two lines"; group expanded, one card open; dark theme -->

### The conversation record: `chat-ui` owns the history

In AG-UI the client sends the whole conversation with every run, and the agent trusts it. Anyone with the
browser's devtools or `curl` could make up earlier turns, tool calls and tool results, or edit and delete real
ones. The model saw the forgery, and the archive recorded it as if it had happened (new threat entry
**TM-007**, client-fabricated history).

Now `chat-ui` keeps one append-only **journal** per session (`/data/sessions/<uuid>.jsonl` on the
`chat-sessions` volume). Each run is written before the agent is called, and each event as it arrives. From
each request `chat-ui` takes only the new user message and sends the agent the history from its journal.
Anything else the client sent that differs is **ignored and recorded** with its kind (fabricated, edited,
deleted, system). The agent itself stays stateless and unchanged in this respect. A run no longer depends
on the browser tab: closing the tab doesn't cancel it, only the stop button does.

### Compaction and `/compact` (`pydantic-ai-agent`)

When the history nears the model's context window, or the provider rejects a request as too long, the agent
asks the same model for a summary and sends that in place of the older messages. The chat shows a divider,
"Earlier conversation compacted", with the summary behind it, and later runs continue from it. Typing
`/compact` (optionally `/compact <what to keep>`, offered in the slash menu) compacts on demand. Settings:
`spe_agent_compaction_enabled`, `spe_agent_context_window_tokens` (set for the de.NBI model; another model
needs its own value), `spe_agent_compaction_trigger_ratio`, `spe_agent_compaction_summary_max_tokens`.

The per-run `total_tokens_limit` is now unset by default (the change from #9). It summed the tokens of every
request in a run, and each request resends the whole conversation, so a long chat hit 400000 tokens where
Open WebUI, which has no such cap, went on.

![The compaction divider, opened to show the summary](https://raw.githubusercontent.com/thodkatz/elixir-biohackathon-2026-test/pr-assets/agui-chat-record-compaction/03-compact.png)

<!-- TODO shot 03: a few neutral turns, then "/compact keep the commands we ran"; divider expanded; one more question after it -->

### Archive

`archive.yml` copies the journals and the agent's run log from the running containers and stops nothing, so
it works as a backup at any time. Only the final archive in `destroy.yml` first stops `chat-ui`, then the
agent, so that no run is left half-written. Each journal is exported as an Open WebUI chat, and
`write_run.py` renders it as it renders an Open WebUI run. It adds what only the AG-UI record has: a run's
status when it didn't complete, content the client sent that was not used, and a *Compacted* section. With
both frontends on, the AG-UI part of a run goes to `<run>/agui/`. `verify.yml` gains no-cost checks: the
session API answers, and the agent key is in neither the sandbox's environment nor `terminal.env`.

The design, with an acceptance check per decision, is the living spec `docs/specs/2026-10-15-agui-frontend-design/`
(§6 sessions, §13 the record, §14 the archive, §15 `/compact`).

## How to try it

**After merge:** a new workspace from the portal gets it. The portal builds from this repository's `main`.

**Before merge**, in an existing workspace: point the clone at this branch and apply everything.

```bash
cd ~/sperange
git fetch https://github.com/thodkatz/elixir-biohackathon-2026-test.git contrib/agui-chat-record-compaction
git checkout FETCH_HEAD
spe-apply all
```

Then open the AG-UI chat. Things to try: two chats, rename one, tag one; a prompt that runs a few commands;
`/compact`; reload the page; `archive.yml` and its `agui/` folder.

## What ran

All testing so far ran from our fork, since the portal only builds from this repository's `main`:

- **de.NBI instance** created with `create.yml` from our checkout (`spe_repo_url` set to the fork), model
  `qwen3.8-27b`: the all-features browser check (themes, sidebar, New chat, grouped tool calls, model title,
  rename, `/compact`, all again after a reload) passed 17/17, with no errors in the agent or `chat-ui` logs.
  A live `archive.yml` wrote every session, and the renamed chat's Markdown shows its *Compacted* section.
- **Portal workspace** (main template, "All data" preset, both frontends) with `~/sperange` switched to the
  fork and `spe-apply all`: two sessions at once, opening one mid-run from a second tab, stop then send at
  once, New chat, rename, delete, and repeated automatic compactions over a long conversation (with the
  context window lowered to 48000 tokens for the test).
  <!-- TODO: the e2e run still has an open failure (tab B on session A after its run shows 0 user messages);
  fix it or state it, then re-run the checklist against this branch's checkout before posting. -->
- Unit tests on this branch: <!-- TODO fill counts from the branch -->
  `pytest platform/dev/tests` …, the agent's `pytest` …, the promptfoo `pytest` …, chat UI `npm run build`
  and `npm test` …, `validate.py` OK, `ansible-playbook --syntax-check` on create/archive/destroy OK.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
