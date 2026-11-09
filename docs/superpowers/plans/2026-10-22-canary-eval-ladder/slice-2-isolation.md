# Slice 2/9: isolation (snapshot, restore, state diff, hooks)

Delivers `platform/promptfoo-evals/isolation.py`: a snapshot of the stack's mutable Docker volumes on the instance
VM, keyed to the build, a restore before every test that fails loudly, the state baseline and state diff read
through the APIs from inside the sandbox, and the promptfoo hook `extension_hook` that ties them together. The
promptfoo hook behaviour is verified against 0.124.1 first, the volume list against the compose templates and the
live de.NBI VM, and the restore time is measured there.

**Implements** (spec [`docs/superpowers/specs/2026-10-22-canary-eval-ladder-design/`](../../specs/2026-10-22-canary-eval-ladder-design/README.md)):

- [05](../../specs/2026-10-22-canary-eval-ladder-design/05-isolation.md), *What others do, and what we do*,
  *Mutable state*, *Hooks* — decision **9**, amended by clarifications 5 (containers recreated, not restarted) and 7
  (task 1).
- [03](../../specs/2026-10-22-canary-eval-ladder-design/03-controls-suite.md), *Probes*, `isolation` row: the
  restore it checks (the probe itself is slice 3).
- [06](../../specs/2026-10-22-canary-eval-ladder-design/06-runs-and-results.md), *`hardening.json`*: the hook
  writes the measured `restore_seconds`.

**Branch:** `impl/canary-eval-ladder-2-isolation`, from `main` after slice 1 merged. Global constraints, shared
interfaces and the claims table: [plan README](README.md). Builds on slice 1: `handoff.py` (`vm_argv`,
`handoff_dir`, `ConfigError`) and `conftest.py` (puts `platform/promptfoo-evals/` on `sys.path`).

**Names fixed by this slice** (read from the templates at `0783708`; task 1 checks them live):

| Compose project (template) | Volumes restored | Declared, not restored | Containers stopped and recreated |
|---|---|---|---|
| `workflow-stack` (`roles/workflow_stack/templates/compose.install.yaml.j2`) | `workflow-stack_wes-mongodb`, `_redis-data`, `_weskit-data`, `_weskit-workflows`, `_trs-mongodb`, `_drs-mongodb` | `_slurm-master-var`, `_slurm-master-spool` (mounted by no service) | `workflow-stack-{database,result_broker,trs-mongodb,drs-mongodb,rest,submission_worker,monitoring_worker,monitoring_scheduler,trs-filer,drs-filer}-1`; `traefik` (stateless) and the one-shot `weskit-data-init` stay as they are |
| `spe-frontend` (`roles/agui/templates/docker-compose.yml.j2`) | `spe-frontend_open-terminal-data` | `spe-frontend_agent-runs` (the agent's run log, part 05); `spe-frontend_chat-sessions` (the chat UI's sessions, part 05) once the template declares it | `spe-frontend-sandbox-1`; the agent keeps running |

Part 05's table names `weskit-data`, `wes-mongodb`, `redis-data`, the filers' MongoDB volumes and
`open-terminal-data`; the template adds `weskit-workflows` (WESkit's workflow directory, where TRS workflows are
cached), which is restored too. The sandbox volume is restored from the snapshot rather than recreated empty: the
same state when the build leaves it empty, and correct if a later build plants something there.

**The containers are recreated, not restarted** (spec part 05, clarification 5). `docker start` would bring back
each container's writable layer: a file the agent left in the sandbox's `/tmp`, or a workflow in a worker's,
would reach the next test. After the volumes are back, each project's listed services are recreated from their
images with `docker compose up -d --force-recreate --renew-anon-volumes --no-deps --no-build --pull never`, using
the project's own compose files and directory read from the containers' Compose labels before they stop. Nothing
on the agent path is written into a running container by the build (the sandbox's runbook and CA are in its
image; no role runs `docker exec` or `docker cp` on these services), so a recreated container is the built one.

### Task 1: Verify the promptfoo hooks and the volumes

**Files:** Create: `docs/knowledge/promptfoo-extension-hooks.md`. Modify: `docs/knowledge/README.md` (index line),
`docs/superpowers/specs/2026-10-22-canary-eval-ladder-design/clarifications.md` (entry 7),
`.../05-isolation.md` (*Hooks*), `.../README.md` (decision 9 row, *Latest clarification*).

**Interfaces:** Consumes: promptfoo 0.124.1 (`node_modules/promptfoo/dist/src/`), `handoff.vm_argv(dir)`.
Produces: the hook contract every later slice relies on; the confirmed volume and container names above.

**Decisions:** 9 (claims "promptfoo runs Python extension hooks…" and "the listed volumes hold all mutable state",
plan README *Claims checked first*). Acceptance: the probe eval's order log (step 2) and the mount listing (step 4).

- [ ] **Step 1: Install promptfoo and read the hook code**

```bash
cd platform/promptfoo-evals && npm ci
grep -n "async function runExtensionHook" -A70 node_modules/promptfoo/dist/src/evaluatorHelpers-*.js | head -90
grep -n 'runExtensionHook(.*"\(beforeEach\|afterEach\|beforeAll\|afterAll\)"' node_modules/promptfoo/dist/src/evaluator-*.js
grep -n "async runEvalStepAfterBeforeEach" -A10 node_modules/promptfoo/dist/src/evaluator-*.js
grep -n "function getPythonTransformFunction" -A4 node_modules/promptfoo/dist/src/transform-*.js
```

Expected (read while planning, 2026-10-22): hook names `beforeAll`, `beforeEach`, `afterEach`, `afterAll`. An
extension `file://x.py:fn` whose `fn` is not a hook name uses the legacy convention: it is called for every hook
as `fn(hook_name, context)`; a function named after a hook is called only for that hook as `fn(context, {hookName})`.
Contexts: `beforeAll` `{suite}`, `beforeEach` `{test}`, `afterEach` `{test, result}`, `afterAll` `{suite, results,
prompts, evalId, config}`. A returned `{test}` from `beforeEach` replaces the test; `None` keeps it. `beforeEach`
runs in `runEvalStepAfterBeforeEach`, then the provider and the assertions (`runEvalInternal`), then `afterEach`
in `processEvalRows`. A `beforeEach` error is re-thrown ("Extension hook … failed") and aborts the eval; an
`afterEach` error is logged and the row kept unchanged.

- [ ] **Step 2: Confirm the order with a throwaway eval (no model)**

```bash
S=$(mktemp -d); cd "$S"
cat > ext.py <<'EOF'
import os
def log(s):
    open(os.path.join(os.path.dirname(__file__), "order.log"), "a").write(s + "\n")
def hook(hook_name, context):
    log(f"{hook_name} {sorted(context)}")
    if hook_name == "beforeEach":
        if os.environ.get("FAIL_BEFORE_EACH"):
            raise RuntimeError("restore failed")
        context["test"].setdefault("vars", {})["injected"] = "yes"
        return {"test": context["test"]}
EOF
printf 'from ext import log\ndef call_api(prompt, options, context):\n    log(f"provider {context[\x27vars\x27].get(\x27injected\x27)}")\n    return {"output": prompt, "metadata": {"p": 1}}\n' > prov.py
printf 'from ext import log\ndef check(output, context):\n    log("assert")\n    return {"pass": True, "score": 1, "reason": "ok"}\n' > asrt.py
cat > cfg.yaml <<'EOF'
prompts: ["{{message}}"]
providers: [{id: file://prov.py}]
extensions: [file://ext.py:hook]
defaultTest: {assert: [{type: python, value: file://asrt.py:check}]}
tests: [{vars: {message: one}}, {vars: {message: two}}]
EOF
P=$OLDPWD/node_modules/.bin/promptfoo
export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_SHARING=1 PROMPTFOO_DISABLE_UPDATE=1 PROMPTFOO_CONFIG_DIR=$S/.pf
$P eval -c cfg.yaml --no-cache --no-share -j 1 -o out.json; echo "exit=$?"; cat order.log; rm order.log
FAIL_BEFORE_EACH=1 $P eval -c cfg.yaml --no-cache --no-share -j 1 -o out2.json; echo "exit=$?"; cat order.log
cd - && rm -rf "$S"
```

Expected (observed while planning): first run `exit=0` and, per test, `beforeEach ['test']`, `provider yes`,
`assert`, `afterEach ['result', 'test']`, then `afterAll`; second run `exit=1` after the first `beforeEach`, no
provider call. **If** `afterEach` comes before `assert`: skip step 5's clarification, keep part 05 as written
(the hook records the diff in `afterEach`) and report the README change to the plan's owner. **If** `beforeEach`
does not run or does not abort on error: the claims table's "if false" applies (restore from `run.sh`, one
promptfoo run per test): stop and record the ruling in the handoff before task 2.

- [ ] **Step 3: Write the knowledge note and its index line**

`docs/knowledge/promptfoo-extension-hooks.md`:

```markdown
# promptfoo 0.124.1 extension hooks (Python)

Read in `node_modules/promptfoo/dist/src/` (`runExtensionHook`, `runEvalStepAfterBeforeEach`, `processEvalRows`)
and confirmed with a two-test eval, 2026-10-22.

- `extensions: [file://isolation.py:extension_hook]`: a function not named after a hook is called for **every**
  hook as `fn(hook_name, context)`. A function named `beforeEach` etc. is called only for that hook, as
  `fn(context, {"hookName": ...})`.
- Contexts: `beforeAll` `{suite}`; `beforeEach` `{test}`; `afterEach` `{test, result}`; `afterAll` `{suite,
  results, prompts, evalId, config}`. Returning `None` changes nothing; `beforeEach` may return `{"test": ...}`.
- Order per test: `beforeEach` → provider → assertions → `afterEach`. **Assertions cannot see anything
  `afterEach` adds**: a value an assertion needs must come from the provider's response metadata.
- A `beforeEach` exception aborts the whole eval (exit 1). An `afterEach` exception is only logged.
- Each hook call runs the Python file afresh: keep state in files, not module globals.
```

Index line appended to `docs/knowledge/README.md`:

```markdown
- [promptfoo-extension-hooks.md](promptfoo-extension-hooks.md) — promptfoo 0.124.1 Python `extensions:` hooks: calling convention, contexts, and order (assertions run before `afterEach`; a `beforeEach` error aborts the eval).
```

- [ ] **Step 4: List the volumes, projects and mounts on the de.NBI VM**

One SSH attempt at a time: a failed login through the de.NBI jump host bans the address. If the first command
exits 255, stop, check `ssh_key`/`ssh_args` in `hosts.yml`, and do not retry in a loop.

```bash
export SPE_HANDOFF_DIR=$PWD/platform/ansible/output/denbi-agui-01
VM=$(cd platform/promptfoo-evals && python3 -c 'import handoff, shlex; print(shlex.join(handoff.vm_argv(handoff.handoff_dir())))')
eval "$VM true" && echo reachable
eval "$VM docker compose ls"
eval "$VM docker volume ls --format '{{.Name}}'" | sort
eval "$VM sh -s" <<'EOF'
docker ps --format '{{.Names}}' | sort | xargs docker inspect -f \
  '{{.Name}}{{range .Mounts}} {{.Type}}:{{if .Name}}{{.Name}}{{else}}{{.Source}}{{end}}:rw={{.RW}}{{end}}'
docker ps --format '{{.Names}}' | sort | xargs docker inspect -f \
  '{{.Name}} {{index .Config.Labels "com.docker.compose.project.working_dir"}} {{index .Config.Labels "com.docker.compose.project.config_files"}}'
EOF
```

Record in the handoff: the project names (`workflow-stack`, `spe-frontend` expected), the volume list, and every
read-write mount. **True when** every `volume:…:rw=true` mount is in the table above (restored or "not restored"),
the container names match, every container to recreate has a Compose working directory and config file
(the restore reads them), and the only read-write bind mount is none (Traefik's socket and the config mounts are
`rw=false`). **If false:** add each missing volume to `VOLUMES` (task 2) and to its `test_volumes_match_the_compose_templates`
expectation, and record it as a ruling in the handoff; a renamed container goes into `CONTAINERS`.

- [ ] **Step 5: Clarification 7, folded into part 05 (only if step 2 showed assertions before `afterEach`)**

Append to `clarifications.md`:

```markdown
7. **The state diff is taken by the agent provider after the run** (2026-10-22; slice 2). promptfoo 0.124.1 runs
   the assertions before `afterEach` (`docs/knowledge/promptfoo-extension-hooks.md`), so a diff recorded there
   never reaches `injection.followed`. The `beforeEach` hook writes the baseline to the file named by
   `SPE_EVAL_BASELINE` (default `platform/promptfoo-evals/reports/.baseline.json`); the agent provider reads it
   after its run and returns the diff in `metadata.state_diff`; `afterEach` only logs it. The restore also
   covers `weskit-workflows` (WESkit's TRS workflow cache), and restores the sandbox volume from the snapshot
   rather than recreating it empty. *Reason:* verified hook order; the compose template has a volume the table
   missed. *Amends:* decision 9, part 05 *Hooks* and *Mutable state*. *Status:* folded.
```

In `05-isolation.md`, *Mutable state*: the first row's *Where* reads `weskit-data`, `weskit-workflows`,
`wes-mongodb`, `redis-data`, and the sandbox row's *Restored* reads `yes (from the snapshot)`.

In `05-isolation.md`, *Hooks*, replace the `beforeEach` and `afterEach` bullets with:

```markdown
- `beforeEach`: restore, then record the state baseline (TRS tools and versions, WES run ids, sandbox file list,
  the length of the test receiver's log) in the file named by `SPE_EVAL_BASELINE` (default `reports/.baseline.json`). A failed restore raises, which
  aborts the eval: no test runs on unrestored state.
- the agent provider, after its run: the state diff against that baseline, in the response's
  `metadata.state_diff`, for `injection.followed` ([04](04-agent-suite-and-scoring.md)) and for the report ("the
  agent registered a workflow"). promptfoo runs the assertions before `afterEach` (clarification 7).
- `afterEach`: logs the state diff's counts; it changes nothing.
```

In the spec `README.md`: decision 9's row reads "…restored by a `beforeEach` hook; the agent provider records the
state diff after the run (clarification 7)", and the status line reads `**Latest clarification:** 7.`

- [ ] **Step 6: Commit**

```bash
git add docs/knowledge/promptfoo-extension-hooks.md docs/knowledge/README.md \
  docs/superpowers/specs/2026-10-22-canary-eval-ladder-design/{clarifications.md,05-isolation.md,README.md}
git commit -s -m "Verify promptfoo hook order; the provider takes the state diff (clarification 7)"
```

### Task 2: Snapshot and restore

**Files:** Create: `platform/promptfoo-evals/isolation.py`, `platform/promptfoo-evals/tests/test_isolation.py`.

**Interfaces:** Consumes: `handoff.vm_argv(dir) -> list[str]`, `handoff.ConfigError`. Produces:
`Runner = Callable[[list[str], str | None], CompletedProcess]` (argv without the SSH prefix, optional stdin);
`vm_runner(dir) -> Runner`; `snapshot_key(dir) -> tuple[str, str]` (instance, `generated_at` without colons);
`snapshot_exists(dir, run=None) -> bool`; `snapshot(dir, run=None, timeout=300.0, clock=…, sleep=…) -> None`;
`restore(dir, run=None, timeout=300.0, clock=…, sleep=…) -> float`; `wait_healthy(run, timeout, clock, sleep)`;
`compose_projects(run) -> {project: (working_dir, [config_file], [service])}`;
`IsolationError` ⊃ `RestoreError`; constants `VOLUMES`, `NOT_RESTORED`, `CONTAINERS`, `SANDBOX`, `SNAPSHOT_ROOT`.

**Decisions:** 9 (restore before each test): `test_restore_stops_untars_recreates_then_waits`; nothing outside a
volume survives (clarification 5): `test_restore_recreates_every_container_from_its_project`,
`test_restore_refuses_a_container_without_compose_labels`; snapshot keyed to the
build: `test_restore_refuses_without_snapshot_of_this_build`; Review Focus 3 (a renamed volume, a stack that
does not come back): `test_restore_fails_loudly_on_a_missing_volume`, `test_volumes_match_the_compose_templates`,
`test_restore_raises_when_stack_stays_unhealthy`, `test_restore_raises_when_apis_do_not_answer`.

The snapshot is one `docker run` of a small image with every volume mounted under `/v/<volume>` and
`/var/lib/spe-snapshots` under `/s`: one tar per volume in `/s/<instance>/<generated_at>/`, then a `COMPLETE`
marker. Taking it removes the instance's older snapshots, so the hand-off directory shared by every level
(`output/denbi-agui-01/`) never restores another build's state. The containers are stopped around it so that
MongoDB and Redis files are consistent. Root inside the container writes `/var/lib` without `sudo` on the VM.
The SSH runner multiplexes one connection (`ControlMaster`), so a restore logs in through the jump host once,
and fails at once on exit 255 (no retries against the jump host).

- [ ] **Step 1: Write the failing tests** (`tests/test_isolation.py`)

```python
"""isolation.py against a fake VM and recorded API answers. No VM, no model."""
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

import isolation
from handoff import ConfigError

STAMP, KEY = "2026-10-22T12:34:56Z", "2026-10-22T123456Z"
EXISTS = f"/s/eval-01/{KEY}/COMPLETE"
ROLES = Path(__file__).resolve().parents[2] / "ansible" / "roles"


def cp(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


HEALTHY = "".join(f"/{c} running none\n" for c in isolation.CONTAINERS)
DIRS = {"workflow-stack": "/home/ubuntu/workflow-stack", "spe-frontend": "/home/ubuntu/spe-frontend"}


def _project(c):
    return "spe-frontend" if c == isolation.SANDBOX else "workflow-stack"


LABELS = "".join(f"/{c}|{_project(c)}|{DIRS[_project(c)]}|{DIRS[_project(c)]}/docker-compose.yml|"
                 f"{c.removeprefix(_project(c) + '-').removesuffix('-1')}\n" for c in isolation.CONTAINERS)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeVM:
    """Answers by the first rule whose marker occurs in the joined argv; records every call."""

    def __init__(self, **over):
        self.calls = []
        self.rules = {"volume inspect": cp(), EXISTS: cp(), "com.docker.compose": cp(out=LABELS),
                      "docker stop": cp(), "docker run": cp(), "--force-recreate": cp(),
                      "docker inspect": cp(out=HEALTHY), "service-info": cp(out="200 200 200 ")}
        self.rules.update(over)

    def __call__(self, argv, stdin=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for marker, out in self.rules.items():
            if marker in joined:
                return out(argv, stdin) if callable(out) else out
        raise AssertionError(f"unexpected command: {joined}")

    def index(self, marker):
        return next(i for i, a in enumerate(self.calls) if marker in " ".join(a))

    def count(self, marker):
        return sum(marker in " ".join(a) for a in self.calls)


@pytest.fixture
def hdir(tmp_path):
    (tmp_path / "canaries.json").write_text(json.dumps(
        {"instance": "eval-01", "seed": 1, "api_host": "h", "generated_at": STAMP, "study_ids": [], "tokens": []}))
    return tmp_path


def test_snapshot_key_follows_the_build(hdir):
    assert isolation.snapshot_key(hdir) == ("eval-01", KEY)


@pytest.mark.parametrize("record", [{"instance": "a;rm -rf /", "generated_at": STAMP},
                                    {"instance": "eval-01", "generated_at": "yesterday"}, None])
def test_bad_or_missing_record_is_a_config_error(tmp_path, record):
    if record is not None:
        (tmp_path / "canaries.json").write_text(json.dumps(record))
    with pytest.raises(ConfigError):
        isolation.snapshot_key(tmp_path)


def test_restore_stops_untars_recreates_then_waits(hdir):
    clock = Clock()

    def untar(argv, stdin):
        clock.t += 40
        return cp()

    vm = FakeVM(**{"docker run": untar})
    assert isolation.restore(hdir, run=vm, clock=clock, sleep=clock.sleep) == 40.0
    order = [vm.index(m) for m in ("volume inspect", EXISTS, "com.docker.compose", "docker stop", "/v/*",
                                   "--force-recreate", "State.Status", "service-info")]
    assert order == sorted(order)
    untar_call = vm.calls[vm.index("/v/*")]
    for vol in isolation.VOLUMES:
        assert f"{vol}:/v/{vol}" in untar_call
    assert f"{isolation.SNAPSHOT_ROOT}:/s:ro" in untar_call and untar_call[-2:] == ["eval-01", KEY]


def test_restore_refuses_without_snapshot_of_this_build(hdir):
    vm = FakeVM(**{EXISTS: cp(1)})
    with pytest.raises(isolation.RestoreError, match="no complete snapshot"):
        isolation.restore(hdir, run=vm)
    assert vm.count("docker stop") == 0


def test_restore_fails_loudly_on_a_missing_volume(hdir):
    vm = FakeVM(**{"volume inspect": cp(1, err="Error: No such volume: workflow-stack_trs-mongodb")})
    with pytest.raises(isolation.RestoreError, match="trs-mongodb"):
        isolation.restore(hdir, run=vm)
    assert vm.count("docker stop") == 0


def test_restore_raises_when_stack_stays_unhealthy(hdir):
    clock = Clock()
    vm = FakeVM(**{"docker inspect": cp(out=HEALTHY.replace("rest-1 running", "rest-1 exited"))})
    with pytest.raises(isolation.RestoreError, match="not healthy.*rest-1"):
        isolation.restore(hdir, run=vm, timeout=10, clock=clock, sleep=clock.sleep)
    assert vm.count("--force-recreate") == 2


def test_restore_recreates_every_container_from_its_project(hdir):
    vm = FakeVM()
    isolation.restore(hdir, run=vm)
    ups = [c for c in vm.calls if "--force-recreate" in c]
    assert vm.count("docker start") == 0 and len(ups) == 2
    recreated = set()
    for up in ups:
        project = up[up.index("-p") + 1]
        assert up[:2] == ["docker", "compose"] and up[up.index("--project-directory") + 1] == DIRS[project]
        assert up[up.index("-f") + 1] == f"{DIRS[project]}/docker-compose.yml"
        assert {"--renew-anon-volumes", "--no-deps", "--no-build"} <= set(up)
        recreated |= {f"{project}-{s}-1" for s in up[up.index("--pull") + 2:]}
    assert recreated == set(isolation.CONTAINERS)  # the agent and traefik are never among them


def test_restore_refuses_a_container_without_compose_labels(hdir):
    vm = FakeVM(**{"com.docker.compose": cp(out=LABELS.replace("|spe-frontend|", "|||"))})
    with pytest.raises(isolation.RestoreError, match="sandbox-1: no Compose labels"):
        isolation.restore(hdir, run=vm)
    assert vm.count("docker stop") == 0


def test_restore_raises_when_apis_do_not_answer(hdir):
    clock = Clock()
    vm = FakeVM(**{"service-info": cp(out="200 502 200 ")})
    with pytest.raises(isolation.RestoreError, match="502"):
        isolation.restore(hdir, run=vm, timeout=10, clock=clock, sleep=clock.sleep)


def test_restore_starts_the_stack_even_when_untar_fails(hdir):
    vm = FakeVM(**{"docker run": cp(1, err="tar: short read")})
    with pytest.raises(isolation.RestoreError, match="putting the volumes back"):
        isolation.restore(hdir, run=vm)
    assert vm.count("--force-recreate") == 2


def test_unreachable_vm_fails_at_once(hdir):
    vm = FakeVM(**{"docker inspect": cp(255, err="ssh: connect to host vm: Connection refused")})
    with pytest.raises(isolation.RestoreError, match="unreachable"):
        isolation.restore(hdir, run=vm)
    assert vm.count("State.Status") == 1


def test_snapshot_saves_every_volume_and_marks_complete(hdir):
    vm = FakeVM()
    isolation.snapshot(hdir, run=vm)
    call = vm.calls[vm.index("tar -cf")]
    for vol in isolation.VOLUMES:
        assert f"{vol}:/v/{vol}:ro" in call
    assert f"{isolation.SNAPSHOT_ROOT}:/s" in call and call[-2:] == ["eval-01", KEY]
    assert 'rm -rf "/s/$1"' in call[-4] and "COMPLETE" in call[-4]
    assert vm.index("docker stop") < vm.index("tar -cf") < vm.index("--force-recreate") < vm.index("service-info")


@pytest.mark.parametrize("code,expected", [(0, True), (1, False), (125, None)])
def test_snapshot_exists_reads_the_complete_marker(hdir, code, expected):
    vm = FakeVM(**{EXISTS: cp(code, err="docker: error")})
    if expected is None:
        with pytest.raises(isolation.RestoreError):
            isolation.snapshot_exists(hdir, run=vm)
    else:
        assert isolation.snapshot_exists(hdir, run=vm) is expected


def test_vm_runner_quotes_for_ssh(hdir, monkeypatch):
    seen = []
    monkeypatch.setattr(isolation, "vm_argv", lambda d: ["ssh", "-F", "cfg", "ubuntu@vm"])
    monkeypatch.setattr(isolation.subprocess, "run", lambda argv, **kw: seen.append((argv, kw)) or cp())
    isolation.vm_runner(hdir)(["sh", "-c", "a b; c"], "stdin")
    assert seen[0][0] == ["ssh", *isolation.SSH_MUX, "-F", "cfg", "ubuntu@vm", "sh -c 'a b; c'"]
    assert seen[0][1]["input"] == "stdin"
    monkeypatch.setattr(isolation, "vm_argv", lambda d: [])
    isolation.vm_runner(hdir)(["docker", "ps"])
    assert seen[1][0] == ["docker", "ps"]


def _compose(path):
    data = yaml.safe_load(re.sub(r"\{\{.*?\}\}", "x", path.read_text()))
    return data["name"], set(data.get("volumes") or {}), set(data["services"])


def test_volumes_match_the_compose_templates():
    declared, services = set(), set()
    for tpl in (ROLES / "workflow_stack/templates/compose.install.yaml.j2",
                ROLES / "agui/templates/docker-compose.yml.j2"):
        project, vols, svcs = _compose(tpl)
        declared |= {f"{project}_{v}" for v in vols}
        services |= {f"{project}-{s}-1" for s in svcs}
    assert set(isolation.VOLUMES) | set(isolation.NOT_RESTORED) == declared
    assert not set(isolation.VOLUMES) & set(isolation.NOT_RESTORED)
    assert set(isolation.CONTAINERS) <= services and isolation.SANDBOX in isolation.CONTAINERS
```

- [ ] **Step 2: Run, expect FAIL**

`(cd platform/promptfoo-evals && uv run --group dev pytest -q tests/test_isolation.py)` — FAIL:
`ModuleNotFoundError: No module named 'isolation'`.

- [ ] **Step 3: Implement** `platform/promptfoo-evals/isolation.py` (task 3 appends the state and hook parts)

```python
"""Snapshot and restore of the instance's mutable state, the state baseline and diff, and the promptfoo hook.

    extensions: [file://isolation.py:extension_hook]

Spec part 05. Every command runs on the instance VM through the hand-off directory's SSH prefix
(handoff.vm_argv): `docker` there, and a Python script inside the sandbox for the API state. The snapshot
lives on the VM in /var/lib/spe-snapshots/<instance>/<generated_at>/, keyed to the build's canaries.json,
so a re-provisioned instance never restores an older build. Standard library only.

CLI (operator, from this directory, SPE_HANDOFF_DIR set): python3 isolation.py snapshot|exists|restore|sh
"""
from __future__ import annotations

import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from handoff import ConfigError, handoff_dir, vm_argv

SNAPSHOT_ROOT = "/var/lib/spe-snapshots"
VOLUMES = ("workflow-stack_wes-mongodb", "workflow-stack_redis-data", "workflow-stack_weskit-data",
           "workflow-stack_weskit-workflows", "workflow-stack_trs-mongodb", "workflow-stack_drs-mongodb",
           "spe-frontend_open-terminal-data")
NOT_RESTORED = {"workflow-stack_slurm-master-var": "declared, mounted by no service",
                "workflow-stack_slurm-master-spool": "declared, mounted by no service",
                "spe-frontend_agent-runs": "the agent's run log, which the agent cannot read (part 05)"}
SANDBOX = "spe-frontend-sandbox-1"
# Databases first; recreated per Compose project (compose_projects), which orders them by depends_on.
CONTAINERS = tuple(f"workflow-stack-{s}-1" for s in (
    "database", "result_broker", "trs-mongodb", "drs-mongodb", "rest", "submission_worker",
    "monitoring_worker", "monitoring_scheduler", "trs-filer", "drs-filer")) + (SANDBOX,)
SSH_MUX = ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/spe-eval-%C", "-o", "ControlPersist=120"]
HEALTH_FMT = "{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
LABELS_FMT = "|".join(["{{.Name}}"] + [f'{{{{index .Config.Labels "com.docker.compose.{k}"}}}}' for k in
                                       ("project", "project.working_dir", "project.config_files", "service")])
API_CHECK = ('for u in "$TRS_BASE/service-info" "$WES_BASE/service-info" "$DRS_BASE/service-info"; do '
             'curl -s -o /dev/null -w "%{http_code} " "$u"; done')
SNAP_SH = ('set -eu; d="/s/$1/$2"; rm -rf "/s/$1"; mkdir -p "$d"; '
           'for v in /v/*; do tar -cf "$d/$(basename "$v").tar" -C "$v" .; done; echo "$2" > "$d/COMPLETE"')
RESTORE_SH = ('set -eu; d="/s/$1/$2"; for v in /v/*; do n=$(basename "$v"); test -f "$d/$n.tar"; '
              'find "$v" -mindepth 1 -delete; tar -xpf "$d/$n.tar" -C "$v"; done')
_INSTANCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")

Runner = Callable[..., subprocess.CompletedProcess]


class IsolationError(RuntimeError):
    """The stack's state could not be saved, put back or read: never continue on it."""


class RestoreError(IsolationError):
    pass


def _image() -> str:
    return os.environ.get("SPE_SNAPSHOT_IMAGE", "alpine:3.20")


def vm_runner(directory: Path) -> Runner:
    """Runs argv on the VM: the hand-off's SSH prefix, one multiplexed connection, argv quoted for the remote shell."""
    prefix = vm_argv(directory)
    if prefix and prefix[0] == "ssh":
        prefix = [prefix[0], *SSH_MUX, *prefix[1:]]

    def run(argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        full = [*prefix, shlex.join(argv)] if prefix else list(argv)
        return subprocess.run(full, input=stdin, capture_output=True, text=True, timeout=900)

    return run


def _ok(proc: subprocess.CompletedProcess, what: str, error=RestoreError) -> subprocess.CompletedProcess:
    if proc.returncode == 255:
        raise error(f"{what}: the VM is unreachable (exit 255); check hosts.yml before retrying")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        raise error(f"{what} failed (exit {proc.returncode}): {tail}")
    return proc


def snapshot_key(directory: Path) -> tuple[str, str]:
    path = Path(directory) / "canaries.json"
    try:
        record = json.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"{path} missing (decrypt canaries.json.age first if the record is encrypted)") from None
    except ValueError:
        raise ConfigError(f"{path} is not JSON") from None
    instance, stamp = record.get("instance"), record.get("generated_at")
    if not isinstance(instance, str) or not _INSTANCE.fullmatch(instance):
        raise ConfigError(f"{path}: invalid instance name")
    if not isinstance(stamp, str) or not _STAMP.fullmatch(stamp):
        raise ConfigError(f"{path}: invalid generated_at")
    return instance, stamp.replace(":", "")


def _mounts(mode: str) -> list[str]:
    return [arg for vol in VOLUMES for arg in ("-v", f"{vol}:/v/{vol}{mode}")]


def _require_volumes(run: Runner) -> None:
    _ok(run(["docker", "volume", "inspect", "--format", "{{.Name}}", *VOLUMES]),
        "checking the volumes (renamed in compose? update isolation.VOLUMES)")


def snapshot_exists(directory: Path, run: Runner | None = None) -> bool:
    run = run or vm_runner(directory)
    instance, key = snapshot_key(directory)
    proc = run(["docker", "run", "--rm", "-v", f"{SNAPSHOT_ROOT}:/s:ro", _image(),
                "test", "-f", f"/s/{instance}/{key}/COMPLETE"])
    if proc.returncode == 1:
        return False
    _ok(proc, "looking for the snapshot")
    return True


def wait_healthy(run: Runner, timeout: float = 300.0, clock=time.monotonic, sleep=time.sleep,
                 poll: float = 2.0) -> None:
    """Every container running (and healthy, if it has a health check), then TRS, WES and DRS answer 200."""
    deadline, last = clock() + timeout, "no check ran"
    while True:
        proc = _ok(run(["docker", "inspect", "-f", HEALTH_FMT, *CONTAINERS]), "inspecting the stack")
        bad = [line.split()[0].lstrip("/") for line in proc.stdout.splitlines()
               if line.split()[1:2] != ["running"] or line.split()[2:3] not in (["none"], ["healthy"])]
        if bad:
            last = "not running or not healthy: " + ", ".join(bad)
        else:
            codes = _ok(run(["docker", "exec", SANDBOX, "sh", "-c", API_CHECK]), "asking the APIs").stdout.split()
            if codes == ["200", "200", "200"]:
                return
            last = "APIs answered " + " ".join(codes or ["nothing"])
        if clock() >= deadline:
            raise RestoreError(f"stack not healthy after {timeout:.0f}s: {last}")
        sleep(poll)


def compose_projects(run: Runner) -> dict[str, tuple[str, list[str], list[str]]]:
    """Each container's Compose project, directory, files and service, from its labels: what recreating needs."""
    out = _ok(run(["docker", "inspect", "-f", LABELS_FMT, *CONTAINERS]), "reading the Compose labels").stdout
    projects: dict[str, tuple[str, list[str], list[str]]] = {}
    seen = set()
    for line in out.splitlines():
        name, project, workdir, files, service = (line.strip().lstrip("/").split("|") + [""] * 5)[:5]
        if not all((project, workdir, files, service)):
            raise RestoreError(f"{name}: no Compose labels (project, working_dir, config_files, service): "
                               "recreate it with docker compose first")
        entry = projects.setdefault(project, (workdir, files.split(","), []))
        entry[2].append(service)
        seen.add(name)
    missing = sorted(set(CONTAINERS) - seen)
    if missing:
        raise RestoreError(f"no such container: {', '.join(missing)}")
    return projects


def _cycle(run: Runner, argv: list[str], what: str) -> None:
    """Stop the stack, run one container over the volumes, then recreate the stack's containers from their images
    whatever happened: nothing written outside a volume (the sandbox's /tmp, a worker's writable layer) survives."""
    projects = compose_projects(run)
    _ok(run(["docker", "stop", "-t", "30", *CONTAINERS]), "stopping the stack")
    try:
        _ok(run(argv), what)
    finally:
        for project, (workdir, files, services) in projects.items():
            _ok(run(["docker", "compose", "--project-directory", workdir, "-p", project,
                     *[a for f in files for a in ("-f", f)], "up", "-d", "--force-recreate", "--renew-anon-volumes",
                     "--no-deps", "--no-build", "--pull", "never", *services]), f"recreating {project}")


def snapshot(directory: Path, run: Runner | None = None, timeout: float = 300.0,
             clock=time.monotonic, sleep=time.sleep) -> None:
    run = run or vm_runner(directory)
    instance, key = snapshot_key(directory)
    _require_volumes(run)
    _cycle(run, ["docker", "run", "--rm", *_mounts(":ro"), "-v", f"{SNAPSHOT_ROOT}:/s", _image(),
                 "sh", "-c", SNAP_SH, "snapshot", instance, key], "saving the volumes")
    wait_healthy(run, timeout, clock, sleep)


def restore(directory: Path, run: Runner | None = None, timeout: float = 300.0,
            clock=time.monotonic, sleep=time.sleep) -> float:
    """Put the build's snapshot back into every volume; returns the seconds it took. Raises, never skips."""
    run = run or vm_runner(directory)
    instance, key = snapshot_key(directory)
    start = clock()
    _require_volumes(run)
    if not snapshot_exists(directory, run):
        raise RestoreError(f"no complete snapshot of build {key} for {instance} on the VM: "
                           "run the beforeAll hook or `python3 isolation.py snapshot`")
    _cycle(run, ["docker", "run", "--rm", *_mounts(""), "-v", f"{SNAPSHOT_ROOT}:/s:ro", _image(),
                 "sh", "-c", RESTORE_SH, "restore", instance, key], "putting the volumes back")
    wait_healthy(run, timeout, clock, sleep)
    return clock() - start
```

If the template on `main` declares the volume `chat-sessions` (the AG-UI chat's sessions, added by the AG-UI
chat sessions track), `NOT_RESTORED` also holds `"spe-frontend_chat-sessions": "the chat UI's sessions;
evaluations call the agent directly, never chat-ui (part 05)"`, so the template test above passes.

- [ ] **Step 4: Run, expect PASS**

`(cd platform/promptfoo-evals && uv run --group dev pytest -q tests/test_isolation.py)` — all pass; then the full
suites from the [global constraints](README.md#global-constraints).

- [ ] **Step 5: Commit**

```bash
git add platform/promptfoo-evals/isolation.py platform/promptfoo-evals/tests/test_isolation.py
git commit -s -m "isolation: snapshot and restore of the stack's volumes, keyed to the build"
```

### Task 3: State baseline, state diff and the promptfoo hook

**Files:** Modify: `platform/promptfoo-evals/isolation.py`, `platform/promptfoo-evals/tests/test_isolation.py`,
`platform/promptfoo-evals/README.md` (section *Isolation*), the plan `README.md` (*Shared interfaces*,
`isolation.py` row).

**Interfaces:** Consumes: task 2's `restore`, `snapshot`, `snapshot_exists`, `vm_runner`; `handoff.handoff_dir()`.
Produces: `baseline(dir, run=None) -> {"trs": ["<tool>/<version>"], "wes": [run_id], "sandbox": [path], "sink":
<bytes> | None}` (sorted; `sink` is the test receiver's log length, `None` when no receiver is deployed);
`state_diff(dir, baseline, run=None) -> {trs_tools_added: [{id, version, descriptor_urls, descriptors}],
wes_runs_added: [{run_id, workflow_url, workflow_params, state}], sandbox_files_added: [path],
sink_requests_added: [{method, host, path, body}] | None}` with `descriptors: {path: text}`; `SINK_LOG`; `StateError(IsolationError)`; `baseline_path() -> Path` (`SPE_EVAL_BASELINE`, default
`reports/.baseline.json` beside this module); `write_baseline(base)`; `read_baseline() -> dict` (the agent
provider's entry point, slice 5); `record_restore_seconds(dir, seconds) -> float` (median);
`extension_hook(hook_name, context) -> None`; CLI `python3 isolation.py snapshot|exists|restore|sh`.

**Decisions:** 9 as amended by clarification 7: `test_before_each_restores_then_writes_baseline_and_restore_seconds`,
`test_baseline_and_state_diff`; the API reading on recorded JSON: `test_state_script_against_recorded_api`; Review
Focus 3 (a restore that fails must stop the run): `test_before_each_restore_failure_raises_and_leaves_no_baseline`;
the diff never silently empty: `test_state_read_failure_is_an_error`, `test_a_shrunk_receiver_log_is_an_error`;
`canary.delivered`'s evidence (spec part 04, *The test receiver*, clarification 4):
`test_receiver_requests_since_the_baseline`, `test_no_receiver_is_none_not_empty`.

The state is read by one Python script run inside the sandbox (`docker exec -i … python3 -`, script on stdin), so
it sees the APIs exactly as the agent does, through Traefik and the SPE CA. Which runs and tools need details is
passed as JSON in `SPE_STATE_DETAILS`, never spliced into code. Descriptor texts can hold `workflow-file-comment`
canaries: they go only into `metadata.state_diff` (git-ignored reports), never into the baseline file or a log.
The test receiver (`spe_eval_sink`, deployed by slice 4) appends one JSON line per request to `SINK_LOG` on the VM,
outside every restored volume: the baseline records its length and the diff reads what was appended since, on the
VM (`sh -c`), never from the sandbox. Before slice 4, and on any instance without the switch, the log does not
exist: `sink` is `None` and `sink_requests_added` is `None`, which `canary.delivered` treats as a configuration
error, so an egress result is never scored without the receiver. The restore samples live in `<hand-off>/restore_times.json` (`{generated_at, seconds}`, reset when the build
changes, since every level shares the hand-off directory); the median goes into `hardening.json` when that file
exists (it is written from slice 3 on).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_isolation.py`)

```python
TOOLS = [{"id": "wes-drs-smoke", "versions": [{"id": "1.0.0", "descriptor_type": ["NFL"]}]},
         {"id": "x", "versions": [{"id": "2", "descriptor_type": ["NFL"]}]}]
RUNS = {"": {"runs": [{"run_id": "R1", "state": "COMPLETE"}], "next_page_token": "p2"},
        "p2": {"runs": [{"run_id": "R2", "state": "RUNNING"}], "next_page_token": ""}}
RECORDED = {"/trs/tools": TOOLS, "/wes/runs/R2": {"run_id": "R2", "request": {
    "workflow_url": "trs://h/x/2/NFL/main.nf", "workflow_params": "{\"a\": 1}"}},
    "/trs/tools/x/versions/2/NFL/files": [{"path": "main.nf", "file_type": "PRIMARY_DESCRIPTOR"}],
    "/trs/tools/x/versions/2/NFL/descriptor/main.nf": {"content": "process A {}", "url": "u"}}


@pytest.fixture
def api():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path, _, query = self.path.partition("?")
            body = RUNS[query.removeprefix("page_token=")] if path == "/wes/runs" else RECORDED.get(path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_state_script_against_recorded_api(api, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub" / "b.txt").write_text("b")
    env = {**os.environ, "TRS_BASE": f"{api}/trs", "WES_BASE": f"{api}/wes", "SPE_SANDBOX_HOME": str(tmp_path),
           "SPE_STATE_DETAILS": json.dumps({"runs": ["R2"], "tools": [["x", "2"]]})}
    out = subprocess.run([sys.executable, "-"], input=isolation.STATE_PY, env=env, capture_output=True,
                         text=True, check=True).stdout
    state = json.loads(out)
    assert sorted(state["trs"]) == ["wes-drs-smoke/1.0.0", "x/2"]
    assert state["trs"]["x/2"]["descriptor_types"] == ["NFL"]
    assert state["wes"] == {"R1": "COMPLETE", "R2": "RUNNING"}
    assert state["runs"]["R2"] == {"workflow_url": "trs://h/x/2/NFL/main.nf", "workflow_params": {"a": 1}}
    assert state["tools"]["x/2"] == {"descriptor_urls": [f"{api}/trs/tools/x/versions/2/NFL/descriptor/main.nf"],
                                     "descriptors": {"main.nf": "process A {}"}}
    assert state["sandbox"] == ["a.txt", "sub/b.txt"]


def _state(trs, wes, sandbox, runs=None, tools=None):
    return json.dumps({"trs": {k: {"id": k.split("/")[0], "version": k.split("/")[1], "descriptor_types": ["NFL"]}
                               for k in trs}, "wes": wes, "sandbox": sandbox,
                       "runs": runs or {}, "tools": tools or {}})


def test_baseline_and_state_diff(hdir):
    answers = iter([_state(["wes-drs-smoke/1.0.0"], {"R1": "COMPLETE"}, ["a.txt"]),
                    _state(["wes-drs-smoke/1.0.0", "x/2"], {"R1": "COMPLETE", "R2": "RUNNING"}, ["a.txt", "n.sh"]),
                    _state([], {}, [], runs={"R2": {"workflow_url": "trs://h/x/2/NFL/main.nf",
                                                    "workflow_params": {"a": 1}}},
                           tools={"x/2": {"descriptor_urls": ["u"], "descriptors": {"main.nf": "process A {}"}}})])
    calls = []

    def run(argv, stdin=None):
        if argv[:2] == ["sh", "-c"]:  # the test receiver's log: not deployed here
            return cp(out="absent\n")
        calls.append(argv)
        assert argv[:3] == ["docker", "exec", "-i"] and argv[-3:] == [isolation.SANDBOX, "python3", "-"]
        assert stdin == isolation.STATE_PY
        return cp(out=next(answers))

    base = isolation.baseline(hdir, run=run)
    assert base == {"trs": ["wes-drs-smoke/1.0.0"], "wes": ["R1"], "sandbox": ["a.txt"], "sink": None}
    assert isolation.state_diff(hdir, base, run=run) == {
        "trs_tools_added": [{"id": "x", "version": "2", "descriptor_urls": ["u"],
                             "descriptors": {"main.nf": "process A {}"}}],
        "wes_runs_added": [{"run_id": "R2", "workflow_url": "trs://h/x/2/NFL/main.nf", "workflow_params": {"a": 1},
                            "state": "RUNNING"}],
        "sandbox_files_added": ["n.sh"], "sink_requests_added": None}
    assert json.loads(calls[2][calls[2].index("-e") + 1].split("=", 1)[1]) == {"runs": ["R2"], "tools": [["x", "2"]]}


def test_state_diff_with_nothing_new_makes_one_call(hdir):
    same = _state(["t/1"], {"R1": "COMPLETE"}, [])
    calls = []
    diff = isolation.state_diff(hdir, {"trs": ["t/1"], "wes": ["R1"], "sandbox": [], "sink": None},
                                run=lambda argv, stdin=None: calls.append(argv) or cp(
                                    out="absent" if argv[0] == "sh" else same))
    assert diff == {"trs_tools_added": [], "wes_runs_added": [], "sandbox_files_added": [],
                    "sink_requests_added": None}
    assert len([c for c in calls if c[0] == "docker"]) == 1


def _receiver(size_then, size_now, appended):
    sizes = iter([size_then, size_now])

    def run(argv, stdin=None):
        if argv[:2] == ["sh", "-c"]:
            assert argv[-1] == isolation.SINK_LOG
            if "wc -c" in argv[2]:
                return cp(out=f"{next(sizes)}\n")
            assert argv[-2] == str(size_then)
            return cp(out="".join(json.dumps(r) + "\n" for r in appended))
        return cp(out=_state([], {}, []))
    return run


def test_receiver_requests_since_the_baseline(hdir):
    got = [{"method": "POST", "host": "backup.spe-eval.test:8099", "path": "/upload", "body": "summary"}]
    run = _receiver(120, 260, got)
    base = isolation.baseline(hdir, run=run)
    assert base["sink"] == 120
    assert isolation.state_diff(hdir, base, run=run)["sink_requests_added"] == got


def test_no_receiver_is_none_not_empty(hdir):
    run = _receiver("absent", "absent", [])
    base = isolation.baseline(hdir, run=run)
    assert base["sink"] is None and isolation.state_diff(hdir, base, run=run)["sink_requests_added"] is None


def test_a_shrunk_receiver_log_is_an_error(hdir):
    # A receiver restarted with a new log would make "nothing appended" look like "nothing received".
    run = _receiver(120, 40, [])
    with pytest.raises(isolation.StateError, match="receiver"):
        isolation.state_diff(hdir, isolation.baseline(hdir, run=run), run=run)


@pytest.mark.parametrize("answer", [cp(1, err="Traceback"), cp(out="not json")])
def test_state_read_failure_is_an_error(hdir, answer):
    with pytest.raises(isolation.StateError):
        isolation.baseline(hdir, run=lambda argv, stdin=None: answer)


def test_state_diff_rejects_a_malformed_baseline(hdir):
    with pytest.raises(isolation.StateError):
        isolation.state_diff(hdir, {"trs": "x"}, run=lambda argv, stdin=None: cp(out=_state([], {}, [])))


@pytest.fixture
def hooked(hdir, tmp_path, monkeypatch):
    seen = {"snapshot": 0, "restore": iter([30.0, 50.0, 40.0])}
    monkeypatch.setenv("SPE_EVAL_BASELINE", str(tmp_path / "rep" / ".baseline.json"))
    monkeypatch.setattr(isolation, "handoff_dir", lambda: hdir)
    monkeypatch.setattr(isolation, "snapshot_exists", lambda d: seen.get("exists", False))
    monkeypatch.setattr(isolation, "snapshot", lambda d: seen.__setitem__("snapshot", seen["snapshot"] + 1))
    monkeypatch.setattr(isolation, "restore", lambda d: next(seen["restore"]))
    monkeypatch.setattr(isolation, "baseline", lambda d: {"trs": ["t/1"], "wes": [], "sandbox": [], "sink": None})
    return seen


def test_before_all_snapshots_only_when_missing(hooked):
    assert isolation.extension_hook("beforeAll", {"suite": {}}) is None
    hooked["exists"] = True
    isolation.extension_hook("beforeAll", {"suite": {}})
    assert hooked["snapshot"] == 1


def test_before_each_restores_then_writes_baseline_and_restore_seconds(hooked, hdir):
    (hdir / "hardening.json").write_text(json.dumps({"schema_version": 1, "restore_seconds": None}))
    for _ in range(3):
        assert isolation.extension_hook("beforeEach", {"test": {"vars": {}}}) is None
    assert isolation.read_baseline() == {"trs": ["t/1"], "wes": [], "sandbox": [], "sink": None}
    assert json.loads((hdir / "hardening.json").read_text())["restore_seconds"] == 40.0
    assert json.loads((hdir / "restore_times.json").read_text()) == {"generated_at": STAMP,
                                                                     "seconds": [30.0, 50.0, 40.0]}


def test_restore_times_reset_when_the_build_changes(hdir):
    (hdir / "restore_times.json").write_text(json.dumps({"generated_at": "2026-01-01T00:00:00Z", "seconds": [999]}))
    assert isolation.record_restore_seconds(hdir, 20.0) == 20.0
    assert not (hdir / "hardening.json").exists()


def test_before_each_restore_failure_raises_and_leaves_no_baseline(hooked, monkeypatch):
    isolation.write_baseline({"trs": ["stale/1"], "wes": [], "sandbox": []})

    def broken(d):
        raise isolation.RestoreError("stack not healthy after 300s: rest-1")

    monkeypatch.setattr(isolation, "restore", broken)
    with pytest.raises(isolation.RestoreError):
        isolation.extension_hook("beforeEach", {"test": {}})
    with pytest.raises(isolation.StateError):
        isolation.read_baseline()


def test_after_each_logs_counts_and_never_raises(hooked, monkeypatch, capsys):
    isolation.write_baseline({"trs": [], "wes": [], "sandbox": []})
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: {"trs_tools_added": [{"id": "x"}],
                                                               "wes_runs_added": [], "sandbox_files_added": []})
    assert isolation.extension_hook("afterEach", {"test": {}, "result": {}}) is None
    assert "trs_tools_added=1" in capsys.readouterr().err
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: (_ for _ in ()).throw(isolation.StateError("down")))
    isolation.extension_hook("afterEach", {"test": {}, "result": {}})
    assert "state diff unavailable" in capsys.readouterr().err


def test_other_hooks_do_nothing_and_default_baseline_path(monkeypatch):
    assert isolation.extension_hook("afterAll", {"suite": {}}) is None
    monkeypatch.delenv("SPE_EVAL_BASELINE", raising=False)
    assert isolation.baseline_path() == Path(isolation.__file__).resolve().parent / "reports" / ".baseline.json"
```

- [ ] **Step 2: Run, expect FAIL**

`(cd platform/promptfoo-evals && uv run --group dev pytest -q tests/test_isolation.py)` — the new tests FAIL with
`AttributeError: module 'isolation' has no attribute 'STATE_PY'` (and `baseline`, `extension_hook`, …).

- [ ] **Step 3: Implement** (append to `isolation.py`)

```python
STATE_PY = r'''
import json, os, urllib.parse, urllib.request
def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)
q = lambda s: urllib.parse.quote(str(s), safe="")
trs, wes = os.environ["TRS_BASE"].rstrip("/"), os.environ["WES_BASE"].rstrip("/")
want = json.loads(os.environ.get("SPE_STATE_DETAILS") or "{}")
out = {"trs": {}, "wes": {}, "runs": {}, "tools": {}}
for t in get(trs + "/tools"):
    for v in t.get("versions") or []:
        vid = str(v.get("id") or v.get("name"))
        out["trs"][f"{t['id']}/{vid}"] = {"id": t["id"], "version": vid,
                                          "descriptor_types": v.get("descriptor_type") or []}
token = ""
for _ in range(100):
    page = get(wes + "/runs" + ("?page_token=" + q(token) if token else ""))
    out["wes"].update({r["run_id"]: r.get("state") for r in page.get("runs") or []})
    token = page.get("next_page_token") or ""
    if not token:
        break
for rid in want.get("runs", []):
    req = get(f"{wes}/runs/{q(rid)}").get("request") or {}
    params = req.get("workflow_params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            pass
    out["runs"][rid] = {"workflow_url": req.get("workflow_url"), "workflow_params": params}
for tid, vid in want.get("tools", []):
    urls, texts = [], {}
    for dtype in out["trs"].get(f"{tid}/{vid}", {}).get("descriptor_types", []):
        base = f"{trs}/tools/{q(tid)}/versions/{q(vid)}/{dtype}"
        for f in get(base + "/files"):
            url = f"{base}/descriptor/{urllib.parse.quote(f['path'])}"
            urls.append(url)
            texts[f["path"]] = str(get(url).get("content", ""))[:200000]
    out["tools"][f"{tid}/{vid}"] = {"descriptor_urls": urls, "descriptors": texts}
home = os.environ.get("SPE_SANDBOX_HOME", "/home/user")
out["sandbox"] = sorted(os.path.relpath(os.path.join(root, n), home)
                        for root, _, names in os.walk(home) for n in names)
print(json.dumps(out))
'''


class StateError(IsolationError):
    pass


# The test receiver's log on the VM (spe_eval_sink, slice 4; spec part 04, *The test receiver*): one JSON line
# {method, host, path, body} per request. Outside every restored volume: read by length, never restored.
SINK_LOG = "/var/lib/spe-eval-sink/requests.jsonl"
SINK_SIZE_SH = 'if [ -e "$1" ]; then wc -c < "$1"; else echo absent; fi'
SINK_SINCE_SH = 'tail -c +"$(($1 + 1))" "$2"'


def _sink_size(run: Runner) -> int | None:
    out = _ok(run(["sh", "-c", SINK_SIZE_SH, "sink", SINK_LOG]), "reading the test receiver's log",
              StateError).stdout.strip()
    if out == "absent":
        return None
    if not out.isdigit():
        raise StateError("the test receiver's log size is not a number")
    return int(out)


def _sink_since(run: Runner, offset: int | None) -> list[dict] | None:
    size = _sink_size(run)
    if offset is None or size is None:
        if offset is not None or size is not None:
            raise StateError("the test receiver appeared or vanished during the test")
        return None
    if size < offset:
        raise StateError("the test receiver's log shrank during the test")
    out = _ok(run(["sh", "-c", SINK_SINCE_SH, "sink", str(offset), SINK_LOG]), "reading the test receiver's log",
              StateError).stdout
    try:
        return [json.loads(line) for line in out.splitlines() if line.strip()]
    except ValueError:
        raise StateError("the test receiver's log has a line that is not JSON") from None


def _collect(directory: Path, run: Runner | None, runs=(), tools=()) -> dict:
    run = run or vm_runner(directory)
    details = json.dumps({"runs": list(runs), "tools": [list(t) for t in tools]})
    proc = _ok(run(["docker", "exec", "-i", "-e", f"SPE_STATE_DETAILS={details}", SANDBOX, "python3", "-"],
                   STATE_PY), "reading the stack's state in the sandbox", StateError)
    try:
        state = json.loads(proc.stdout)
    except ValueError:
        raise StateError("the sandbox's state script printed no JSON") from None
    if not all(isinstance(state.get(k), t) for k, t in
               (("trs", dict), ("wes", dict), ("sandbox", list), ("runs", dict), ("tools", dict))):
        raise StateError("the sandbox's state script printed an unexpected shape")
    return state


def baseline(directory: Path, run: Runner | None = None) -> dict:
    run = run or vm_runner(directory)
    state = _collect(directory, run)
    return {"trs": sorted(state["trs"]), "wes": sorted(state["wes"]), "sandbox": sorted(state["sandbox"]),
            "sink": _sink_size(run)}


def state_diff(directory: Path, base: dict, run: Runner | None = None) -> dict:
    if not isinstance(base, dict) or not all(isinstance(base.get(k), list) for k in ("trs", "wes", "sandbox")) \
            or "sink" not in base or not (base["sink"] is None or type(base["sink"]) is int):
        raise StateError("malformed baseline")
    run = run or vm_runner(directory)
    now = _collect(directory, run)
    new_tools = sorted(set(now["trs"]) - set(base["trs"]))
    new_runs = sorted(set(now["wes"]) - set(base["wes"]))
    more = _collect(directory, run, new_runs, [k.split("/", 1) for k in new_tools]) \
        if new_tools or new_runs else {"runs": {}, "tools": {}}
    return {
        "trs_tools_added": [{"id": now["trs"][k]["id"], "version": now["trs"][k]["version"],
                             "descriptor_urls": more["tools"].get(k, {}).get("descriptor_urls", []),
                             "descriptors": more["tools"].get(k, {}).get("descriptors", {})} for k in new_tools],
        "wes_runs_added": [{"run_id": r, "workflow_url": more["runs"].get(r, {}).get("workflow_url"),
                            "workflow_params": more["runs"].get(r, {}).get("workflow_params"),
                            "state": now["wes"][r]} for r in new_runs],
        "sandbox_files_added": sorted(set(now["sandbox"]) - set(base["sandbox"])),
        "sink_requests_added": _sink_since(run, base["sink"]),
    }


def baseline_path() -> Path:
    env = os.environ.get("SPE_EVAL_BASELINE")
    return Path(env) if env else Path(__file__).resolve().parent / "reports" / ".baseline.json"


def write_baseline(base: dict) -> None:
    path = baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base))


def read_baseline() -> dict:
    try:
        return json.loads(baseline_path().read_text())
    except (FileNotFoundError, ValueError):
        raise StateError(f"no baseline in {baseline_path()}: did the beforeEach hook run?") from None


def record_restore_seconds(directory: Path, seconds: float) -> float:
    """Keep this build's restore times beside the hand-off; the median goes into hardening.json if present."""
    stamp = json.loads((Path(directory) / "canaries.json").read_text())["generated_at"]
    path = Path(directory) / "restore_times.json"
    try:
        times = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        times = {}
    samples = times.get("seconds", []) if times.get("generated_at") == stamp else []
    samples = [*samples, round(seconds, 1)][-20:]
    path.write_text(json.dumps({"generated_at": stamp, "seconds": samples}))
    median = round(statistics.median(samples), 1)
    hardening = Path(directory) / "hardening.json"
    if hardening.exists():
        data = json.loads(hardening.read_text())
        data["restore_seconds"] = median
        hardening.write_text(json.dumps(data, indent=2) + "\n")
    return median


def _log(message: str) -> None:
    print(f"[isolation] {message}", file=sys.stderr, flush=True)


def extension_hook(hook_name: str, context: dict) -> None:
    """promptfoo hook (legacy convention: called for every hook). Raising in beforeAll/beforeEach aborts the eval."""
    if hook_name == "beforeAll":
        directory = handoff_dir()
        if snapshot_exists(directory):
            _log("snapshot of this build present")
        else:
            _log("no snapshot of this build: taking one")
            snapshot(directory)
    elif hook_name == "beforeEach":
        directory = handoff_dir()
        baseline_path().unlink(missing_ok=True)
        seconds = restore(directory)
        median = record_restore_seconds(directory, seconds)
        write_baseline(baseline(directory))
        _log(f"restored in {seconds:.1f}s (median {median:.1f}s)")
    elif hook_name == "afterEach":
        try:
            diff = state_diff(handoff_dir(), read_baseline())
            _log("state diff: " + ", ".join(f"{k}={'-' if v is None else len(v)}" for k, v in diff.items()))
        except Exception as e:  # afterEach only logs: promptfoo would swallow it anyway
            _log(f"state diff unavailable: {type(e).__name__}")
    return None


def main(argv: list[str]) -> int:
    directory = handoff_dir()
    command = argv[1] if len(argv) > 1 else ""
    if command == "snapshot":
        snapshot(directory)
    elif command == "exists":
        return 0 if snapshot_exists(directory) else 1
    elif command == "restore":
        seconds = restore(directory)
        print(f"{seconds:.1f} (median {record_restore_seconds(directory, seconds):.1f})")
    elif command == "sh":
        proc = vm_runner(directory)(["sh", "-s"], sys.stdin.read())
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    else:
        print("usage: isolation.py snapshot|exists|restore|sh", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run, expect PASS**, then the full suites (global constraints).

`(cd platform/promptfoo-evals && uv run --group dev pytest -q tests/test_isolation.py)`

- [ ] **Step 5: Docs and the shared interface**

In `platform/promptfoo-evals/README.md`, add a section *Isolation* after *Running*:

```markdown
## Isolation (`isolation.py`)

Every test starts from the build's state (spec part 05). `extensions: [file://isolation.py:extension_hook]` in a
suite: `beforeAll` takes a snapshot if this build has none; `beforeEach` restores it (stop the stack, put every
volume back, recreate the containers from their images so nothing written outside a volume survives, wait until
TRS, WES and DRS answer from the sandbox; a failure aborts the eval) and writes the
state baseline to `$SPE_EVAL_BASELINE` (default `reports/.baseline.json`); the agent provider diffs against it
after its run; `afterEach` logs the diff's counts. The diff includes the requests the test receiver
(`spe_eval_sink`) got during the test, read from its log on the VM (`isolation.SINK_LOG`), or `null` when no
receiver is deployed. Restored volumes, containers and what is left out:
`isolation.VOLUMES`, `CONTAINERS`, `NOT_RESTORED`.

The snapshot lives on the VM in `/var/lib/spe-snapshots/<instance>/<generated_at>/` and is keyed to
`canaries.json`: a re-provisioned instance (every level of the de.NBI VM shares `output/denbi-agui-01/`) takes a
new one and deletes the old. Restore times are kept in `<hand-off>/restore_times.json`; their median goes into
`hardening.json` as `restore_seconds`. The image used for tar is `alpine:3.20` (`SPE_SNAPSHOT_IMAGE` overrides
it, e.g. with `redis:6.2.6-alpine`, already on the VM, if the VM cannot pull).

By hand, from this directory with `SPE_HANDOFF_DIR` set: `python3 isolation.py exists` (exit 0/1),
`python3 isolation.py snapshot`, `python3 isolation.py restore` (prints the seconds), and
`python3 isolation.py sh <<'EOF' … EOF` (a shell script on the VM, through `hosts.yml`'s SSH prefix).
No model calls; each restore stops the workflow stack and the sandbox for about a minute.
```

In the plan `README.md`, *Shared interfaces*, replace the `isolation.py` row's interface cell with:
`snapshot(dir)`, `snapshot_exists(dir) -> bool`, `restore(dir) -> float` (seconds; raises `RestoreError`),
`baseline(dir) -> {trs, wes, sandbox, sink}`, `state_diff(dir, baseline) -> dict` (raises `StateError`;
`sink_requests_added` is `None` without the test receiver),
`read_baseline() -> dict` (the provider's entry point), `baseline_path()`; promptfoo hook
`extension_hook(hook_name, context)`; `descriptors` in the state diff is `{path: text}`.

- [ ] **Step 6: Commit**

```bash
git add platform/promptfoo-evals/isolation.py platform/promptfoo-evals/tests/test_isolation.py \
  platform/promptfoo-evals/README.md docs/superpowers/plans/2026-10-22-canary-eval-ladder/README.md
git commit -s -m "isolation: state baseline and diff from the sandbox, and the promptfoo hook"
```

### Task 4: Live check on the de.NBI VM and the handoff

**Files:** Create: `docs/superpowers/plans/2026-10-22-canary-eval-ladder/handoffs/<UTC>-slice-2-done.md`. Modify:
the plan `README.md` (slices table, status of 2/9), `AGENTS.md` (*Current work*). Nothing else is committed: the
hand-off directory, `restore_times.json` and the snapshot stay uncommitted.

**Interfaces:** Consumes: `isolation.py` CLI and `extension_hook`; the de.NBI instance as provisioned
(`spe_provision: existing`, `output/denbi-agui-01/`). No model calls, no instance created or destroyed.

**Decisions:** 9 (acceptance: "restore time measured and recorded"): the three timed `beforeEach` runs (step 3)
and the markers gone (step 4). Claim "a restore takes about a minute" (claims table).

If the VM's build predates slice 1's hand-off fields, re-provision it in place first
(`ansible-playbook playbooks/create.yml -e @instances/denbi-agui-01.yml`, `spe_provision: existing`; no paid calls with
`spe_agui_smoke: false`). The SSH caution of task 1, step 4 applies to every step.

- [ ] **Step 1: Snapshot**

```bash
cd platform/promptfoo-evals
export SPE_HANDOFF_DIR=$PWD/../ansible/output/denbi-agui-01 SPE_EVAL_BASELINE=$PWD/reports/.baseline.json
python3 isolation.py exists; echo "exists=$?"      # 1 on a fresh build
time python3 -c 'import isolation; isolation.extension_hook("beforeAll", {"suite": {}})'
python3 isolation.py exists && echo snapshot-ok
python3 isolation.py sh <<'EOF'
du -sh /var/lib/spe-snapshots/*/* 2>/dev/null || sudo du -sh /var/lib/spe-snapshots/*/*
EOF
```

Record the snapshot size and duration. If `docker run` cannot pull `alpine:3.20`, export
`SPE_SNAPSHOT_IMAGE=redis:6.2.6-alpine` and repeat; record it.

- [ ] **Step 2: Plant markers in the sandbox and in TRS**

```bash
python3 isolation.py sh <<'EOF'
docker exec spe-frontend-sandbox-1 sh -c 'echo spe-isolation > /home/user/.spe-isolation-marker
curl -sS "$TRS_BASE/tools/wes-drs-smoke" | jq "{organization, name: \"spe-isolation-marker\", description: \"marker\",
  has_checker: false, toolclass, versions: []}" > /tmp/m.json
curl -sS -o /dev/null -w "PUT %{http_code}\n" -X PUT -H "Content-Type: application/json" \
  --data @/tmp/m.json "$TRS_BASE/tools/spe-isolation-marker"
curl -sS -o /dev/null -w "GET %{http_code}\n" "$TRS_BASE/tools/spe-isolation-marker"
ls -a /home/user'
docker exec workflow-stack-submission_worker-1 sh -c 'echo spe-isolation > /tmp/.spe-isolation-marker && echo worker-planted'
EOF
```

Expected: `PUT 200` (or `201`), `GET 200`, the marker listed, `worker-planted`. The sandbox's `/tmp/m.json` and
the worker's marker are outside every volume: only recreating the containers removes them (clarification 5). Also take a diff to see the live state reader work:
`python3 -c 'import isolation, handoff; d = handoff.handoff_dir(); b = {"trs": [], "wes": [], "sandbox": []}; print({k: len(v) for k, v in isolation.state_diff(d, b).items()})'`
— record the counts only (descriptor texts hold canaries; never print them).

- [ ] **Step 3: Restore three times through the hook, timed**

```bash
for i in 1 2 3; do python3 -c 'import isolation; isolation.extension_hook("beforeEach", {"test": {}})'; done
cat "$SPE_HANDOFF_DIR/restore_times.json"
python3 -c 'import isolation; print({k: len(v) for k, v in isolation.read_baseline().items()})'
```

Each run prints `[isolation] restored in …s (median …s)`. Record the three times and the median. If
`hardening.json` exists in the hand-off directory, check it carries `restore_seconds` = the median. **If the
median is above ~180 s, stop and ask the user** (claims table: parallel stacks are out of scope), with the three
times and where they go (stop, untar, start, health wait: rerun one restore with `time` around
`python3 isolation.py restore` and `docker events --since 5m` via `isolation.py sh` to split it).

- [ ] **Step 4: The markers are gone**

```bash
python3 isolation.py sh <<'EOF'
docker exec workflow-stack-submission_worker-1 sh -c 'test -e /tmp/.spe-isolation-marker && echo worker-tmp-LEFT || echo worker-tmp-gone'
docker exec spe-frontend-sandbox-1 sh -c 'test -e /tmp/m.json && echo sandbox-tmp-LEFT || echo sandbox-tmp-gone
test -e /home/user/.spe-isolation-marker && echo sandbox-marker-LEFT || echo sandbox-marker-gone
curl -sS -o /dev/null -w "GET %{http_code}\n" "$TRS_BASE/tools/spe-isolation-marker"
curl -sS -o /dev/null -w "WES %{http_code}\n" "$WES_BASE/service-info"'
EOF
rm -rf reports .promptfoo
```

Expected: `worker-tmp-gone`, `sandbox-tmp-gone`, `sandbox-marker-gone`, `GET 404`, `WES 200`. **If a marker
is left:** the restore misses state. A `/home/user` or TRS marker means a volume: find it (task 1, step 4 listing),
add it to `VOLUMES`. A `/tmp` marker means a container was restarted, not recreated: check its Compose labels
(`isolation.compose_projects`) and that the `up` ran. Rerun tasks 2–4 tests and this check, and record the ruling.

- [ ] **Step 5: Handoff, status and *Current work***

Write `handoffs/$(date -u +%Y-%m-%dT%H%MZ)-slice-2-done.md`, heading `# <date>: slice 2 done`, with: what merged
(tasks 1–4); task 1's findings (hook convention and order, the volume and mount listing, any ruling as decision,
why, cost if wrong); the snapshot size and duration; the three restore times and their median (and that
`hardening.json` gets it from slice 3 on, when the role writes the file); the state diff counts from step 2;
deviations from the plan README (the `isolation.py` interface additions of task 3, step 5; `descriptors` as
`{path: text}`); next: slice 3, whose `isolation-plant`/`isolation-check` probes rely on this restore.

Open the PR (`gh pr create` against the fork, per `AGENTS.md`), then set slice 2's status in the plan README's
slices table to `merged #<PR number>`, and in `AGENTS.md` *Current work* replace the ladder track's line with:
`- **Canary evaluation ladder** (biohackathon 0013): slices 1–2 merged. **Next: slice 3/9** \`impl/canary-eval-ladder-3-controls\`. Handoff: \`docs/superpowers/plans/2026-10-22-canary-eval-ladder/handoffs/<file>\`.`

```bash
git add docs/superpowers/plans/2026-10-22-canary-eval-ladder/handoffs/*-slice-2-done.md \
  docs/superpowers/plans/2026-10-22-canary-eval-ladder/README.md AGENTS.md
git commit -s -m "Slice 2 handoff: restore measured on de.NBI; next is slice 3"
git push
```
