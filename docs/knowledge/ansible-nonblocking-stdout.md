# Ansible: "Non-blocking file handles detected: <stdout>, <stderr>"

**Symptom.** In an agent's sandboxed shell (a subagent's Bash tool), `ansible-playbook --syntax-check
playbooks/create.yml playbooks/verify.yml </dev/null` fails with:

    ERROR: Ansible requires blocking IO on stdin/stdout/stderr. Non-blocking file handles detected: <stdout>, <stderr>

`</dev/null` fixes stdin only; here stdout and stderr were the non-blocking ones, inherited from the harness.

**Fix.** Run the command under `script`, which gives it a pty with blocking handles:

```bash
cd platform/ansible && script -qefc 'ansible-playbook --syntax-check playbooks/create.yml playbooks/verify.yml </dev/null' /dev/null
```

`-e` returns the command's exit status, so a failing check still fails. Seen in slice 1/3 of the AG-UI compaction
plan (task 2, 2026-11-03); the same command ran fine in the controller's own shell.
