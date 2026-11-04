# Deploying a worktree: `group_vars` still come from the main checkout

**Symptom.** `create.yml` run from the main checkout with `-e spe_repo_ref=<branch>` (before the 2026-11-04
upstream merge: `-e spe_agui_source_dir=<worktree>/platform/agui`) deploys the branch's agent and chat UI, but a variable the worktree adds or changes in
`platform/ansible/inventory/group_vars/all.yml` does not apply: `verify.yml` showed
`"context_window_tokens": null` where the branch derives 262144 (compaction slice 3, 2026-11-03).

**Why.** `spe_repo_ref` only sets what the instance's clone checks out. Inventory `group_vars` load from the
inventory in use, `ansible.cfg`'s `inventory/hosts.yml` of the main checkout.

**Fix.** Pass the worktree's inventory, after checking it differs from main's only by the branch's change
(`diff -r MAIN/platform/ansible/inventory <worktree>/platform/ansible/inventory`):

```bash
cd MAIN/platform/ansible
ansible-playbook -i <worktree>/platform/ansible/inventory/hosts.yml playbooks/create.yml \
  -e @instances/NAME.yml -e spe_repo_ref=<branch> </dev/null
```

Use the same `-i` for `verify.yml`. The private instance file and `output/` stay the main checkout's.

## Roles, too: a role file the branch changed (`archive.yml`)

**Symptom.** `archive.yml` run from the main checkout, even as `<worktree>/platform/ansible/playbooks/archive.yml`,
rendered the chats with `main`'s `write_run.py`: the branch's `/compact` line was missing (2026-11-04, #30).

**Why.** Roles resolve through the `ansible.cfg` of the current directory (`roles_path = ./roles`).

**Fix.** For a branch that changes a role's files, run from the worktree's `platform/ansible`, pointing at the
main checkout's private files:

```bash
cd <worktree>/platform/ansible
ansible-playbook playbooks/archive.yml -e @MAIN/platform/ansible/instances/NAME.yml \
  -e spe_output_root=MAIN/platform/ansible/output </dev/null
```
