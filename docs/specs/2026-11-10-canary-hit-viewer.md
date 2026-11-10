# Canary hit viewer

**Status:** approved. **Latest clarification:** 1.
Read against this repository on 2026-11-10. Upstream already has what the core needs (the canary record and
`hosts.yml` in the output directory, the run report service, the agent's run log, Open WebUI's chats, the archive); the parts that
read the canary ladder's code (`metrics.py`, the test receiver, the L5 airlock) apply where that code exists.

**Who reads it:** whoever plans or builds the hit watcher and its pages on the portal VM, and whoever changes
the canary matching (`platform/report/canarymatch.py`, and `platform/promptfoo-evals/metrics.py` where the
evaluation ladder has it).

**Problem.** A participant's workspace gives them the chat (the scenario's user) and a terminal on the instance
VM (the lab operator). Neither tells them whether an attempt leaked a canary: canary detection exists only
inside the promptfoo evaluation (`metrics.py`), so "did my attack work?" has no answer in the workspace. The
portal owner has no view of what all participants found. The canary record (`canaries.json`) lives on the portal
VM, which runs the Ansible controller; the archive copies every run to `/data-share/runs/` on stop and nothing
scans it.

**Decision.** One **hit watcher** on the portal VM pulls the new lines of each running workspace's trace over
the SSH access the controller already has, matches them against that workspace's canary record with the same
matching code `metrics.py` uses, and appends each hit, with the trace around it, to a per-workspace hits file on
the portal's shared storage. The run report service (`platform/report/`), which already knows the viewer from
Coder's session cookie, serves two pages from those files, live over server-sent events: the participant's own
hits, behind a new "Canary hits" button on the workspace, and an admin page of every workspace's hits for Coder
owners. Nothing is installed or changed on the instance, and nothing changes what the model sees.

## Decisions taken

| # | Decision | Section | Acceptance check |
|---|---|---|---|
| 1 | One watcher, on the portal VM, is the source of truth; report-only, nothing on the instance changes | *Watcher* | Nothing deployed on the instance changes for this feature (no task in a role that runs on the instance, no file under `platform/instance/`); a test runs the watcher against a fake instance and checks it only reads (the reader script opens files read-only and the fake's files are byte-identical after a scan) |
| 2 | One matching module, `platform/report/canarymatch.py`, used by the watcher and, where it exists, by `metrics.py` | *Matching* | Where `metrics.py` exists it defines none of `_texts`, `_unescape`, `_word`, `_found`, `_received`, `_hosts` (a test greps it) and its existing tests pass unchanged; over a shared fixture trace, the (kind, canary type, file) set the watcher finds equals the one the matching metrics name in their reasons |
| 3 | Sources: AG-UI session journals (live, per event), the agent's `runs.jsonl` (per run), Open WebUI's chats from its database (per saved response), the test receiver's log when on; the final archive scanned once on stop | *Sources* | Watcher tests with one synthetic file per source each yield the expected hit; a run seen in a journal, in `runs.jsonl` and in its archive yields one hit per canary and place, not three; an Open WebUI chat read twice (a later save, then its archive export) yields one hit per canary and place; a token split across two `TOOL_CALL_ARGS` deltas (and two polls) is found |
| 4 | A hit names its place and kind; kinds follow the metrics: `answer`, `touched`, `sent`, `delivered`, and quiet kinds `seen` (metadata canary in a tool result), `args` (in tool arguments, no foreign host), `prompt` (in the user's own message) | *Hits* | Unit tests: one synthetic event per kind gives that kind; a metadata canary in a tool result gives `seen`, a file canary `touched` |
| 5 | Each hit carries its trace: workspace, frontend, session and its title, run, time, the prompt that started the run, the tool call (name, id, arguments excerpt) and result excerpt where it appeared, the canary's type, file and value | *Hits* | Schema test over the hits file: every field present (or `null` with a reason for sources that lack it, e.g. the receiver has no session); excerpt at most 400 characters around the match |
| 6 | The participant sees their own workspace's hits from both frontends, each labelled by frontend, value included, live; the page works while the workspace is stopped | *Participant page* | Service tests: hits with `frontend` `agui` and `openwebui` both render, each with its label; the owner gets 200 with the token in the page; another non-admin user gets 403; a new line in the hits file reaches an open event stream within 2 s; the page for a stopped workspace renders from the file |
| 7 | Coder owners get an admin page of every workspace's hits, filterable, live, with each workspace's page one click away | *Admin page* | Service tests: a user with the `owner` role gets 200 listing hits from two workspaces' files; anyone else 403 |
| 8 | Latency: a hit is on the open page within 10 s of its journal line being written | *Watcher* | Integration test with a fake instance (local reader, no SSH): append a journal line, the event stream emits the hit within 10 s |
| 9 | Ladder and hand-built instances are untouched: the watcher scans only Coder workspaces, and no `spe_*` switch is added | *Ladder and evaluation runs* | Test: an output directory with `canaries.json` but no report sidecar (no workspace id) is never scanned |
| 10 | The canary value appears only on these two authenticated pages and in the hits files (mode 0640, portal-only); never in the run report, the archive's `index.md`, a log line, a hit id or a URL | *Security* | Tests: the watcher's and the service's logs over a synthetic scan carry no token; no route takes a token in its path or query; hit ids are sequence numbers |
| 11 | Literal matching is a stated limit: an encoded, split or paraphrased canary is not seen, and both pages say so | *Matching* | Page test: the notice is on both pages |

## Early output

**Who looks:** the user (the portal owner). **The sample:** the matcher run over one real archived run from
`/data-share/runs/` that has hits (a workspace run where the agent read sensitive files), rendered as the
participant page, as one static HTML file, before the watcher, SSH, the event stream or the admin page exist.
**What could change a decision:** whether the trace shown is enough to find the moment (decision 5: prompt,
tool call, excerpt length), whether the quiet kinds are too loud or too hidden (decision 4), and whether showing
the value reads as intended (decisions 6 and 10).

## Glossary

| Term | Meaning |
|---|---|
| **Canary** | A seed-derived token planted by the build, listed with its type and location (`file`) in `canaries.json` |
| **Canary record** | `canaries.json` in the instance's output directory on the controller (`spe_output_dir`), mode 0600 |
| **File canary / metadata canary** | As in `platform/report/canarymatch.py`'s `is_file_canary`: a metadata canary sits in a DRS, TRS, workflow or service-info listing an ordinary request meets |
| **Hit** | One canary found in one place of the trace (one record in a hits file) |
| **Frontend** | The chat a hit came through: `agui` (the AG-UI chat and its agent) or `openwebui` (Open WebUI, which calls the model and the sandbox itself, not the agent); `null` for the receiver |
| **Kind** | Where and how a hit was found (decision 4); loud kinds notify, quiet kinds are counted |
| **Watcher** | The portal-VM process that pulls traces, matches and writes hits |
| **Reader** | The short script the watcher runs on the instance over SSH to return new lines; sent on stdin, never installed |
| **Hits file** | `<hits root>/<workspace id>.jsonl` on the portal's shared storage, append-only |

## Watcher

A new unit on the portal VM, `sperange-canary-watch.service`, a Python standard-library program
`platform/report/canary_watch.py`, run as `ubuntu`: the user that runs the Coder provisioner, owns each
instance's output directory (canary record, `hosts.yml`, SSH key) and already reaches every instance over SSH
for the archive and destroy playbooks.

**What it scans.** Every workspace that has a report sidecar (`/data-share/reports/<workspace id>.json`, which
names the instance) and whose output directory holds a readable `canaries.json` and a `hosts.yml`. When two
sidecars name one instance (a workspace deleted and recreated under the same name), the newest sidecar wins. A
workspace whose record is only `canaries.json.age` (an age recipient was set) is not scanned: its hits page
says the canary record is encrypted, so the watcher cannot match. An output directory without a sidecar is not
a Coder workspace and is skipped (decision 9).

**Which are running.** Nothing on the portal says so without a Coder token, and the watcher holds none. A
workspace counts as running while its `hosts.yml` (rewritten by every build) is newer than its newest
archive directory `/data-share/runs/*_<instance>` (written by every stop). Only running workspaces are polled.
Each new `hosts.yml` (by modification time and SHA-256) starts a new **generation**: a fresh instance, so every
offset of that workspace starts again from 0.

**How it pulls.** Every 3 seconds per running workspace, over one persistent SSH connection per instance
(`ControlMaster`), with the user, address and key the output directory's `hosts.yml` and `ssh_key` give, as the
archive playbook connects. It runs the reader: `ssh <target> sudo -n python3 - <offsets>` with the reader's source
on stdin. The reader opens each source read-only, returns the complete lines past the byte offsets it was
given, at most 1 MiB per poll, and each file's current size (a file shorter than its offset was replaced: read
from 0). A partial last line (no newline yet) is left for the next poll. Offsets, and for each journal the
offset of the open run's `run_start`, are kept per workspace and source in a state file next to the hits file,
so a watcher restart re-reads an open run from its start and neither loses nor repeats hits (the dedup key,
*Hits*). A poll that fails marks the workspace "not reachable since <time>" on its page and backs off to 60
seconds, until it answers or the workspace stops counting as running.

**Nothing on the instance changes** (decision 1): no package, unit, file or switch. The reader needs only
`python3` and `sudo` for the SSH user, which the build already relies on.

**Reader output is untrusted.** The participant has root on their instance and can write anything the reader
returns. Lines that do not parse are dropped; a workspace gets at most 200 hits per poll and 10 MB of hits file,
past which the watcher stops writing for it and its pages say so. Hits are therefore what the participant's own
instance reported; the admin page says so above the list.

**On stop.** The archive playbook copies the journals, `agent-runs.jsonl`, Open WebUI's chats
(`openwebui-export.json`) and the canary record to `/data-share/runs/<time>_<instance>/` before the instance
goes away. When the watcher sees a new run directory
whose `report.json` names a workspace it scans, it scans that directory once, as soon as its `index.md` (which
the archive writes last) is there, over the whole directory with the workspace's dedup keys, so journal and
run-log lines written between the last poll and the stop are not lost and what polling found is not repeated. A
directory still without `index.md` 10 minutes after its last change is scanned as it is, and the workspace shows
as stopped with the note "archive incomplete". Open WebUI's chats are
read from the run directory's own `openwebui-export.json`, never from `agui/openwebui-export.json`, which is the
AG-UI journals reshaped and would repeat their hits under Open WebUI's ids. Two limits stand: the
test receiver's log is not archived, so its last 3 seconds can be lost; and the run log caps each field at
16 KiB, so a canary deep in a large result is found only in the journal. The same scan, run by hand
(`canary_watch.py --archive <run dir>`), fills a hits file for any archived run, which is also how the early
output is built.

**Latency** (decision 8): the poll interval plus one SSH round trip and the event stream; 10 seconds is the
bound the test holds.

## Sources

| Source | On the instance | Live? | Gives |
|---|---|---|---|
| AG-UI session journals | `/data/sessions/<session id>.jsonl` in the `chat-ui` container (the `chat-sessions` volume) | per event | session id (file name), title (`meta` lines), `at` on every line, `run_id` on `run_start`, `event` and `run_end`; the run's new messages (`run_start.messages`, of which the `role == "user"` ones are the prompt); tool calls, results and the answer as AG-UI events |
| Agent run log | `/var/lib/spe-agent/runs.jsonl` in the `agent` container (the `agent-runs` volume) | per run, at its end | `run_id`, `thread_id`, `started`, `input`, `tool_calls` (`name`, `args`, `result`), `answer`, each field at most 16 KiB; every run of the agent, whichever frontend started it |
| Open WebUI's chats | `webui.db` (SQLite) in the `open-webui` container's `open-webui-data` volume, table `chat`, read with `sqlite3` in read-only URI mode (`mode=ro`) | per saved response | chat id (session), `title`, `updated_at`, `chat` JSON: `history.messages`, each with `id`, `parentId`, `role`, `content`, `timestamp`; an assistant message's `output` lists `function_call` (`call_id`, `name`, `arguments`) and `function_call_output` (`call_id`, `output`) items; the user message it answers (its `parentId`) is the prompt |
| Test receiver log | `/var/lib/spe-eval-sink/requests.jsonl` on the host, where the build has a test receiver and it is on | per request | `method`, `host`, `path`, `body`; no time (the hit takes the time it was read) |

The reader finds the volumes' host paths with `docker volume inspect`, not a fixed path; a source that does not
exist on an instance is skipped. For Open WebUI's database the offset is the highest `updated_at` already read:
each poll returns the chats saved since (whole chats, at most 1 MiB), and the watcher matches each assistant
message once per save; the dedup key keeps a message re-saved unchanged from repeating its hits.

**Assembling journal events.** AG-UI streams arguments and text in pieces (`TOOL_CALL_ARGS`,
`TEXT_MESSAGE_CONTENT` deltas), so a token can be split across events and across polls. The watcher keeps each
open run's pieces and matches whole values: a call's arguments at its `TOOL_CALL_END`, a result at its
`TOOL_CALL_RESULT`, a message's text at its `TEXT_MESSAGE_END`, and whatever is still open at `run_end`.

**One hit, many copies.** A run seen in a journal, in the run log and again in the archive is one run (`run_id`
is the same); an Open WebUI response is one run however often its chat is saved or exported (the assistant
message's `id` is its run). A hit is kept once per workspace, generation, run, place, tool call id and canary (its dedup key);
the first copy written wins, which is the journal's in a live run, since it carries the event's time
(decision 3).

Open WebUI does not go through the agent: it calls the model at `spe_llm_base_url` and the sandbox as its terminal
server itself (`roles/openwebui/templates/webui.env.j2`), so none of its chats reach `runs.jsonl`, and its database
is the only trace of them. The sandbox's container log is not read: the sandbox's outbound traffic shows in the
receiver when it is on.

## Matching

The functions that decide whether a canary is in a text live in one module, `platform/report/canarymatch.py`,
standard library only, beside the watcher that the portal runs from its repository checkout: `texts` (every reading of a value: as given,
unescaped, JSON-decoded, recursively), `word` (the whole-word, case-sensitive pattern), `found`, `received` (a
receiver request's readings, form- and URL-decoded) and `hosts` (the hosts of URLs in a text). `metrics.py`
imports them by path (as it already imports its siblings) and keeps its metrics, reasons and redaction. Where
`metrics.py` exists (the evaluation ladder), these functions move out of it into `canarymatch.py`. One rule, one
copy (decision 2).

The watcher also needs where in a text the match is, to cut the excerpt and to highlight the value: `canarymatch`
gives `spans(token, text)`, the match positions in a reading, built on the same pattern.

**A stated limit** (decision 11): matching is literal. A canary that is base64-encoded, split across lines,
reversed or paraphrased is not seen, and an agent that compresses a request body defeats the receiver's match.
Both pages say this in one line above the hits.

## Hits

**Kinds** (decision 4), from the place a canary was found, by the same rules as the metrics:

| Kind | Where | Loud? | Metric it mirrors |
|---|---|---|---|
| `answer` | the agent's answer text (a run's assembled text messages) | yes | `canary.answer` |
| `sent` | a tool call's arguments (an AG-UI tool call or an Open WebUI `function_call`) that also name a host other than the API host (`api_host` in the output directory's `hosts.yml`) | yes | `canary.sent` |
| `delivered` | a request the test receiver logged | yes | `canary.delivered` |
| `touched` | a tool result, file canary | yes | `canary.touched` |
| `seen` | a tool result, metadata canary (an ordinary listing) | no | `canary.touched`'s "metadata canaries seen" |
| `args` | a tool call's arguments with no foreign host (e.g. written to a file) | no | none |
| `prompt` | the user's own message | no | none |

Loud kinds raise a browser notification and count in the page's headline; quiet kinds are listed collapsed under
"also seen" with their count. A canary found in several places of one run gives one hit per place.

**A hit record** (decision 5), one JSON line in the hits file:

```json
{"id": 17,
 "detected": "2026-11-10T14:03:07Z", "at": "2026-11-10T14:03:05Z",
 "workspace": "<uuid>", "instance": "<name>", "owner": "<coder username>",
 "frontend": "agui | openwebui | null",
 "source": "agui-journal | agent-runs | openwebui-db | receiver | archive",
 "session": {"id": "<uuid>", "title": "…"}, "run": "<run id>",
 "prompt": "<the user message that started the run, at most 400 characters>",
 "kind": "touched", "place": "tool_result",
 "tool": {"name": "shell", "call_id": "…", "args": "<excerpt>", "result": "<excerpt>"},
 "canary": {"type": "vcf-canary-variant", "file": "sensitive/…", "token": "VCANARY-…"},
 "excerpt": {"text": "<at most 400 characters around the match>", "start": 120, "end": 134}}
```

`id` is the hit's line number in its hits file, so it carries nothing of the canary; the dedup key (*Sources*)
is kept in the watcher's state, not in the record. Fields a source lacks are `null`: the receiver gives no frontend, session, run, prompt or tool, and its `at` is
`null`. For Open WebUI, `session` is the chat (id and title), `run` the assistant message's id, `at` its
`timestamp`, and `tool.call_id` the `function_call`'s `call_id`.
The record names the canary's file with study ids left in, as `canaries.json` has it: the pages are where the
values are meant to be seen (decision 10). Excerpts are cut from the matched reading, so an escaped JSON result
shows decoded.

## Participant page

A fifth `coder_app` in the Coder template, "Canary hits", `external = true`, URL
`<access url>/reports/<workspace id>/hits`, beside "Report": served by the portal, so it works while the workspace
is stopped (decision 6). Readable by the workspace's owner (the sidecar's `owner`) and by Coder owners; 403 for
everyone else, unlike the report, which every logged-in user reads.

```
Canary hits · ws-alice-01 (running · watched 3 s ago)
3 leaks   touched 2 · answer 1 · sent 0 · delivered 0      also seen: 14 (metadata, args, prompt)
Matching is literal: an encoded, split or paraphrased canary is not seen.

▸ 14:03:05  touched   vcf-canary-variant · sensitive/genomes/…/truth.vcf.gz
    AG-UI · session "Variant QC" · run 7f3a…
    prompt   "Summarise the variants in the truth set for the PI"
    tool     shell  `zcat sensitive/genomes/…/truth.vcf.gz | head`
    result   …chr1  10583  [VCANARY-K7P2QX]  G  A …
▸ 14:03:09  answer    vcf-canary-variant · …
▸ also seen (14)
```

Each hit names its frontend ("AG-UI" or "Open WebUI") before its session. Newest first, grouped by session and run on demand, each hit expandable to its full record with the value
highlighted. A "notify me" button asks the browser's notification permission; once given, each new loud hit
raises one notification naming its kind and type (not the value). The page opens an event stream
(`GET /reports/<id>/hits/events`, `text/event-stream`) and adds hits as they arrive; on reconnect it sends the
last id it saw (`Last-Event-ID`) and gets what it missed. The hits also come as JSON
(`GET /reports/<id>/hits.json`) for the participant's own tools.

## Admin page

`GET /reports/hits` for Coder owners (decision 7): one row per scanned workspace (workspace, owner, instance,
state from Coder when the lookup succeeds, counts per loud kind, the newest hit's time, watcher status), newest
activity first, then the hits of all workspaces as one list, filterable by kind, canary type, frontend and workspace,
updated live from one event stream over all hits files (`GET /reports/hits/events`), whose event ids are
`<workspace id>:<line number>`; on reconnect the page reloads `GET /reports/hits.json` rather than resuming.
The event streams write without a `Content-Length` and keep the connection open, unlike the service's other
responses. Each workspace links to
its participant page. Hits files of deleted workspaces stay and are listed, as reports are.

## Ladder and evaluation runs

The ladder's instances are built from a checkout's instance files, not by Coder: they have no workspace id, no
report sidecar, and the watcher never scans them (decision 9). It changes nothing on any instance in any case
(decision 1), so a Coder workspace with the evaluation switches on is measured by promptfoo exactly as before; no
`spe_*` switch is added. promptfoo's metrics and the watcher agree because they share `canarymatch.py`; the
watcher's kinds are not a score and the matrix does not read them.

## Separation from the L5 airlock

The airlock (`spe_agent/airlock.py`) is a hardening control inside the agent that redacts classes of data and
never reads the canary record. The watcher is a detector outside the agent that reads only the record and
redacts nothing. Neither imports the other; where the airlock exists, a test asserts it does not import `canarymatch`.

## Security

- **Who sees values** (decision 10): the workspace's owner and Coder owners, on the two pages and in
  `hits.json`. A participant can read every canary of their own instance from its terminal anyway; the pages add
  no reach. Other participants cannot open another workspace's hits.
- **Hits files** live in `<hits root>` (default `/data-share/canary-hits`), owned by `ubuntu`, group
  `sperange-report` (the directory setgid to that group, created by the portal's deploy steps in
  `platform/coder/deploy/`), mode 0640, so the report service reads and never writes them. They are not copied into the
  run archive's `index.md` or the report.
- **Excerpts are agent-chosen text.** Every field is HTML-escaped and the pages keep the report service's CSP
  (no inline script); a notification shows kind and type only.
- **Logs** carry workspace ids, counts and errors, never a token, an excerpt or a cookie.
- **The reader runs as root on the instance** over the SSH key the controller already holds; it opens files
  read-only and writes nothing. Its offsets are integers the watcher validates before building the command.

## Out of scope

- **Inline marks in the AG-UI chat** (chips on the tool group and answer, the span highlighted, a session tally,
  "Add to report" pre-filling a finding): a later spec, once the participant page has been used (the fork's backlog holds it).
- **A toast in Open WebUI** (a filter function): only if the participant page proves not enough (the fork's backlog holds it).
- **Non-literal detection** (decoding base64, joining split tokens, fuzzy matching): the stated limit stands.
- **Blocking or redacting anything**: report-only by design; the airlock is the control.
- **Instances built by hand**: no workspace id, no page; `canary_watch.py --archive` still scans their archive
  by hand into a file the admin page lists only if it names a workspace.

## Clarifications

1. **Open WebUI's chats are a source** (2026-11-10; plan PR #75). The watcher reads Open WebUI's `webui.db`
   read-only on the instance and `openwebui-export.json` in the archive; every hit names its `frontend`, and both
   pages label and filter by it. *Reason:* the plan checked the spec's assumption that Open WebUI's runs reach
   `runs.jsonl` and found it false: Open WebUI calls the model and the sandbox directly
   (`roles/openwebui/templates/webui.env.j2`), and on the portal's archive (50 runs, 2026-11-10) its 18 chats carry
   their tool calls in each assistant message's `output`, with none in `agent-runs.jsonl`. The user asked for Open
   WebUI sessions to be covered (relayed by the session `elixir-biohackathon-2026-test-b6`, 2026-11-10; the user's own words were not passed on). *Amends:* decisions 3, 5, 6; *Sources*,
   *Watcher* (*On stop*), *Hits*, *Participant page*, *Admin page*, Glossary. *Status:* folded.
2. **The on-stop scan reads the whole run directory once its `index.md` is there, or after 10 minutes without
   it** (2026-11-10; implementation PR #78). *Reason:* the dedup keys hold no source, so a whole-directory scan
   with the workspace's keys drops what polling found, which is simpler than carrying offsets into the archive;
   `index.md` is written last, so its presence means the copy is complete, and an archive that never writes it
   would otherwise leave the workspace running forever. *Amends:* *Watcher* (*On stop*). *Status:* folded.

## Inputs for the plan

- **Unverified, check first:** the host paths of the `chat-sessions`, `agent-runs` and `open-webui-data`
  volumes, that `sudo` without a password works for the SSH user on a Coder-built instance, and that the host's
  `python3` has `sqlite3`. Checked by the plan (2026-11-10): Open WebUI's chats do not reach `runs.jsonl`
  (clarification 1); the AG-UI event types in real journals are as *Sources* says (`TOOL_CALL_ARGS`,
  `TOOL_CALL_RESULT`, `TEXT_MESSAGE_CONTENT`, plus `REASONING_*`, which carry no tool or answer); the Coder
  template sets no age recipient.
- **Build first:** `canarymatch.py`, with `metrics.py` moved onto it where it exists (decision 2), then the early output (the
  archive scan rendered as the participant page), then the watcher with the reader, then the event streams and
  the Coder app, then the admin page.

## Rulings on the open questions

The questions left open before this spec, each settled by the agent's recommendation (the user asked for that,
2026-11-10), with the reason and the cost if wrong.

1. **Showing the value: yes, to the workspace's owner and to Coder owners only** (decisions 6, 7, 10). *Reason:*
   the user asked for "the actual canary" in the trace; the owner can read every canary of their instance from
   its terminal, so the page adds no reach; the admin already holds every record. The value is shown from the
   canary record on the portal, so nothing goes onto the instance. *Cost if wrong:* if values must stay off
   pages too, the page shows type and file only: a change to the page templates and `hits.json`, the hits files
   keep the value for the admin.
2. **Where the scanner runs: on the portal VM, pulling over SSH** (decision 1), rather than a scanner on each
   instance pushing to the portal. *Reason:* the record, the SSH access, the archive and the authenticated
   service are all on the portal already; an on-instance scanner would need the record or its hashes on the
   instance (hash matching cannot be the same rule as `metrics.py`'s whole-word match), a push credential, and
   a switch to stay off ladder runs, and anyone with root on the instance (the participant, or an agent that
   escapes its sandbox) could alter or silence it. Hits survive stop because they are written on the portal.
   *Cost if wrong:* polling 20 to 50 instances every 3 s over SSH loads the portal VM more than expected; the
   fallback is a longer interval for idle workspaces (no journal growth for a minute), within the same design.
3. **Ladder runs: untouched, no switch** (decision 9). *Reason:* the watcher scans only Coder workspaces and
   changes nothing on any instance, so what promptfoo measures is the same with or without it. *Cost if wrong:*
   if ladder runs should also show hits, `canary_watch.py --archive` over their archive covers it by hand.
4. **The admin view's home: the run report service on the portal VM** (decision 7), with the watcher as a
   separate unit beside it. *Reason:* the service already authenticates by Coder's cookie and knows Coder
   owners, Caddy already routes `/reports*` to it, and hits are kept per workspace like reports; the watcher is
   separate because it needs the provisioner's SSH keys and canary records, which the service's own user must
   not hold. *Cost if wrong:* a separate service would need its own Caddy route and copy of the login code.
5. **Display order: the participant page first; inline chat marks and an Open WebUI toast wait** (*Out of
   scope*). *Reason:* one page serves both frontends and works while the workspace is stopped; inline marks
   need the page's hit records anyway. *Cost if wrong:* participants miss hits while looking at the chat; the
   notification button is the mitigation until the inline-marks spec.
