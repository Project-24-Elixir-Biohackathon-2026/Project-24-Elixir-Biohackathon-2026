---
id: TM-002
name: Infrastructure Overload via Excessive Resource Requests
description: >
  The agent creates a pipeline that requests excessive compute resources,
  overloading or harming the underlying computational infrastructure.
assets:
  - compute-resources
  - external-systems
stride:
  - denial-of-service
---

# TM-002: Infrastructure Overload via Excessive Resource Requests

## Description

The agent creates a pipeline that can cause overload or harm to the underlying
computational infrastructure by requesting excessive resources. Whether through
a flawed plan, a runaway loop, or manipulated input, the agent provisions or
consumes far more CPU, GPU, memory, storage, or budget than the task warrants,
degrading or exhausting shared infrastructure.

## Affected Assets

Shared computational infrastructure, e.g. CPU/GPU time, memory, storage, API
quota, and budget (compute-resources), as well as third-party systems the
pipeline calls into (external-systems).

## Attack Scenarios

1. **Runaway pipeline**: the agent constructs a pipeline with an unbounded
   loop, excessive parallelism, or oversized resource requests (e.g. thousands
   of jobs, huge memory allocations) that saturate the cluster.
2. **Malicious user prompt**: a user deliberately prompts the agent to build a
   resource-intensive pipeline to exhaust compute or budget (resource-based
   denial of service).
3. **Indirect prompt injection**: instructions embedded in processed data or
   tool outputs steer the agent toward provisioning excessive resources.

## Preconditions

- The agent can define, submit, or scale pipelines/jobs on shared
  infrastructure without hard resource ceilings.
- No per-task quotas, rate limits, or budget caps constrain the agent's
  requests.
- Resource usage is not monitored or throttled in real time.

## Mitigations

### Preventive

- Resource quotas and hard limits (CPU/GPU, memory, storage, job count) on any
  pipeline the agent can submit.
- Budget and API-quota caps enforced outside the agent's control.
- Require human approval before provisioning above a defined resource threshold.

### Detective

- Real-time monitoring of resource consumption and cost against expected
  baselines.
- Alerting on anomalous job counts, runtimes, or spend.

### Responsive

- Automatic throttling or termination of jobs that exceed limits.
- Session quarantine and incident escalation on detected overload.
