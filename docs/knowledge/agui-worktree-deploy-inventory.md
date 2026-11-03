# Deploying a worktree: `group_vars` still come from the main checkout

**Symptom.** `create.yml` run from the main checkout with `-e spe_agui_source_dir=<worktree>/platform/agui`
deploys the worktree's agent and chat UI, but a variable the worktree adds or changes in
`platform/ansible/inventory/group_vars/all.yml` does not apply: `verify.yml` showed
`"context_window_tokens": null` where the branch derives 262144 (compaction slice 3, 2026-11-03).

**Why.** `spe_agui_source_dir` only points the image builds at the worktree. Inventory `group_vars` load from the
inventory in use, `ansible.cfg`'s `inventory/hosts.yml` of the main checkout.

**Fix.** Pass the worktree's inventory, after checking it differs from main's only by the branch's change
(`diff -r MAIN/platform/ansible/inventory <worktree>/platform/ansible/inventory`):

```bash
cd MAIN/platform/ansible
ansible-playbook -i <worktree>/platform/ansible/inventory/hosts.yml playbooks/create.yml \
  -e @instances/NAME.yml -e spe_agui_source_dir=<worktree>/platform/agui </dev/null
```

Use the same `-i` for `verify.yml`. The private instance file and `output/` stay the main checkout's.
