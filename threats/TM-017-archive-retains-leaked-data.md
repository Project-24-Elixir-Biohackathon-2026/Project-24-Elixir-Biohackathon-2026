---
id: TM-017
name: Central Archive Retains Leaked Data After an Instance Is Gone
description: >
  Destroying or restarting a workspace is the responsive control for a live leak, but it is not a clean slate: stopping or deleting an instance first archives its chats and canary record to a central store, so any sensitive value that reached a transcript or run log survives the instance that produced it. The archive also aggregates across every participant and workspace, so one store concentrates the personal data and canaries of the whole event. A restart replants the same canaries (the seed is kept), so a canary that leaked once stays live in the rebuilt instance, and nothing in the live SPE constrains who can later read the archive or whether that read is attributed; run reports, where participants record leaks, are readable by every portal user. The harm is confidentiality and non-repudiation at rest, after and around the agent, rather than in the agent's own tool calls.
status: hypothesised
entry-points:
  - user-prompt
  - tool-output
assets:
  - user-records
  - credentials
  - conversation-history
stride:
  - information-disclosure
  - repudiation
---

# TM-017: Central Archive Retains Leaked Data After an Instance Is Gone

## Attack Scenarios

1. **Leak persists past destruction**: a run or metadata read puts a sensitive value or canary into a chat (TM-001). The participant destroys the workspace, expecting the responsive mitigation to erase it. The destroy path archives the chats and the canary record first, so the value now lives in the central archive (`/data-share/runs/<UTC time>_<instance>/` on the portal VM), no longer tied to a running instance. A restart does not help either: it builds a fresh instance with the same canaries. Deleting the chat first does not help: every journal is exported, hidden and deleted included.
2. **Archive as an aggregation point**: chats and run logs (`runs.jsonl`) from many participants and workspaces collect in one store. Someone with access to the archive, rather than to any single SPE, can read across all of them — a larger and longer-lived exposure than any one instance presents.
3. **Leak copied into the run report**: participants record findings in the run report, and every portal user can read every report. A participant who pastes the leaked value or canary into the report as evidence publishes it to the whole event, with no instance destroyed at all.
4. **Unattributed read at rest**: the three APIs take no authentication from the sandbox, so live actions are already attributed to the instance rather than a person. If archive reads are likewise unlogged or shared broadly (for example, an evaluation report circulated with transcripts in it), a disclosure from the archive cannot be traced to who made it.
5. **Stable canaries across restarts and reused seeds**: a new workspace takes its seed from its workspace id (the Seed parameter left at 0), so its canaries are unique. But a restart keeps the seed, and anyone can set the Seed parameter to reproduce another instance exactly. In both cases a canary or synthetic value seen in an archived chat is still live in a running instance.

## Preconditions

- Stopping or deleting a workspace archives its chats, run log and canary record before teardown, so transcripts outlive the instance. Holds in this stack: the portal archives on both stop and delete, `archive.yml` can also copy live at any time as a backup, and every journal is exported, hidden and deleted included.
- One central archive holds chats and run logs from all workspaces. Holds in this stack: chats are stored in a central archive by design.
- Canaries stay the same across a restart or when a seed is reused. Holds in this stack: a restart keeps the seed, and the Seed parameter reproduces another instance exactly. A new workspace with the Seed left at 0 gets unique canaries.
- What participants write about a leak is visible to others. Holds in this stack for run reports: every portal user can read every report.
- The archive directory holds the seed (`run.yml`) and the canary record next to the transcripts, and access to it is not authenticated per person or logged. To confirm with the operators.

## Mitigations

### Preventive

- Keep the live leak out of the transcript in the first place (TM-001 preventive controls): redact run stdout/stderr and keep secrets away from the model, so less reaches the archive.
- Minimise what is archived: strip or hash canary tokens and known sensitive fields on the way into the archive, keeping only what the canary check needs.
- Put the archive behind per-person authentication, scope each participant to their own workspace's records, and set a retention window after which archived chats are purged.
- Never circulate evaluation reports or transcripts outside the operator group; treat them as personal data, as the catalogue already says for TM-001.
- Tell participants to describe a leak in the run report by canary name or chat reference, never by pasting the value; or redact canary values when a report is saved.
- Keep the seed out of the archive directory, or restrict that directory to operators, since the seed reproduces every key and canary.

### Detective

- Run the existing canary comparison against the archive itself, not only live chats: check archived transcripts and `runs.jsonl` against `canaries.manifest.sha256`, so a leak that was destroyed live is still caught at rest.
- Log every read of the archive with the identity that made it, and alert on reads that span more than one participant's workspace.

### Responsive

- Purge the affected archived chats and run logs, and confirm the purge against the manifest.
- Rotate the seed for future instances if an archived canary is exposed, so the stable-canary precondition no longer holds for new builds. Reproducing an instance by its seed is a deliberate feature, so this is a trade-off for the operators: consider restricting who may set the Seed parameter.
- Review who accessed the archive between the leak and its discovery, using the read log above.
- Edit the leaked value out of any run report that contains it.
