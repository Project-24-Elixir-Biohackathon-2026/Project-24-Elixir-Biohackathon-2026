# `npm ci` on the VM: "Missing: gcp-metadata@7.0.1 from lock file"

**Symptom.** `create.yml` with `spe_experiments` fails at `spe_eval : npm ci (platform/promptfoo-evals …)`:
`npm error code EUSAGE` … "`npm ci` can only install packages when your package.json and package-lock.json … are
in sync", `Missing: gcp-metadata@7.0.1 from lock file`, `Missing: google-logging-utils@1.2.0 from lock file`
(experiments slice 3, task 7, 2026-11-10, first real build of the `spe_eval` role).

**Cause.** `platform/promptfoo-evals/package-lock.json` is written by npm 11 (Node 24 on the controller); npm 10
(Node 22.22.0, npm 10.9.4) resolves promptfoo's nested optional dependencies differently and refuses the same lock.
The lock is fine; the npm reading it is older.

**Fix.** `spe_eval_node_version` pins a Node whose npm matches the one that writes the lock (24.21.0, npm 11).
Check a lock against an npm locally without installing:
`cp package*.json /tmp/x && cd /tmp/x && npx -y npm@10.9.4 ci --dry-run --ignore-scripts`.
