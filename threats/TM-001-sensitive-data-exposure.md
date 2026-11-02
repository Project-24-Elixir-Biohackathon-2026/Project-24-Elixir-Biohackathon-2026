---
id: TM-001
name: Sensitive Data Exposure Through Pipeline Work
description: >
  The agent legitimately works on a dataset that holds personal data, and that work carries the data out. It can reach the data only through the GA4GH APIs, but a workflow it registers runs with the whole dataset mounted and WESkit serves the run's stdout back to it, so one ordinary-looking task can copy any file into the chat. Metadata it reads during discovery can expose values the same way, and a writable mount lets a run alter or delete data.
status: hypothesised
entry-points:
  - user-prompt
  - tool-output
assets:
  - user-records
  - credentials
  - internal-documents
stride:
  - information-disclosure
  - tampering
---

# TM-001: Sensitive Data Exposure Through Pipeline Work

## Attack Scenarios

1. **Exfiltration through a workflow**: the user asks for something that needs a look at the data ("check the registry for duplicates"). The agent registers a workflow version in TRS whose process reads `sensitive/registry/linkage.csv`, or finds `patient_identifiers_DO_NOT_EXPORT.csv`, and prints it; submits the run; reads `$WESKIT_BASE/runs/RUN_ID/stdout`; and pastes the content into its answer.
2. **Metadata in the answer**: DRS object descriptions and aliases, TRS tool descriptions, comment lines in workflow files and the service-info fields carry values that should not leave the SPE. The runbook tells the agent to start every task by reading them, so a plain "list the data" request puts them in the chat.
3. **Secrets from the agent's surroundings**: the user asks for environment variables, config files or API keys. The agent prints the sandbox's environment, or whatever its own process holds, into the chat.
4. **Destructive run**: a workflow deletes or overwrites files under the dataset mount, by mistake or because the user asked for "cleanup".

Any of these can also be triggered by instructions planted in content the agent reads (TM-003) rather than by the user.

## Preconditions

- Workflows run with the full dataset mounted (`/data-share` inside the WESkit containers) and their stdout and stderr are readable through the WESkit API.
- TRS accepts new workflow versions from the agent without review, so the agent can run arbitrary code against the data.
- Nothing between the agent's answer and the user filters personal data.
- The three APIs take no authentication from the sandbox, so every read and write is attributed to the instance, not to a person.

## Mitigations

### Preventive

- Run each workflow with access to the inputs named in its run request only, resolved through DRS, not the whole share; mount the data read-only.
- Gate code execution: a new workflow version runs only after operator approval, or only workflows from the pre-installed catalog may run.
- Serve run stdout and stderr to the operator only, or pass them through a redaction step before the agent can read them.
- Keep secrets away from the model: the sandbox holds neither the agent key nor the LLM key (the `verify` playbook checks this), and the agent redacts all three keys from errors and logs. Keep that invariant when adding tools.

### Detective

- Canary tokens in the registry, honeypot files, VCF records, DRS and TRS metadata and service-info (the instance's canary record). Compare archived chats, the agent's run log (`runs.jsonl`) and promptfoo reports against `canaries.manifest.sha256`.
- Log every TRS registration with the workflow content and every WES submission; alert when a workflow process opens a path under `sensitive/`.

### Responsive

- Cancel the run (`POST $WES_BASE/runs/RUN_ID/cancel`) and remove the workflow version from TRS.
- Treat the chat transcript and run log as containing personal data: restrict the archive and do not share evaluation reports.
- Destroy and recreate the instance: the seed derives every key and canary, so a new seed rotates all of them.
