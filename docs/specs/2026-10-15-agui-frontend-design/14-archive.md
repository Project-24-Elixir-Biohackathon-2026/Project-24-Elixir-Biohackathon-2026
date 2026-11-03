## 14. The archive

`archive.yml` saves an `agui` instance's conversations the way it saves an Open WebUI one: export on the VM,
fetch, write on the controller (`roles/run_archive`). Each journal is exported as an **Open WebUI chat**, which
the existing Open WebUI renderer turns into the same run layout, so both frontends are saved and exported one
way. Decisions 15, 16 and 30 of the [README](README.md#decisions-taken).

As built (clarifications 11 and 14), every archive copies live (decision 30): only the final archive
`destroy.yml` runs keeps step 1's barrier, stopping `chat-ui` then the agent; run on its own, `archive.yml`
interrupts nothing, and the bundle says `spe_archive_mode: live`. Runs archived before the record keep the
files written for them (`agui-sessions/<uuid>.json`, rendered by the renderer of that time); they are not
re-rendered.

### Export

`archive.yml` can run at any time while participants work, as often as wanted, as a backup: it copies the
files while `chat-ui` and the agent keep running, and interrupts nothing. Only the **final archive**, the one
`destroy.yml` runs before it removes the volumes, stops the services first, since a run finishing after that
copy would be lost with the volume. `destroy.yml` imports `archive.yml` with `spe_archive_final: true`; run on
its own, `archive.yml` is live. `destroy.yml` checks its own preconditions (the instance file against the
hand-off, and on an existing VM `spe_confirm_reset`) before that archive, so a destroy it would refuse never
leaves the services stopped.

`tasks/export.yml`, the block for `spe_frontend == 'agui'`:

1. **Barrier, final archive only.** `docker compose -p spe-frontend stop -t 30 chat-ui`, then `… stop -t 30
   agent`. On `SIGTERM` the chat UI refuses new runs, stops every run in progress (each ends `cancelled`),
   waits for the session queue to drain and exits (a handler registered in `instrumentation.ts`,
   `lib/shutdown.ts`; the image sets `NEXT_MANUAL_SIG_HANDLE=true`, because Next.js's own handler closes the
   server and exits without waiting for a detached run's last append). The agent, stopped second, has then
   seen its last request and closed its run log. A stop that did not end cleanly fails the export: each
   service running before the barrier must have exited 0 (`docker compose ps -a --format
   '{{.Service}} {{.ExitCode}}'`), since a drain timeout (the chat UI exits 1) or a kill after `-t 30` (137)
   leaves `stop` itself at rc 0. A service already stopped before the barrier keeps an old exit code, so it
   is not checked. The services are not started again: `destroy.yml` removes them next. A live archive skips
   this step.
2. **Copy** `docker compose -p spe-frontend cp chat-ui:/data/sessions <tmp>/agui-journals` (always present:
   the image creates it, §6) and `… cp agent:/var/lib/spe-agent/runs.jsonl <tmp>/agent-runs.jsonl`, from the
   running containers in a live archive and from the stopped ones in the final one. A missing `chat-ui`
   container fails the export, checked before this step. Only an absent run log is tolerated (no run reached
   the agent yet): the copy's own `Could not find the file` error is accepted; any other copy error fails the
   export.
3. **Export** the copied journals with the exporter from the `chat-ui` image, in a one-off container, into
   the bundle below, with `spe_archive_mode` set to `live` or `final`.
4. Pack `<tmp>` and fetch it to `{{ spe_output_dir }}/archive-bundle-agui.tar.gz`, remove both copies from
   the VM. The fetched bundle is removed after writing, like `archive-bundle.json`.

**Why a live copy is consistent.** Journals and the run log are append-only (§13, decision 10; §5, *Run
log*), so a copy taken during an append is an earlier state of the file, at most with a torn last line. The
rebuild already reads such a file: it skips a line that does not parse, and a run without `run_end` is
`incomplete` with the events it has (§13, *The journal*; decision 8). In a live archive an `incomplete` run
was most likely still going when the copy was taken; the run goes on, and the next archive has it whole. The
journals and the run log are copied a moment apart, so a run that started or ended in between can be in one
and not the other; whoever compares them allows for that at the edge of the copy.

Every journal is exported, hidden and deleted included. If any step fails, `archive.yml` fails and
`destroy.yml` deletes nothing, as for Open WebUI.

### The Open WebUI chat

The exporter writes the bundle `write_run.py` already reads for Open WebUI (`{chats: [...], tags: [...],
notes: []}`, plus our `spe_archive_mode`), one chat per session, using the rebuild of §13:

- `title`, `created_at`, `updated_at`, `archived` (the session is hidden), `meta.tags`, and
  `meta.spe_deleted_at` for a deleted session;
- `chat.history.messages`: every message of every branch, keyed by id, with `parentId` and `childrenIds`;
  `chat.history.currentId`: the exported assistant message of the tip's run (each run is folded into one, below);
- a user message as Open WebUI's: `role`, `content`. A client message id that is already an exported id, or
  starts with `spe-run-` or `spe-msg-`, is exported under a fresh `spe-msg-<n>` id and keeps its own as
  `spe_original_id`, so no client id can make a message its own ancestor (clarification 8);
- **one assistant message per run**, `spe-run-<run id>`, parent the run's last new user message (for a run that
  added none, the anchor; an anchor that was folded into an earlier run's message is that run's message), with
  `output` items in the order their first event arrived, in v0.11.3's shapes (`utils/middleware.py`,
  `utils/ask_user.py`): a text message as
  `{type: "message", id, role: "assistant", content: [{type: "output_text", text}]}`, a tool call as
  `{type: "function_call", id, call_id, name, arguments}` (`arguments` a JSON string), a tool result as
  `{type: "function_call_output", id, call_id, output: [{type: "input_text", text}]}`, reasoning as
  `{type: "reasoning", id, content}`, each with `status: "completed"`; a compaction marker as a `message` item
  keeping its id; `content` is the run's text joined, without a compaction marker's summary, which stays its
  own item. These are the items Open WebUI itself replays to a model (`MESSAGE_REPLAY_KEYS`,
  `process_messages_with_output`), so the export is a chat Open WebUI could continue;
- `spe_run` on that assistant message (`run_id`, `status`, `started_at`, `ended_at`, `error` from the run's
  `run_end`), and `spe_ignored` (the run's ignored content) on it too, so a refused run still has a message to
  carry what it was sent.

Fields starting with `spe_` are ours; Open WebUI itself never writes them, so its own runs render as before.

### Write

`tasks/write.yml` unpacks the bundle and runs `files/write_run.py` on it, as for an Open WebUI run:

```
<run dir>/
  run.yml                     as for every run
  index.md                    sessions table `# | Session | Tags | Created | Runs | Compactions | State`; says
                              that the AG-UI frontend has no run report, and whether the archive was live
                              (incomplete runs may still have been going) or final
  openwebui-export.json       the bundle, copied as for Open WebUI; an in-place re-render reads it back
  chats/NN-<slug>.md          the active branch along currentId: user and assistant text, each tool call with
                              fenced arguments and result, plus the three additions below; then every message on
                              other branches, each naming the message it follows (clarification 8)
  chats/NN-<slug>.json        the exported chat
  agui-journals/<uuid>.jsonl  the raw journals, untouched
  agent-runs.jsonl            the agent's run log, when a run reached it
```

`write_run.py` also renders the three things only the AG-UI record has (decision 16): a run's status when it
is not `completed`, with its `error` if any; its ignored content as a block "sent by the client, not used",
with its kind and the content fenced, between the turns it was sent with; and a compaction marker as a
"Compacted" section. Fences are one backtick longer than the longest run of backticks in the content (at
least three). A bundle with no chats gives an `index.md` saying no session was recorded; without
`agent-runs.jsonl` the index says no run reached the agent. Given an archived run directory, the script
re-renders it in place. Open WebUI runs render as before.

The run directory's AG-UI files contain canaries, like the run log: they are outside git and **not**
shareable, as `canaries.json` is.
