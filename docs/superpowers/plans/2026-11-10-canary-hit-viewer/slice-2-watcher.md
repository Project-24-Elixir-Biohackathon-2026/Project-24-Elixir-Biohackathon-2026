# Slice 2/5: the watcher

Branch `impl/canary-hit-viewer-2-watcher`. Spec: decisions 1, 3, 9, 10 (*Watcher*, *Sources*, *Ladder and
evaluation runs*, *Security*), clarification 1; plan rulings 1, 5, 6. Global constraints:
[README](README.md#global-constraints). Plan a mid-slice handoff after Task 6 if the context budget is past half.

### Task 5: the reader

Decisions 1, 3; ruling 1.

**Files:**
- Create: `platform/report/canary_reader.py`, `platform/report/tests/test_canary_reader.py`

**Interfaces:**
- Produces: a script run as `python3 - '<offsets JSON>'` with its source on stdin. Offsets:
  `{"journals": {"<session uuid>": <int>}, "agent_runs": <int>, "receiver": <int>, "openwebui": <number>}`
  (missing keys are 0). It finds the volumes with `docker volume inspect spe-frontend_<name> --format
  '{{ .Mountpoint }}'` for `chat-sessions` (`<mount>/*.jsonl`), `agent-runs` (`<mount>/runs.jsonl`) and
  `open-webui-data` (`<mount>/webui.db`); the receiver is `/var/lib/spe-eval-sink/requests.jsonl`. A test override:
  env `SPE_READER_PATHS` (JSON `{"sessions": dir, "agent_runs": file, "receiver": file, "webui_db": file}`)
  replaces the lookup. Prints one JSON object:
  `{"files": {"journal:<uuid>" | "agent_runs" | "receiver": {"size": int, "start": int, "end": int, "lines": [str]}},
  "openwebui": {"rows": [{"id", "title", "updated_at", "chat"}], "max": number} | null, "missing": [str],
  "errors": [str]}`. `start` is where reading began (0 when the file is shorter than its offset: replaced), `end`
  the offset after the last complete line; a partial last line stays unread. All files together at most 1 MiB
  per call: past it, the rest waits for the next poll (`end` says where it stopped); each source still returns
  at least its first line or row, so one line or row over 1 MiB cannot stall it. Open WebUI: rows with
  `updated_at >= offset` (whole seconds: a chat saved in the second of the last row read is not skipped; the
  dedup keys drop the repeats), ordered by it, through `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, stopping at
  1 MiB of `chat` text; an error (no table, locked) goes in `errors` as `openwebui: <exception class>`.
  Files open with `open(path, "rb")` only.
- Consumes: nothing from the other modules: the reader is self-contained (it is sent alone).

- [ ] **Step 0: Check the unverified claims** on our de.NBI instance (`denbi-agui-01`, if it is up; else rely on the fixture
  and write the open check into slice 3's Task 9 text, which the PR body points to): `docker volume ls --format '{{.Name}}' | grep spe-frontend_`, `sudo -n
  true`, `python3 -c 'import sqlite3'`, and the `chat` table's columns
  (`sudo python3 -c "import sqlite3; c=sqlite3.connect('file:<mount>/webui.db?mode=ro', uri=True);
  print([r[1] for r in c.execute('pragma table_info(chat)')])"`). A difference is a ruling in `progress.md` and
  a rewrite of this task.
- [ ] **Step 1: Write the failing tests** (run the reader as a subprocess with `SPE_READER_PATHS` over a
  `tmp_path`): `test_reads_complete_lines_only` (a trailing partial line is not returned; `end` stops before it),
  `test_replaced_file_read_from_zero`, `test_cap_one_mib`, `test_openwebui_rows_since` (a SQLite `chat` table
  built in the test with three rows, offset between them: two rows returned, `max` the newest),
  `test_openwebui_missing_table_is_error`, `test_missing_source_listed`, `test_reader_is_read_only` (the files'
  bytes and mtimes are unchanged after a call; the source has no `"w"`, `"a"`, `"r+"` mode, `unlink`, `rename`),
  `test_reader_output_untrusted` is Task 7's (the watcher side).
- [ ] **Step 2: Run** `uv run --with pytest --with markdown pytest platform/report/tests/test_canary_reader.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implement** `canary_reader.py`.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Canary reader: new lines and Open WebUI chats, read-only`.

### Task 6: which workspaces, and their generations

Decisions 1, 9; ruling 6.

**Files:**
- Modify: `platform/report/canary_watch.py`
- Test: `platform/report/tests/test_canary_watch.py`

**Interfaces:**
- Produces: `@dataclass Workspace`: `id`, `owner`, `instance`, `output_dir`, `api_host`, `ssh` (`user`, `host`,
  `key`), `generation: str` (SHA-256 of `hosts.yml`'s bytes and mtime), `running: bool`, `encrypted: bool`.
  `discover(reports_dir: str, output_root: str, runs_dir: str) -> list[Workspace]`: one per sidecar
  `<reports_dir>/<uuid>.json` whose `instance` has `<output_root>/<instance>/hosts.yml`; for two sidecars naming
  one instance, the newer (mtime) only; `encrypted` when only `canaries.json.age` is there; `running` when
  `hosts.yml` is newer than every `<runs_dir>/*_<instance>` directory. How to reach the VM: `canary_record.vm_argv(output_dir)`
  (slice 1), which reads `hosts.yml`'s `ssh_target` and `ssh_args` (or a local target); not `archive.yml`'s way,
  which asks OpenStack for the address. `hosts.yml` is read with `canary_record.read_hosts`, the record with
  `canary_record.load_canaries` (ruling 2).
- Defaults: `--reports-dir /data-share/reports`, `--runs-dir /data-share/runs`, `--hits-dir
  /data-share/canary-hits`, `--output-root` `<repo>/platform/ansible/output` (from the script's own path).

- [ ] **Step 1: Write the failing tests**: `test_no_sidecar_never_scanned` (decision 9: an output directory with
  `canaries.json` and `hosts.yml` but no sidecar is not in `discover`), `test_newest_sidecar_wins`,
  `test_running_until_archived` (an archive directory newer than `hosts.yml` makes it not running),
  `test_encrypted_record`, `test_generation_changes_with_hosts_yml`.
- [ ] **Step 2: Run** the watch tests. Expected: FAIL.
- [ ] **Step 3: Implement** `discover`.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Canary watch: find Coder workspaces and their generations`.

### Task 7: polling, state, status, on stop

Decisions 1, 3, 10; *Watcher* (*How it pulls*, *Reader output is untrusted*, *On stop*); ruling 6.

**Files:**
- Modify: `platform/report/canary_watch.py`
- Test: `platform/report/tests/test_canary_watch.py`

**Interfaces:**
- Consumes: `canary_hits` (`JournalReader`, `agent_run_places`, `openwebui_places`, `receiver_places`,
  `hits_for`, `dedup_key`, `HitsFile`), `scan_archive`, `discover`, the reader's output format (Task 5).
- Produces:
  - `class Transport` with `read(ws: Workspace, offsets: dict) -> dict`; `SshTransport` runs
    `canary_record.vm_argv(output_dir)` (SSH from `hosts.yml`'s target and arguments, or local) with
    `-o ControlMaster=auto -o ControlPath=~/.ssh/cm-%C -o ControlPersist=60 -o BatchMode=yes` (sockets on local
    disk, not on `/data-share`'s NFS), then `sudo python3 - <shlex.quote(offsets JSON)>` with the reader's source
    on stdin (timeout 30 s); the offsets' journal keys are checked as UUIDs and their values as integers before
    the call (`test_offsets_quoted_and_checked`);
    `LocalTransport(paths: dict)` runs the reader locally with `SPE_READER_PATHS` (the fake instance).
  - State per workspace in `<hits_dir>/<id>.state.json` (0600): `generation`, `offsets` (the reader's keys),
    `run_starts` (per journal, the offset of its open run's `run_start` line), `seen` (dedup keys), `archived`
    (run directories already scanned). After a restart a journal is re-read from its open run's `run_start`,
    the dedup keys drop the repeats.
  - Status per workspace in `<hits_dir>/<id>.status.json` (0640): `state`, `since`, `last_poll`, `hits`
    (count per kind), `note` (e.g. "canary record is encrypted", "hits file full").
  - `Watcher(hits_dir, reports_dir, runs_dir, output_root, transport).tick(now: float) -> None`: discovers, polls
    each running workspace whose next poll is due (3 s; 60 s after a failure, `state` `unreachable`), scans each
    new run directory whose `report.json` names a scanned workspace once, and only once its `index.md` exists
    (the archive writes it last; `report.json` comes before the journals and exports,
    `test_scan_waits_for_index_md`) (from the offsets reached, then
    `state` `stopped`), and writes state and status. `run_forever()` calls `tick` every second.
  - Untrusted output: a line that is not JSON is dropped; at most 200 hits per workspace per poll; `HitsFile`
    at 10 MB stops writing (`state` `capped`); a reader reply that is not the expected shape is a failed poll.
- Carried from slice 1 (its review and rulings):
  - `JournalReader` keeps an open run's pieces until its `run_end`; a run that never ends grows forever. Bound it:
    drop a run's pieces past 1 MiB of buffered text, and ignore events for a run already ended (slice 1's
    reader re-creates it) (`test_unclosed_run_is_bounded`).
  - `HitsFile` assumes one writer: the daemon is the only one per workspace (the unit runs one process; `--archive`
    and `--once` write elsewhere or hold `fcntl.flock` on the file while appending). After a crash mid-write the
    file can end in a partial line: `append` first ends it with a newline, and `read` skips a line that is not
    JSON (`test_partial_last_line_after_crash`, cut both between lines and mid-character).
  - A source file the watcher cannot read (`OSError`, e.g. `PermissionError` in `canary_hits._jsonl`) is skipped
    and logged with its workspace id, never a traceback that ends the daemon (`test_unreadable_source_skipped`).
  - Receiver hits share one dedup key per canary per generation (the spec's key, *Sources*): one `delivered` hit
    per canary, not one per request. Slice 3 revisits it if the page should list each request.
- Logging: `logging` to stderr with workspace id, counts, errors; never a token, an excerpt, a line or a path
  under `sensitive/`.

- [ ] **Step 1: Write the failing tests** (fake instance: `LocalTransport` over a `tmp_path` holding a journal,
  `runs.jsonl`, a `webui.db`, `requests.jsonl`; a sidecar and output directory with the fixture
  `canaries.json`): `test_poll_appends_hits_from_each_source`, `test_split_token_across_polls` (the two
  `TOOL_CALL_ARGS` lines written between two ticks: one hit), `test_restart_mid_run_no_loss_no_repeat` (new
  `Watcher` on the same `hits_dir` after a tick inside a run: the run's later hits appear, none twice),
  `test_new_generation_resets_offsets` (rewrite `hosts.yml`, truncate the journal, make `webui.db` anew with a lower
  `updated_at`: its hits found), `test_reader_output_untrusted` (non-JSON and 300-hit replies: dropped / 200
  kept), `test_failed_poll_backs_off` (a transport that raises: `unreachable`, next poll after 60 s),
  `test_on_stop_scans_archive_once` (a run directory appears with lines past the last poll: their hits, once),
  `test_logs_carry_no_token` (`caplog` over a full scan), `test_state_file_modes` (state 0600, hits and status
  0640).
- [ ] **Step 2: Run** the watch tests. Expected: FAIL.
- [ ] **Step 3: Implement** `Transport`, `SshTransport`, `LocalTransport`, `Watcher`.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Canary watch: poll running workspaces, keep state, scan on stop`.

### Task 8: the unit, the hits root, a real check

Decision 1 (nothing on the instance), decision 10 (file modes); ruling 5.

**Files:**
- Create: `platform/coder/deploy/sperange-canary-watch.service`
- Modify: `platform/report/canary_watch.py` (`--once --output-dir DIR` for a hand check: one poll of that
  directory's instance, hits to `--out`), `platform/coder/README.md` (deploy steps: the unit, the hits root
  `/data-share/canary-hits` owned `ubuntu:sperange-report`, mode 2750), `platform/report/README.md` (what the
  watcher reads and writes, `--archive`, `--once`)
- Test: `platform/report/tests/test_canary_watch.py`

- [ ] **Step 1: Write the failing test** `test_nothing_on_the_instance_changes`: `git diff --name-only
  origin/main...HEAD` lists nothing under `platform/instance/` or `platform/ansible/roles/` (skip when not in a
  git checkout or `origin/main` is missing, as upstream and CI have it).
- [ ] **Step 2: Write the unit** like `sperange-report.service` (`User=ubuntu`, `Restart=always`,
  `ExecStart=/usr/bin/python3 <checkout>/platform/report/canary_watch.py`), and the README steps.
- [ ] **Step 3: Run** the report suite. Expected: PASS.
- [ ] **Step 4: The real check**, if `denbi-agui-01` is up (one instance at a time, standing OK): from the main
  checkout, `python3 platform/report/canary_watch.py --once --output-dir platform/ansible/output/denbi-agui-01
  --out <scratch>/hits.jsonl`. Expected: the reader answers (no `errors`), the sources it finds are listed, and
  the hits count per kind is printed (no value). Put the command and the counts in the PR body. If the instance
  is down, say so there; the fake-instance tests stand.
- [ ] **Step 5: Commit** `Canary watch: systemd unit, hits root, one-shot check`.
