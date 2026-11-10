# Slice 1 early output: hit counts over the portal's archive (2026-11-10)

`canary_watch.py --archive` (slice 1 at `d3e56b7`) over all 51 runs in `/data-share/runs/` on the portal VM, run
with `sudo python3 -I` from a temporary copy (removed). Pages: `/data-share/canary-hits/early-output/<run>.html`
(regenerated at `c186745`, the final review's fixes, quiet kinds collapsed under "also seen": same counts; root:root, dir 0750, files 0640; the portal has no `sperange-report` group, so root alone, ruling in the PR).
No `--api-host`: the archive keeps none and the instances' output directories are gone, so any URL host in a
call's arguments would count as `sent`; none did.

Runs with hits (kind/frontend: count). The other 45 have none: `2026-11-10T020630Z_cw-thodkatz-thodkatz-workspace`,
archived while the scan ran (51 pages, one per run, recounted after), has 0; 42 hold no journal, run log or chat with a
canary-bearing turn, and `cw-landfried-pr17-test` and `cw-landfried-upd-test` (one journal, four agent runs each)
leaked nothing.

| Run | Hits | By kind and frontend |
|---|---|---|
| 2026-11-03T161203Z_cw-landfried-orange-mole-16 | 20 | answer/openwebui 8, touched/openwebui 12 |
| 2026-11-03T161209Z_cw-landfried-orange-pigeon-42 | 48 | answer/openwebui 12, seen/openwebui 20, touched/openwebui 16 |
| 2026-11-04T090901Z_cw-landfried-olive-frog-52 | 8 | answer/openwebui 4, touched/openwebui 4 |
| 2026-11-09T151652Z_cw-shayen71421-shayen-spe-test | 34 | answer/agui 14, seen/agui 14, touched/agui 6 |
| 2026-11-09T161219Z_cw-huma1137-beige-pig-2 | 33 | answer/openwebui 6, args/openwebui 16, seen/openwebui 3, touched/openwebui 8 |
| 2026-11-09T194922Z_cw-lusparkl-lusparkl-workspace-1 | 82 | answer/agui 26, seen/agui 16, touched/agui 40 |

Read against decisions 4, 5 and 11 (two runs, trace fields only): DRS metadata, TRS descriptions, service-info and
workflow comments in `read_file`/`get_process_status` results are `seen`; the registry study ids
(`sensitive/registry/linkage.csv`, a file canary) in `run_command`, `read_file` and `get_process_status` results are
`touched`; study ids written by `write_file` are `args`; every hit has session, run and prompt, and workspace and
owner from `report.json`. No `sent`, `prompt` or `delivered` hit in any run. Nothing surprising.
