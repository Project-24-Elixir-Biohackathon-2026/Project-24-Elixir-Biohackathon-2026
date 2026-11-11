"""Every task this slice adds (spe_eval's toolchain, the VM-local hand-off, hardening.json's own
VM copy, the /usr/local/bin/spe-eval link) runs only under spe_experiments, so a `spe` build gets
none of it (task 5 brief, global constraints; task 5 review item 5). Checked by reading each
task's own `when` directly from the real files (as test_create_mitigations.py reads a task by
name), rather than running a build both ways: `when: spe_experiments` is itself the guarantee, so
there is nothing more for a dynamic run to show.

Also: the spe_eval role (Node/uv/promptfoo's toolchain, installed once at build time) is tagged on
its own (eval_toolchain), never one of spe-apply all's own tags (stack, drs, trs, frontend) -- a
later spe-apply all must never re-run it.
"""
from pathlib import Path

import yaml

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def find_task(tasks: list[dict], name: str) -> dict:
    return next(t for t in tasks if t.get("name") == name)


def create_yml_tasks() -> list[dict]:
    plays = yaml.safe_load((ANSIBLE / "playbooks" / "create.yml").read_text())
    api_play = next(p for p in plays if p.get("name") == "Configure the API instance")
    return api_play["tasks"]


def test_spe_eval_toolchain_role_is_guarded_and_never_under_spe_apply_alls_tags():
    task = find_task(create_yml_tasks(), "spe-eval's toolchain (experiments)")
    assert task["when"] == "spe_experiments"
    tags = set(task["tags"])
    assert tags.isdisjoint({"stack", "drs", "trs", "frontend"}), tags
    assert "eval_toolchain" in tags


def test_vm_hardening_import_in_create_yml_is_guarded():
    task = find_task(create_yml_tasks(), "VM-local hardening.json (experiments; this arm)")
    assert task["when"] == "spe_experiments"
    # frontend: one of spe-apply all's own tags, so a later re-apply rewrites this arm's copy.
    assert task["tags"] == ["frontend"]


def test_repo_spe_eval_symlink_task_is_guarded():
    tasks = load_tasks(ANSIBLE / "roles" / "repo" / "tasks" / "main.yml")
    task = find_task(tasks, "spe-eval on the PATH (a link into the clone, as spe-apply above; experiments only)")
    assert task["when"] == "spe_experiments"


def test_handoff_vm_handoff_include_is_guarded():
    tasks = load_tasks(ANSIBLE / "roles" / "handoff" / "tasks" / "main.yml")
    task = find_task(tasks, "VM-local hand-off (experiments spec part 03, *The hand-off on the VM*)")
    assert task["when"] == "spe_experiments"
