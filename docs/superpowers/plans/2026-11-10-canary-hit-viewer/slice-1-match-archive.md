# Slice 1/5: matching, hits from every source, the archive scan, the early output

Branch `impl/canary-hit-viewer-1-match-archive`. Spec: decisions 2, 3, 4, 5, 11 (*Matching*, *Sources*, *Hits*),
*Early output*, clarification 1. Global constraints: [README](README.md#global-constraints).

### Task 1: `canarymatch.py` and `canary_record.py`, with `metrics.py` and `handoff.py` on them

Decision 2.

**Files:**
- Create: `platform/report/canarymatch.py`, `platform/report/canary_record.py` (ruling 2),
  `platform/report/tests/test_canarymatch.py`
- Modify: `platform/promptfoo-evals/metrics.py` (drop `_unescape`, `_texts`, `_word`, `_found`,
  `URL`, `_hosts`, `_received`; import them), `platform/promptfoo-evals/handoff.py` (`METADATA_TYPES`,
  `is_file_canary` imported from `canarymatch`; `ConfigError`, `_scalar`, `read_hosts`, `load_canaries` from
  `canary_record`), `BACKLOG.md` (the *Next* line for the ladder's upstream port: that port now needs
  `platform/report/canarymatch.py` and `canary_record.py`, from this track's upstream port or carried itself),
  `docs/specs/2026-11-10-canary-hit-viewer.md` (Glossary: *File canary* points at `canarymatch.py`)
- Test: `platform/promptfoo-evals/tests/test_metrics.py` (add one test),
  `platform/agui/pydantic-ai-agent/tests/test_airlock.py` (add one test)

**Interfaces:**
- Produces, in `canarymatch`: `unescape(text: str) -> str`; `texts(value: object, depth: int = 0) -> list[str]`;
  `word(token: str) -> re.Pattern` (cached); `found(entries: list[dict], texts: list[str]) -> list[dict]`;
  `URL: re.Pattern`; `hosts(text: str) -> set[str]`; `received(request: dict) -> list[str]`;
  `spans(token: str, text: str) -> list[tuple[int, int]]`; `METADATA_TYPES: frozenset[str]`;
  `is_file_canary(entry: dict) -> bool`. Bodies move verbatim from `metrics.py`/`handoff.py`; only `spans` is new
  (`[m.span() for m in word(token).finditer(text)]`).
- Produces, in `canary_record`: `class RecordError(Exception)`; `load_canaries(dir) -> list[dict]`;
  `read_hosts(dir) -> dict`; `_scalar`; bodies verbatim from `handoff.py` with `ConfigError` read as `RecordError`
  (`load_canaries`'s private `_json` comes along), and `vm_argv(dir) -> list[str]` (the SSH or local command
  prefix from `hosts.yml`, verbatim; slice 2's transport uses it). `handoff.py` inserts the same
  `platform/report` path as `metrics.py` below (it is imported first by `metrics.py`, `controls_provider`,
  `isolation` and `matrix`), then `from canary_record import RecordError as ConfigError, _json, _scalar,
  load_canaries, read_hosts, vm_argv`, so `ManifestError(ConfigError)` and every caller are unchanged.
- `metrics.py` imports by path: `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "report"))`, then
  `from canarymatch import texts as _texts, found as _found, …`, so its metric bodies stay unchanged.

- [ ] **Step 1: Write the failing tests** in `test_canarymatch.py`:
  `test_texts_reads_escaped_and_json` (`texts('{"a": "x\\nFCANARY-TEST01"}')` contains a reading where
  `word("FCANARY-TEST01")` matches), `test_word_is_whole_word` (no match in `FCANARY-TEST011`),
  `test_spans_positions` (`spans("FCANARY-TEST01", "ab FCANARY-TEST01 c") == [(3, 17)]`),
  `test_received_form_decoded` (`received({"path": "/x?q=FCANARY%2DTEST01", "body": None})` matches),
  `test_hosts`, `test_record_readers` (`read_hosts` and `load_canaries` over a `hosts.yml` and `canaries.json` written to
  `tmp_path`; an encrypted-only record raises `RecordError`), `test_is_file_canary` (a `drs-…` metadata type is not a file canary; take the type names from
  `handoff.METADATA_TYPES` as it is now). In `test_metrics.py`: `test_matching_lives_in_canarymatch`: the source
  of `metrics.py` defines none of `def _texts`, `def _unescape`, `def _word`, `def _found`, `def _received`,
  `def _hosts`. In `test_airlock.py`: `test_airlock_does_not_import_canarymatch` (the airlock's source has no
  `canarymatch`).
- [ ] **Step 2: Run** `uv run --with pytest --with markdown pytest platform/report/tests/test_canarymatch.py -q` and
  `(cd platform/promptfoo-evals && uv run --group dev pytest tests/test_metrics.py -q)`. Expected: FAIL (no module
  `canarymatch`; the grep test fails).
- [ ] **Step 3: Move the functions** into `canarymatch.py` and `canary_record.py` and import them in `metrics.py`
  and `handoff.py`; `canary_record.py` and `canarymatch.py` import nothing from `platform/promptfoo-evals/`.
- [ ] **Step 4: Run** both suites in full and the agent's. Expected: PASS, with every pre-existing metrics test
  unchanged.
- [ ] **Step 5: Commit** `Move canary matching and the record readers into platform/report`.

### Task 2: places and hits, per source

Decisions 3, 4, 5; clarification 1.

**Files:**
- Create: `platform/report/canary_hits.py`, `platform/report/tests/test_canary_hits.py`,
  `platform/report/tests/fixtures/canary/` (`canaries.json` with one file canary `FCANARY-TEST01`, one metadata
  canary `MCANARY-TEST02`, one `FCANARY-TEST011`; `hosts.yml` with `api_host: api.spe.test`; a journal
  `agui-journals/s1.jsonl`; `agent-runs.jsonl`; `openwebui-export.json`; `requests.jsonl`)

**Interfaces:**
- Consumes: `canarymatch` (Task 1).
- Produces:
  - `@dataclass Place`: `frontend: str | None`, `source: str`, `session: dict | None` (`{"id", "title"}`),
    `run: str | None`, `at: str | None`, `prompt: str | None`, `place: str`, `tool: dict | None`
    (`{"name", "call_id", "args", "result"}` as raw values), `value: object` (what is matched).
  - `class JournalReader`: `__init__(session_id: str)`; `feed(line: dict) -> list[Place]`. Keeps the session title
    (`meta` lines), each open run's prompt (`run_start.messages`, `role == "user"`, joined), and per open run the
    pieces of tool calls (`TOOL_CALL_START` name and id, `TOOL_CALL_ARGS` deltas) and text messages
    (`TEXT_MESSAGE_CONTENT` deltas by `messageId`). Emits a `tool_args` place at `TOOL_CALL_END`, a `tool_result`
    place at `TOOL_CALL_RESULT` (with the call's name and args), an `answer` place at `TEXT_MESSAGE_END`, a
    `prompt` place at `run_start`, and whatever is still open at `run_end`. `REASONING_*` events are ignored.
    `at` is the line's `at`; `frontend` `agui`; `source` `agui-journal`.
  - `agent_run_places(record: dict, titles: dict[str, str]) -> list[Place]`: `prompt` from `input`,
    `tool_args`/`tool_result` per `tool_calls` item (`id`, `name`, `args`, `result`), `answer` from `answer`;
    `run` `run_id`, `session` `{"id": thread_id, "title": titles.get(thread_id)}`, `at` `started` (epoch
    seconds, as ISO 8601 UTC); `frontend` `agui`, `source` `agent-runs`. Records `{"type": "title", "thread_id",
    "title"}` (`app.py`, `title.py`) give no places: the caller collects them into `titles`.
  - `openwebui_places(chat: dict, source: str) -> list[Place]`, for one item of the export's `chats` or one
    database row (`id`, `title`, `chat` JSON): per assistant message in `chat.history.messages`, `run` = its
    `id`, `at` its `timestamp` (epoch seconds, as ISO 8601 UTC), `prompt` the `content` of its `parentId`
    message; `tool_args` per `output` item of type `function_call` (`call_id`, `name`, `arguments`),
    `tool_result` per `function_call_output` (matched to its call by `call_id`), `answer` from its `content`; and
    one `prompt` place per user message. `frontend` `openwebui`.
  - `receiver_places(request: dict) -> list[Place]`: one `request` place, `value` the request, all trace fields
    `None`, `frontend` `None`, `source` `receiver`.
  - `hits_for(place: Place, canaries: list[dict], api_host: str | None) -> list[dict]`: one partial hit record per canary
    found (spec *Hits*, without `id`, `detected`, `workspace`, `instance`, `owner`). Kind: `answer`→`answer`;
    `tool_result`→`touched` if `is_file_canary` else `seen`; `tool_args`→`sent` if the readings name a host
    other than `api_host` (any host when it is `None`) else `args`; `prompt`→`prompt`; `request`→`delivered` (readings from `received`). The
    excerpt is cut from the first reading with a span: at most 400 characters centred on the match, `start`/`end`
    the match within the excerpt; `tool.args` and `tool.result` excerpts the same way (400 characters, around the
    match when it is in them, else their start); `prompt` cut to 400.
  - `dedup_key(hit: dict, generation: str) -> str`: SHA-256 hex of `workspace|generation|run|place|call_id|token`.

- [ ] **Step 1: Write the failing tests** in `test_canary_hits.py`, over the fixtures:
  `test_kind_per_place` (one place per kind gives that kind, all seven), `test_metadata_in_result_is_seen`,
  `test_split_args_found` (a token split across two `TOOL_CALL_ARGS` deltas, fed as two `feed` calls, gives one
  `tool_args` place whose value holds the whole token), `test_reasoning_ignored`,
  `test_journal_trace_fields` (session title from `meta`, prompt from `run_start`, tool name and call id),
  `test_openwebui_places` (a `function_call` with `FCANARY-TEST01` in its output gives `touched` with `frontend`
  `openwebui`, `run` the assistant message id, `prompt` the parent's content),
  `test_receiver_hit_has_nulls` (`frontend`, `session`, `run`, `prompt`, `tool`, `at` all `None`),
  `test_one_hit_per_place` (one canary in args, result and answer of one run: three hits),
  `test_prefix_token_not_matched` (`FCANARY-TEST011` in a result gives only that canary),
  `test_excerpt_at_most_400` (a 10 000-character result: excerpt ≤ 400, and
  `excerpt.text[start:end] == token`), `test_record_schema` (every key of the spec's record present, `null` where
  the source lacks it). And decision 2's acceptance check, in `platform/promptfoo-evals/tests/test_metrics.py`:
  `test_watcher_agrees_with_metrics`: over one fixture trace (a run with a file canary read by a tool, a metadata
  canary in a listing, a canary in the answer and one sent to the receiver), the set of (kind, canary type,
  `file`) from `hits_for` equals the set `canary_answer`, `canary_touched`, `canary_sent` and `canary_delivered`
  name in their reasons (`seen` has no metric: compare it with `touched`'s metadata exclusion).
- [ ] **Step 2: Run** `uv run --with pytest --with markdown pytest platform/report/tests/test_canary_hits.py -q`.
  Expected: FAIL (no module).
- [ ] **Step 3: Implement** `canary_hits.py` to the interfaces above.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Canary hits: places from journals, run log, Open WebUI and receiver`.

### Task 3: the hits file and `canary_watch.py --archive`

Decision 3 (dedup), decision 5, decision 10 (ids).

**Files:**
- Modify: `platform/report/canary_hits.py` (add `HitsFile`)
- Create: `platform/report/canary_watch.py`, `platform/report/tests/test_canary_watch.py`, fixture
  `platform/report/tests/fixtures/canary/run/` (an archived run: `report.json` naming workspace and owner,
  `canaries.json`, `agui/agui-journals/`,
  `agui/agent-runs.jsonl`, `agui/openwebui-export.json` with the journal's run reshaped, `openwebui-export.json`)

**Interfaces:**
- Produces:
  - `class HitsFile`: `__init__(path: str, max_bytes: int = 10_000_000)`; `append(hit: dict) -> int | None`
    (sets `id` to the next line number, starting at 1, writes one JSON line with mode 0640 on create, returns the
    id, `None` once full); `full: bool`; `read(after: int = 0) -> list[dict]`.
  - `scan_archive(run_dir: str, hits: HitsFile, seen: set[str], meta: dict, api_host: str | None,
    generation: str) -> int` in
    `canary_watch.py`: reads `<run_dir>/canaries.json`, the journals, `agui/agent-runs.jsonl`, and `<run_dir>/openwebui-export.json` (never
    `agui/openwebui-export.json`); stamps `detected`, `workspace`, `instance`, `owner` from `meta`; appends each
    hit whose `dedup_key` is not in `seen`; returns the count. Journals first, so their copy wins.
  - CLI: `canary_watch.py --archive RUN_DIR --out HITS.jsonl [--html PAGE.html] [--api-host HOST]`. `meta` comes
    from the run's `report.json` (the report sidecar's copy: `workspace_id`, the workspace's UUID, as
    `workspace`; `owner`, `instance`), else from `run.yml` (`instance`, `participant`), workspace `null`. The
    daemon passes the workspace's generation (slice 2), so the on-stop scan's keys match the live poll's; the
    CLI passes `"archive"`.
- The archive does not keep the API host (`run_archive/tasks/write.yml`'s `run_record` has none). The daemon
  passes the workspace's `hosts.yml` `api_host`; by hand it is `--api-host`, else the instance's output
  directory's `hosts.yml` when it still exists, else `None`: then any URL host in a call's arguments counts as
  foreign (`sent`), as a host built from a shell variable does in `canary_sent`.

- [ ] **Step 1: Write the failing tests**: `test_archive_one_hit_per_canary_and_place` (the fixture run's
  journal, `agent-runs.jsonl` and `agui/openwebui-export.json` hold the same run: one hit per canary and place,
  `source` `agui-journal`), `test_archive_reads_openwebui_export` (a hit with `frontend` `openwebui`),
  `test_openwebui_resaved_once` (the same chat scanned twice: no new hit), `test_ids_are_line_numbers`,
  `test_hits_file_mode_0640`, `test_hits_file_cap` (`max_bytes=2000`: `append` returns `None` and `full` is true),
  `test_cli_logs_no_token` (run the CLI on the fixture with `capsys`/subprocess: stdout and stderr hold no
  fixture token).
- [ ] **Step 2: Run** `uv run --with pytest --with markdown pytest platform/report/tests/test_canary_watch.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implement** `HitsFile`, `scan_archive` and the CLI.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Canary watch: scan an archived run into a hits file`.

### Task 4: the participant page as a static file, and the early output

Decisions 4, 5, 11; *Early output*; ruling 4.

**Files:**
- Create: `platform/report/hits_view.py`, `platform/report/static/hits.css`,
  `platform/report/tests/test_hits_pages.py`,
  `docs/superpowers/plans/2026-11-10-canary-hit-viewer/evidence/slice-1/counts.md`

**Interfaces:**
- Produces: `participant_body(meta: dict, hits: list[dict], status: dict | None) -> str` (the page's HTML body:
  header with workspace and status, the headline counts per loud kind, "also seen: N" for quiet kinds, the
  notice, then hits newest first, each a `<details>` with time, kind, canary type and file, frontend label
  ("AG-UI" or "Open WebUI"), session title, run, prompt, tool, result and excerpt with the value in `<mark>`);
  `standalone(title: str, body: str) -> str` (a whole HTML document with `hits.css` inlined, no script). Every
  field passes `html.escape`.
  `NOTICE = "Matching is literal: an encoded, split or paraphrased canary is not seen."`

- [ ] **Step 1: Write the failing tests**: `test_notice_on_participant_page`, `test_counts_loud_and_quiet`
  (2 `touched`, 1 `answer`, 3 `seen`: headline "3 leaks", "also seen: 3"), `test_frontend_labels` (one `agui`
  and one `openwebui` hit: both labels present), `test_value_marked` (`<mark>FCANARY-TEST01</mark>`),
  `test_escapes_fields` (a title `<script>x</script>` appears escaped).
- [ ] **Step 2: Run** `uv run --with pytest --with markdown pytest platform/report/tests/test_hits_pages.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implement** `hits_view.py` and `hits.css`; wire `--html` in the CLI.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Hits view: the participant page as static HTML`.
- [ ] **Step 6: The early output.** Pick archived runs with hits: copy the slice's five modules and `static/hits.css` to a temporary
  directory on the portal (`ssh agent-service-1 'mktemp -d'`, `scp`), run
  `sudo python3 canary_watch.py --archive /data-share/runs/<run> --out <tmp>/<run>.jsonl --html
  /data-share/canary-hits/early-output/<run>.html` over every run (create the directory as `root:sperange-report`
  0750 if it is missing; HTML files 0640), then remove the temporary directory. Write per run the counts per kind
  and frontend, no value, into `evidence/slice-1/counts.md`. Read two pages against decisions 4, 5 and 11 before
  asking (`development-workflow.md`, *Slicing implementation*): a hit that surprises you is a bug until a
  decision explains it. Commit `Slice 1 early output: hit counts over the portal's archive`.
- [ ] **Step 7: Ask** in one PR comment, no gate: the page paths on the portal, the counts, and the questions
  the spec's *Early output* names (is the trace enough, are quiet kinds too loud or hidden, does showing the value
  read as intended), each answerable in a word.
