# The ladder's transcripts survive in the agent's run log

**Symptom.** A canary ladder level was run, its counts committed (`docs/results/<model>/L*.json`), and now the
answers and tool calls behind a count are wanted (which canary, which listing, to show the team), but
`reports/` and `.promptfoo/` are gone: the ladder deletes them after each level (`platform/promptfoo-evals/README.md`,
*Run the suite*), because they hold canaries.

**Where they are.** The agent logs every run to `/var/lib/spe-agent/runs.jsonl` on the instance, in the volume
`spe-frontend_agent-runs`, which the isolation reset (`isolation.NOT_RESTORED`) leaves alone. On `denbi-agui-01`
it held all 286 runs of the 2026-11-09/10 ladder (L0, L0-clean, L1, L1-clean, L2, L3). `destroy.yml` takes the
volume with the VM, so **copy the log to the controller before destroying**. Read it from the agent's container or the volume (the volume path is on the instance under
`/var/lib/docker/volumes/`), write it to `platform/ansible/output/<instance>/ladder-runs/runs.jsonl` with mode
0600, and compare `sha256sum` on both sides. It holds canaries: it stays under `platform/ansible/output/`, never in git.

**Rebuilding the reports.** `platform/promptfoo-evals/replay.py` turns the log back into one promptfoo eval per
level that `promptfoo view` renders, and checks the re-scored canary metrics against the committed counts
(README, *Replaying the run log*). The log caps each field at 16 KiB: on that ladder 567 of 5,310 tool fields
carry `[truncated: …]`.
