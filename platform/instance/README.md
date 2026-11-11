# platform/instance

What runs on an instance from the repository clone there (`spe_repo_dir`,
`/home/ubuntu/sperange`):

| Path | What |
|---|---|
| `compose.yml` | The `spe-frontend` compose project: both chats, the sandbox they share, and (profile `evals`, `spe-experiments` builds only) `evals-view` and `evals-promptfoo`; selected by `COMPOSE_PROFILES` in the frontend directory's `.env`. Linked as `spe_frontend_dir/docker-compose.yml`; mounts the runbook, the prompt and the agent's source from the clone |
| `compose.<name>.yml` | Compose overlays a canary ladder switch adds to the `spe-frontend` project, e.g. `compose.eval-sink.yml` (`spe_eval_sink`: the sandbox resolves the test receiver's name to the VM). The `.env`'s `SPE_COMPOSE_OVERLAYS` (`eval-sink,…`, absent by default) selects them; `spe-apply` passes each with `-f` after `compose.yml` |
| `evals-view/` | The viewer's nginx config and Dockerfile (`spe-apply build evals-view`, `docs/specs/2026-11-10-experiments-design/04-viewer.md`): a read-only `promptfoo view` behind an allow-list proxy, profile `evals` |
| `spe-apply` | Builds the images from the clone and recreates the containers; `stack`, `all` and `ansible` run the Ansible roles on the VM against itself with `instances/local.yml`, written at creation, and all three pass extra arguments through to `ansible-playbook`. On a `spe-experiments` build, every command except the read-only `status`, `logs` and `-h`/`--help`/`help` refuses while an `spe-eval run` or `arm` holds `~/spe-eval/lock` (experiments spec part 03, decision 11), unless `SPE_EVAL_LOCK` names the holder's own token. Linked as `/usr/local/bin/spe-apply` |
| `spe_eval.py` | `spe-eval`'s core library (experiments spec part 03): loading an experiment and checking it against this build (decision 7), the two arms' `-e` values (decision 9), the generated agent suite (R1), the run id/reports layout, the lock (decision 11) and the reading `status`/`wait`/`runs` do over `~/spe-eval/reports/` and the progress file. Standard library plus PyYAML only |
| `spe-eval` | The command line over `spe_eval.py` (experiments spec part 07): `new`, `test`, `arm`, `run` (`--repeat`, `--detach`), `status`, `wait`, `runs`, `results`, `pr-body`. Calls `spe-apply` and `systemd-run` (`$PATH`), `<SPE_REPO_DIR>/platform/promptfoo-evals/run.sh`, `<SPE_REPO_DIR>/check_experiment.py`, and probes the agent's own `/healthz` directly (the same URL the `agui` role's `checks.yml` checks) to wait for the stack. Linked as `/usr/local/bin/spe-eval`, only on a `spe-experiments` build |
| `workspace/AGENTS.md` | The guide for Coder Agents in a workspace: what is live, what needs `spe-apply`, what needs a new template, how to verify |
| `workspace/skills/` | Skills for Coder Agents, linked as `~/.agents/skills/` |

A change in the clone is testable in the instance's chat without rebuilding the
instance. The table in `../coder/README.md`, "Working in a workspace", says what
each change needs.

## `~/spe-eval` (`spe-experiments` builds only)

Everything `spe-eval` keeps on the VM (experiments spec part 03), owned by the workspace user:

| Path | What |
|---|---|
| `handoff/` | The VM-local hand-off (mode 0700): `canaries.json`, `hardening.json` (rewritten per arm), `injections.json`, `trs-installed.json`, `drs-inventory.json`, `ca.crt`, the agent and LLM key files, and `hosts.yml` (`provision: existing`, `ssh_target: localhost`). None of it is mounted into any container (decision 8) |
| `reports/<experiment>/<run id>/<arm>/` | Every kept run: `controls.json`, `agent.json`, `hardening.json`, `run.json`, `progress.jsonl` |
| `promptfoo/` | `PROMPTFOO_CONFIG_DIR`: promptfoo's own eval database, so `npx promptfoo view` works on the VM; bind-mounted into `evals-promptfoo` (the **Evaluations** app) too |
| `windows.jsonl` | One line per run (start/end time), so the canary hit watcher can tell an eval hit from a chat hit |
| `lock` | `flock`'d while an `arm` or `run` is in progress (decision 11) |

`archive.yml` copies `reports/`, `promptfoo/` and `windows.jsonl` into the run directory's `evals/` on stop
(`../ansible/README.md`, "Archive and destroy"); on a `spe` build (no `~/spe-eval`) it copies nothing.

Node, npm, npx, `uv` and `uvx` are installed on the host directly (role `spe_eval`, `../ansible/README.md`,
"Experiments") and linked onto `/usr/local/bin`, alongside `spe-apply` and `spe-eval` themselves.
