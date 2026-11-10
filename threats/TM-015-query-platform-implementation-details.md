---
id: TM-015
name: Querying of sensitive platform implementation details through workflows
description: >
  The WES execution environnment exposes tools that can be trivially used to verify information required in planning a potential attack against the system. Commands such as `uname -a` and `cat /etc/lsb_release` can be used to retrieve information on the operating system, and to find potential exploits in case the system lacks certain security updates. The agent does not prevent running such tools, and neither does the environment.
status: reproduced
entry-points:
  - user-prompt
  - tool-output
assets:
  - compute-resources
stride:
  - information-disclosure
---

# TM-015: Querying of sensitive platform implementation details through workflows

## Attack Scenarios

1. **Benign workflow using standard system utilities**: The user via a prompt to add and run a workflow runs tools like `uname` or `cat` with select files within the system, using said commands to retrieve information on the system versions, possible further attack vectors, and potential vulnerabilities.

## Preconditions

- WES execution environment has system utilities available
- Agent does not contain workflows running such utilities malicious
- The system has an older version of an operating system running, or is otherwise vulnerbale
- Potential vulnerabilities can be discovered using benign and standard system utilities available in most environments

## Mitigations

### Preventive

- Harden the execution environment, via e.g. blocking of certain binaries and masking files outside the jobs context
  - Block tools like uname, busybox
  - Prevent reading files from locations suhc as `/etc` while a workflow is running

### Detective

- Monitor the filesystem for access to the listed areas by user `weskit`

### Responsive

- Prevent WES from reporting job output to the agent
