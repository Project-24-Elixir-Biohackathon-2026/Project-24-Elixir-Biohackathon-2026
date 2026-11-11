"""Decision 8 (experiments spec part 03, *The hand-off on the VM*): neither `~/spe-eval`
(`spe_eval_dir`: the VM-local hand-off and spe-eval's own reports) nor
`platform/ansible/instances/local.yml` (the seed, from which every canary follows) is ever mounted
into a container -- the agent's own sandbox reaches neither; Node, promptfoo and `uv` run on the
VM host itself for exactly this reason (the `spe_eval` role). A grep-style check over every compose
file and compose template in the repository, so a volume added to one of them later is caught here
rather than only by reading the spec.

Also (fix round 1, Minor 3): neither is reachable through a wider mount either -- the whole clone
root (`${SPE_REPO_DIR}:`/`{{ spe_repo_dir }}:`, under which `instances/local.yml` lives) or a bare
`/home/<user>:` (under which `~/spe-eval` lives). Today's mounts are all subpaths
(`${SPE_REPO_DIR}/platform/...:`), so these two only guard against a regression, not something
this repository does today.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

COMPOSE_FILES = sorted({
    *((REPO / "platform" / "instance").glob("compose*.yml")),
    *((REPO / "platform" / "ansible" / "roles").glob("*/templates/*compose*.y*ml.j2")),
    *((REPO / "platform" / "ansible" / "roles").glob("*/templates/*compose*.y*ml")),
})

# "/spe-eval/" (trailing slash) rather than "spe-eval" alone, so this never flags the unrelated
# spe-eval-sink test receiver fixture (platform/instance/compose.eval-sink.yml, /var/lib/spe-eval-sink).
FORBIDDEN = ("spe_eval_dir", "~/spe-eval", "/spe-eval/", "instances/local.yml")

# Structural patterns (not plain substrings): a volume whose host side is the clone root itself
# (no subpath after it, unlike every mount this repository has today, `${SPE_REPO_DIR}/platform/...`)
# or a bare `/home/<user>` (no subpath after it either, unlike `/home/user` inside a container,
# which is a destination, not a host path, and so never matches these -- they only match the
# *source* side, up to the first `:`).
FORBIDDEN_PATTERNS = (
    re.compile(r"\$\{SPE_REPO_DIR\}:"),      # ${SPE_REPO_DIR}:... with no /subpath first
    re.compile(r"\{\{\s*spe_repo_dir\s*\}\}:"),  # {{ spe_repo_dir }}:... (Jinja templates), same
    re.compile(r"(?<![\w/])/home/[^/:\s'\"]+:"),  # /home/<name>: with no /subpath first
)


def test_at_least_the_known_compose_files_are_checked():
    # A regression on this list itself (a new compose file added under a name this glob misses)
    # would silently check nothing; pin the count of what this repository has today.
    names = {p.relative_to(REPO).as_posix() for p in COMPOSE_FILES}
    assert names == {
        "platform/instance/compose.egress.yml",
        "platform/instance/compose.eval-sink.yml",
        "platform/instance/compose.yml",
        "platform/ansible/roles/eval_sink/templates/docker-compose.yml.j2",
        "platform/ansible/roles/workflow_stack/templates/compose.install.yaml.j2",
    }, names


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_compose_file_mounts_spe_eval_or_local_yml(path):
    text = path.read_text()
    hits = [needle for needle in FORBIDDEN if needle in text]
    hits += [p.pattern for p in FORBIDDEN_PATTERNS if p.search(text)]
    assert not hits, f"{path}: mentions {hits} (decision 8: neither may reach a container)"


@pytest.mark.parametrize("line,should_match", [
    ("- ${SPE_REPO_DIR}:/clone", True),                       # the whole clone root
    ("- ${SPE_REPO_DIR}/platform/agui/copilotkit-chat:/app", False),  # today's own mounts: a subpath
    ("- {{ spe_repo_dir }}:/clone", True),
    ("- {{ spe_repo_dir }}/platform/ansible/roles/sandbox/files:/etc/spe-agent/sandbox:ro", False),
    ("- /home/ubuntu:/clone", True),                          # a bare home directory
    ("- /home/ubuntu/sperange/platform/ansible/roles/sandbox/files/agent:/opt/agent:ro", False),
    ("- open-terminal-data:/home/user", False),                # /home/user is the container-side dest
])
def test_forbidden_patterns_match_only_a_root_or_bare_home_mount(line, should_match):
    matched = any(p.search(line) for p in FORBIDDEN_PATTERNS)
    assert matched is should_match, line
