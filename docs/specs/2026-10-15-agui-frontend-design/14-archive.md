## 14. The archive

`archive.yml` saves an `agui` instance's conversations the way it saves an Open WebUI one: export on the VM,
fetch, write on the controller (`roles/run_archive`). Each journal is exported as an **Open WebUI chat**, which
the existing Open WebUI renderer turns into the same run layout, so both frontends are saved and exported one
way. Decisions 15, 16 and 30 of the [README](README.md#decisions-taken).

Until the record is built, the archive is the chat sessions' as built: `agui-sessions/<uuid>.json` copied from
the volume and rendered by `files/write_agui_run.py` (`index.md` columns `# | Session | Tags | Created | Runs |
State`). Runs archived in that form keep the files written for them; the new renderer does not re-render them.

### Export

`tasks/export.yml`, the block for `spe_frontend == 'agui'`:

1. **Barrier.** Copying files while runs go on gives no consistent bundle: a run finishing after its journal
   was copied would be missing from the archive and then destroyed with the volume. So first
   `docker compose -p spe-frontend stop -t 30 chat-ui`, then `… stop -t 30 agent`. On `SIGTERM` the chat UI
   refuses new runs, stops every run in progress (each ends `cancelled`), waits for the session queue to drain
   and exits (a handler registered in `instrumentation.ts`, `lib/shutdown.ts`; the image sets
   `NEXT_MANUAL_SIG_HANDLE=true`, because Next.js's own handler closes the server and exits without waiting
   for a detached run's last append). The agent, stopped second, has then seen its last request and closed
   its run log. A missing `chat-ui` container fails here, and so does a stop that did not end cleanly: each
   service running before the barrier must have exited 0 (`docker compose ps -a --format
   '{{.Service}} {{.ExitCode}}'`), since a drain timeout (the chat UI exits 1) or a kill after `-t 30` (137)
   leaves `stop` itself at rc 0. A service already stopped before the barrier keeps an old exit code, so it
   is not checked. The containers are started again either way.
2. **Copy** from the stopped containers: `docker compose -p spe-frontend cp chat-ui:/data/sessions
   <tmp>/agui-journals` (always present: the image creates it, §6) and `… cp
   agent:/var/lib/spe-agent/runs.jsonl <tmp>/agent-runs.jsonl`. Only an absent run log is tolerated (no run
   reached the agent yet): the copy's own `Could not find the file` error is accepted, since the stopped
   agent cannot be asked whether the file exists; any other copy error fails the export.
3. **Export** the copied journals with the exporter from the `chat-ui` image, in a one-off container, into
   the bundle below.
4. **Restart** both (`docker compose -p spe-frontend start agent chat-ui`), so `archive.yml` run on its own
   leaves a working instance; under `destroy.yml` they are removed right after.
5. Pack `<tmp>` and fetch it to `{{ spe_output_dir }}/archive-bundle-agui.tar.gz`, remove both copies from
   the VM. The fetched bundle is removed after writing, like `archive-bundle.json`.

Every journal is exported, hidden and deleted included. The containers are still up when `archive.yml` starts
(`destroy.yml` imports it first; the Coder stop runs `destroy.yml`). If any step fails, `archive.yml` fails
and `destroy.yml` deletes nothing, as for Open WebUI.

### The Open WebUI chat

The exporter writes the bundle `write_run.py` already reads for Open WebUI (`{chats: [...], tags: [...],
notes: []}`), one chat per session, using the rebuild of §13:

- `title`, `created_at`, `updated_at`, `archived` (the session is hidden), `meta.tags`, and
  `meta.spe_deleted_at` for a deleted session;
- `chat.history.messages`: every message of every branch, keyed by id, with `parentId` and `childrenIds`;
  `chat.history.currentId`: the exported assistant message of the tip's run (each run is folded into one, below);
- a user message as Open WebUI's: `role`, `content`;
- **one assistant message per run**, parent the run's last new user message (the anchor, for a run that
  added none), with `output` items in the order
  their first event arrived, in v0.11.3's shapes (`utils/middleware.py`, `utils/ask_user.py`): a text message as
  `{type: "message", id, role: "assistant", content: [{type: "output_text", text}]}`, a tool call as
  `{type: "function_call", id, call_id, name, arguments}` (`arguments` a JSON string), a tool result as
  `{type: "function_call_output", id, call_id, output: [{type: "input_text", text}]}`, reasoning as
  `{type: "reasoning", id, content}`, each with `status: "completed"`; a compaction marker as a `message` item
  keeping its id; `content` is the run's text joined. These are the items Open WebUI itself replays to a model
  (`MESSAGE_REPLAY_KEYS`, `process_messages_with_output`), so the export is a chat Open WebUI could continue;
- `spe_run` on that assistant message (`run_id`, `status`, `started_at`, `ended_at`), and `spe_ignored` (the
  run's ignored content) on it too, so a refused run still has a message to carry what it was sent.

Fields starting with `spe_` are ours; Open WebUI itself never writes them, so its own runs render as before.

### Write

`tasks/write.yml` unpacks the bundle and runs `files/write_run.py` on it, as for an Open WebUI run:

```
<run dir>/
  run.yml                     as for every run
  index.md                    chats table, as for Open WebUI; says that the AG-UI frontend has no run report
  chats/NN-<slug>.md          the active branch along currentId: user and assistant text, each tool call with
                              fenced arguments and result, plus the three additions below
  chats/NN-<slug>.json        the exported chat
  agui-journals/<uuid>.jsonl  the raw journals, untouched
  agent-runs.jsonl            the agent's run log, when a run reached it
```

`write_run.py` also renders the three things only the AG-UI record has (decision 16): a run's status when it
is not `completed`; its ignored content as a block "sent by the client, not used", with its kind and the
content fenced, between the turns it was sent with; and a compaction marker as a "Compacted" section. Fences
are one backtick longer than the longest run of backticks in the content (at least three). A bundle with no
chats gives an `index.md` saying no session was recorded; without `agent-runs.jsonl` the index says no run
reached the agent. Given an archived run directory, the script re-renders it in place. Open WebUI runs render
as before.

The run directory's AG-UI files contain canaries, like the run log: they are outside git and **not**
shareable, as `canaries.json` is.
