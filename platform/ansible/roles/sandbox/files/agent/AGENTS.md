# Workflow runbook

You drive a GA4GH workflow stack that lives on a different machine. You reach it through
three HTTPS APIs and nothing else. This file gives you the exact command for every
operation. Copy the shapes literally and substitute values.

Read the *Constraints* section before anything else. Most wasted effort here comes from
attempting something the system cannot do.

---

## 1. Constraints

| You want to | Can you? |
|---|---|
| List workflows and data | Yes |
| Register a new workflow / version in TRS | Yes |
| Submit a run and poll it | Yes |
| Register a new DRS object (new input data) | **No** — operator only |
| Download an output file | **No** — outputs stay on the workflow machine |
| SSH / docker / read the workflow machine's filesystem | **No** |
| Connect to a `*.weskit.internal` host | **No** — see §2 |

If a user asks for something in the No column, say plainly that it requires the operator
and stop. Do not look for a workaround.

None of the three APIs requires authentication. Do not send an Authorization header and
do not go looking for a token; there isn't one.

---

## 2. Two kinds of address — do not confuse them

**Reachable** — the three environment variables. Every `curl` you run uses one of these:

    $WES_BASE    e.g. https://<ip>/ga4gh/wes/v1
    $DRS_BASE    e.g. https://<ip>/ga4gh/drs/v1
    $TRS_BASE    e.g. https://<ip>/ga4gh/trs/v2

There is a fourth path on the same host: WESkit's own (non-GA4GH) API, which serves run
logs. It has no environment variable, so derive it — never hardcode the IP:

    WESKIT_BASE="${WES_BASE%/ga4gh/wes/v1}/weskit/v1"

**Not reachable** — `trs://trs-filer.weskit.internal:8080/...` and
`drs://drs-filer.weskit.internal:8080/...`. These are *identifiers you place inside a
request body*. The workflow engine resolves them on its own side. Curling one will fail
with a DNS error, and that failure means you made this mistake — not that the service is
down.

TLS: the private CA is installed in this container's trust store. Verification stays on.
Never pass `-k` / `--insecure`.

---

## 3. Discovery — always start here

Never assume an ID exists. Look it up.

**What workflows are registered:**

    curl -sS "$TRS_BASE/tools" | jq '.[] | {id, name, versions: [.versions[].id]}'

**One workflow's versions and descriptor types:**

    curl -sS "$TRS_BASE/tools/TOOL_ID/versions" | jq '.[] | {id, descriptor_type}'

**What data is available:**

    curl -sS "$DRS_BASE/objects" | jq '.[] | {id, name, size}'

**Details of one object** (use this to confirm an ID before putting it in a run):

    curl -sS "$DRS_BASE/objects/OBJECT_ID" | jq '{id, name, size, checksums}'

**Which engines the executor supports** — read this before choosing
`workflow_type` / `workflow_type_version`, rather than trusting §5's table:

    curl -sS "$WES_BASE/service-info" | jq '.workflow_type_versions'

---

## 4. Registering a workflow in TRS

Two steps: create the tool, then create the version with its files inline. There is no
separate file-upload call.

The registry validates strictly. **The ID goes in the URL, never in the body.** Sending
`id` inside the JSON is rejected with `Additional properties are not allowed`.

Use `PUT`, not `POST`. `POST /tools` invents a random ID; `PUT /tools/TOOL_ID` creates the
ID you chose. You want the ID you chose, because §5's TRS URI has to contain it.

Pick a `TOOL_ID` that is lowercase, hyphenated and descriptive.

**Never change a version that has been run. Register a new version ID instead.**

WESkit caches each `<tool>/<version>/<type>/<engine>` directory indefinitely and does not
re-fetch it when TRS changes. Overwrite an existing version and TRS will hold your new
code while WESkit keeps running the old — with no error. The run succeeds and the results
are wrong. Only an operator can resynchronise the cache.

So: every edit to a workflow, however small, gets a new `VERSION_ID`. Never reuse one to
"fix" a workflow.

Choosing the ID — list what exists and take the next number:

    curl -sS "$TRS_BASE/tools/TOOL_ID/versions" | jq -r '.[].id'

Use `v1` for a new tool, otherwise the highest existing `vN` plus one. If the user names a
version, use it, but if that ID already exists tell them it cannot be overwritten and
propose the next number.

The one safe exception: if a *registration* failed and you never submitted a run against
that ID, nothing was cached, so retrying the same ID is fine. Once any run has referenced
a version, that ID is frozen for good.

Always tell the user which tool and version you registered and ran. That pairing is the
only provenance record connecting a result to the code that produced it.

**Step 1 — the tool.** `organization`, `toolclass` and `versions` are required; omit any
of them and the call fails.

    curl -sS -X PUT "$TRS_BASE/tools/TOOL_ID" \
      -H 'Content-Type: application/json' \
      -d '{
        "organization": "local",
        "name": "Human readable name",
        "description": "What this workflow does",
        "has_checker": false,
        "toolclass": {
          "id": "workflow",
          "name": "Workflow",
          "description": "Runnable workflow"
        },
        "versions": []
      }'

`"versions": []` is correct here — the version is created separately in step 2.

**Step 2 — the version and its files together.** Again the ID is in the URL and must not
appear in the body. Each entry in `files` carries three things: `tool_file` (the path and
role), `file_wrapper` (the content), and `type` (the descriptor type, `NFL` or `SMK`).

**`is_production` is not optional in practice — always send `"is_production": false`.**
The schema marks it optional, but the implementation reads it directly whenever `files` is
non-empty, so omitting it raises a KeyError and returns 500. An empty version registers
fine without it, which makes this look like a file problem when it isn't.

Do not set it to `true` unless you are also supplying a checksum for every file, which the
implementation then demands. There is no benefit here to `true`.

The primary descriptor must be named `main.nf` (Nextflow) or `Snakefile` (Snakemake),
because that is the filename §5's TRS URI points at.

    curl -sS -X PUT "$TRS_BASE/tools/TOOL_ID/versions/VERSION_ID" \
      -H 'Content-Type: application/json' \
      -d '{
        "name": "VERSION_ID",
        "is_production": false,
        "descriptor_type": ["NFL"],
        "files": [
          {
            "tool_file": {"path": "main.nf", "file_type": "PRIMARY_DESCRIPTOR"},
            "file_wrapper": {"content": "<workflow source as a JSON string>"},
            "type": "NFL"
          }
        ]
      }'

Additional files (`nextflow.config`, included modules) go in the same array with
`"file_type": "SECONDARY_DESCRIPTOR"`.

**Build the JSON with a tool, not by hand.** Embedding a workflow as a JSON string will go
wrong on quoting, newlines and backslashes:

    cat > /tmp/main.nf <<'EOF'
    ...workflow source...
    EOF

    jq -n --rawfile c /tmp/main.nf --arg v "VERSION_ID" '{
      name: $v,
      is_production: false,
      descriptor_type: ["NFL"],
      files: [{
        tool_file: {path: "main.nf", file_type: "PRIMARY_DESCRIPTOR"},
        file_wrapper: {content: $c},
        type: "NFL"
      }]
    }' > /tmp/version.json

    curl -sS -X PUT "$TRS_BASE/tools/TOOL_ID/versions/VERSION_ID" \
      -H 'Content-Type: application/json' --data-binary @/tmp/version.json

**Verify before submitting a run.** A failed registration surfaces later as a confusing
500 or SYSTEM_ERROR from WES, not as an obvious error, so check here:

    curl -sS "$TRS_BASE/tools/TOOL_ID/versions/VERSION_ID/NFL/descriptor" | head

If either step failed, stop. Do not submit a run against a tool that does not exist.

**If the schema rejects your body**, the error text is precise — obey it literally:

- `Additional properties are not allowed ('X' was unexpected)` — delete field `X`. Do not
  rename it or nest it elsewhere.
- `'X' is a required property` — add field `X`.

The registry's schema is authoritative over this document. If the two disagree, follow the
error and tell the user which field differed, so the runbook can be corrected.

Use `SMK` in place of `NFL` throughout for Snakemake.


## 5. Submitting a run

`POST $WES_BASE/runs` is multipart. Five fields matter.

- `workflow_url` — a TRS URI naming the primary descriptor:
  `trs://trs-filer.weskit.internal:8080/TOOL_ID/VERSION_ID/NFL/main.nf`
- `workflow_params` — JSON. Input files are **not** paths; each is an object
  `{"drs_uri": "drs://drs-filer.weskit.internal:8080/OBJECT_ID"}`.
- `workflow_type` — `NFL` or `SMK`
- `workflow_type_version` — engine version from `/service-info`
- `workflow_engine_parameters` — optional JSON, usually `{}`

Engine versions (confirm against `/service-info` — that is authoritative, this table is a
reminder):

| Engine | `workflow_type` | `workflow_type_version` |
|---|---|---|
| Nextflow | `NFL` | `25.04.3` |
| Nextflow, tasks pull their own containers | `NFL` | `25.04.3-singularity` |
| Snakemake | `SMK` | `9.16.3` |
| Snakemake, tasks pull their own containers | `SMK` | `9.16.3-singularity` |

Use a `-singularity` variant only when the workflow's own processes declare container
images. If unsure, try the plain variant first and read the error.

**The command:**

    curl -sS -X POST "$WES_BASE/runs" \
      -F 'workflow_type=NFL' \
      -F 'workflow_type_version=25.04.3' \
      -F 'workflow_url=trs://trs-filer.weskit.internal:8080/TOOL_ID/VERSION_ID/NFL/main.nf' \
      -F 'workflow_engine_parameters={}' \
      -F 'workflow_params={"input_file":{"drs_uri":"drs://drs-filer.weskit.internal:8080/OBJECT_ID"},"threads":2}'

The response is `{"run_id": "..."}`. Capture it and report it to the user immediately —
it is the only handle on the run.

For anything beyond a couple of parameters, build `workflow_params` with `jq` and pass it
as a file to avoid shell quoting damage:

    jq -n '{input_file: {drs_uri: "drs://drs-filer.weskit.internal:8080/OBJECT_ID"}}' \
      > /tmp/params.json
    # then: -F workflow_params=</tmp/params.json

---

## 6. Monitoring

**Cheap status check:**

    curl -sS "$WES_BASE/runs/RUN_ID/status" | jq

**Full detail — outputs, logs, exit codes:**

    curl -sS "$WES_BASE/runs/RUN_ID" | jq

States progress roughly `QUEUED → INITIALIZING → RUNNING → COMPLETE`, or terminate at
`EXECUTOR_ERROR`, `SYSTEM_ERROR` or `CANCELED`.

**Poll like this** — sleep between checks, and give up rather than looping forever:

    for i in $(seq 1 60); do
      s=$(curl -sS "$WES_BASE/runs/RUN_ID/status" | jq -r .state)
      echo "$(date +%T) $s"
      case "$s" in COMPLETE|EXECUTOR_ERROR|SYSTEM_ERROR|CANCELED) break;; esac
      sleep 20
    done

Adjust the loop bound to the expected runtime, and tell the user roughly how long you
intend to wait. If you hit the bound, report the run ID and last state and let them ask
you to resume — do not silently keep polling.

**Read the logs.** WESkit serves stdout and stderr as actual content, in any run state,
as soon as the executor has created the file:

    curl -sS "$WESKIT_BASE/runs/RUN_ID/stderr" | jq -r .content
    curl -sS "$WESKIT_BASE/runs/RUN_ID/stdout" | jq -r .content

A 404 means the log does not exist *yet* — the run has not got far enough. That is a
normal state early on, not a failure. Wait and retry rather than reporting an error.

Because these work while a run is still going, use stderr to check on a long run rather
than only polling `state`. And when a run fails, read stderr *first* — it usually contains
the answer, and it is the only place the real error text appears.

**Cancel:**

    curl -sS -X POST "$WES_BASE/runs/RUN_ID/cancel"

---

## 7. Reporting back

On success, give the user: the run ID, the final state, the output paths from
`run_log`/`outputs`, and the wall time. State explicitly that the paths are on the
workflow machine and that an operator must retrieve the files.

On failure, give them: the run ID, the final state, and the actual error text from
`$WESKIT_BASE/runs/RUN_ID/stderr`, plus the exit code from `GET $WES_BASE/runs/RUN_ID`.
Quote the error verbatim. Do not paraphrase it into something vaguer, do not report only
the state, and do not offer a diagnosis you cannot support from the log.

---

## 8. When something goes wrong

**`Could not resolve host: trs-filer.weskit.internal`** — you tried to curl an internal
name. Those go inside request bodies only. Re-read §2.

**SSL certificate verification failed** — configuration problem on the operator's side
(wrong trust anchor, or the server's IP changed). Report it. Do not disable verification.

**404 on `POST $WES_BASE/runs`** — check `$WES_BASE` includes `/ga4gh/wes/v1`.

**Run goes straight to `SYSTEM_ERROR`** — usually the TRS URI doesn't resolve. Verify the
descriptor is fetchable (end of §4), and check the filename in the URI matches the
`path` you registered.

**Run reaches `EXECUTOR_ERROR`** — read `$WESKIT_BASE/runs/RUN_ID/stderr` before
theorising. Common causes: a DRS object ID that doesn't exist, or an input passed as a
bare string where the workflow expected a `drs_uri` object. Re-check the object with
`GET $DRS_BASE/objects/OBJECT_ID`.

**stderr says `singularity: command not found`** — you submitted with a plain engine
variant but the workflow's processes declare container images. Resubmit with the matching
`-singularity` version from §5. This failure happens almost immediately.

**`Additional properties are not allowed ('id' was unexpected)` from TRS** — you put the
ID in the JSON body. It belongs in the URL. See §4.

**500 from TRS when registering a version with files** — first suspect: you omitted
`"is_production": false`. The service crashes on the missing key rather than reporting it.
Add the field and retry before investigating anything else. A version with an empty `files`
array succeeds without it, so do not conclude from that success that your file entries are
at fault.

**500 from TRS on a version call, with `is_production` already set** — likely a *cascade*:
the tool creation before it failed, so you are adding a version to something that does not
exist. Go back, re-run step 1 of §4, and read that response.

**A workflow fix had no effect — the run reproduces the old behaviour, or stderr points at
a line that is no longer in the file** — you overwrote an existing version and WESkit is
running its cached copy. Do not resubmit; you will get the same result. Register the code
under a new version ID and run that. If the stale version must be repaired in place, that
is an operator task.

**Any 4xx from TRS** — print the full response body before reacting. The filers return
precise validation messages naming the exact offending field, and those are lost if you
only look at the status code.

If two attempts at the same thing fail the same way, stop and report to the user with the
exact commands and responses. Do not keep varying the request hoping something sticks.

---

## 9. Worked example

> "Run the QC workflow on sample A and give me the results."

    # 1. find it
    curl -sS "$TRS_BASE/tools" | jq '.[] | {id, name}'
    #    → {"id": "fastqc-basic", "name": "Basic read QC"}
    curl -sS "$TRS_BASE/tools/fastqc-basic/versions" | jq '.[].id'
    #    → "v1"

    # 2. find the data
    curl -sS "$DRS_BASE/objects" | jq '.[] | {id, name}'
    #    → {"id": "sha256-3f9a...", "name": "sampleA_R1.fastq.gz"}

    # 3. confirm the engine
    curl -sS "$WES_BASE/service-info" | jq '.workflow_type_versions'

    # 4. submit
    curl -sS -X POST "$WES_BASE/runs" \
      -F 'workflow_type=NFL' \
      -F 'workflow_type_version=25.04.3' \
      -F 'workflow_url=trs://trs-filer.weskit.internal:8080/fastqc-basic/v1/NFL/main.nf' \
      -F 'workflow_params={"reads":{"drs_uri":"drs://drs-filer.weskit.internal:8080/sha256-3f9a..."}}'
    #    → {"run_id": "a1b2c3d4"}

    # 5. poll (see §6), then
    curl -sS "$WES_BASE/runs/a1b2c3d4" | jq '{state, outputs, run_log}'
    curl -sS "$WESKIT_BASE/runs/a1b2c3d4/stderr" | jq -r .content | tail -20

Then report: run `a1b2c3d4` COMPLETE, outputs at `<paths>` on the workflow machine,
retrievable by the operator.
