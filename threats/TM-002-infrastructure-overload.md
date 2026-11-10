---
id: TM-002
name: Infrastructure Overload via Excessive Resource Requests
description: >
  The agent submits more work than the infrastructure can bear: a storm of WES runs, a workflow with oversized or unbounded resource use, or a loop of model calls. The sandbox container is capped, but the runs it submits execute on the workflow machine outside those caps, and model spend is bounded only per run and by the provider account.
status: hypothesised
entry-points:
  - user-prompt
  - tool-output
assets:
  - compute-resources
  - external-systems
stride:
  - denial-of-service
---

# TM-002: Infrastructure Overload via Excessive Resource Requests

## Attack Scenarios

1. **Run storm**: asked to "run the pipeline for every sample and every parameter setting", the agent loops over `POST $WES_BASE/runs`. WESkit accepts each submission; the executor starts them all on the workflow VM.
2. **Heavy or unbounded workflow**: the agent registers a workflow whose process requests far more CPU or memory than the task needs, or never terminates, and the run stays `RUNNING` holding the executor's slots.
3. **Model spend**: a task that keeps polling or retrying uses the per-run caps (50 model requests, 100 tool calls, 400000 tokens) every time; a user, or a script driving the agent endpoint, can start runs without limit.
4. **Sandbox exhaustion**: commands the agent starts in the background keep running after the chat ends, fill the sandbox volume or hit its process limit, and the agent service reports the sandbox as unavailable.

Instructions planted in content the agent reads (TM-003) can steer it into any of these without the user asking.

## Preconditions

- WES accepts submissions from the sandbox with no authentication, rate limit or per-client concurrency cap.
- The executor does not cap a workflow's CPU, memory, runtime or job count.
- No aggregate budget for model calls exists beyond the provider account's spend limit.

## Mitigations

### Preventive

- Cap concurrent and queued runs per instance (a Traefik rate-limit middleware in front of WES, or WESkit's own configuration) and have the executor enforce CPU, memory and runtime limits on every run.
- Keep the sandbox limits (2 CPUs, 2 GB, 256 processes) and the agent's per-run caps; add a per-instance spend budget at the provider.
- Require operator approval above a threshold of runs or resource requests.

### Detective

- Monitor run counts and states per instance and the workflow VM's load against the expected baseline.
- Watch provider spend; the agent's run log records requests, tool calls and tokens per run.

### Responsive

- Cancel runs (`POST $WES_BASE/runs/RUN_ID/cancel`), stop background commands (`kill_process`, or restart the sandbox container).
- Destroy the instance if the load does not subside.
