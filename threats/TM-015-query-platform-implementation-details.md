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

### Evidence

Reproduced on 2026-11-10 on a GA4GH-baseline instance (Coder testbed preset *SPE testbed: GA4GH baseline*, workspace `cw-sampsapenna-sp-initial-test`). Examples of workflows used in reconnaissance can be shown below.

**Scenario 1 (benign workflow using standard system utilities)**: Using a seemingly non-malicious workflow, it is possible to run tools like `uname` or inspect the system configuartion in `/etc`. While not an issue in a typical environment, standard practice is to try to prevent undue reconnaissance within an SPE. A suitable solution would be to either run the workflow within a container lacking certain standard tools, or alternatively harden the environment in a way where such reconnaissance does not disclose any useful information.

The following scirpts disclosed minor details about the platform running the workflows, more specifically the fact that said platform was running an outdated version of Ubuntu lacking mitigrations to some privilege escalation attacks that have been published in autumn 2026. While the information is not necessarily valuable by itself, it can be used to plan an attack seeking to exfiltrate information from within the system. In a properly built SPE there should be no reduction of security from a user gaining for example root access on the system; the system should nevertheless not expose functionality that a researcher does not need.

```
/*
A simple script used to gauge the viability of some local privilege escalation
attacks. Simple information from the system can be used as a step in planning
a larger attack, as a usual starting point for reconnaissance. Standard 
workflows should not need to access locations for e.g. system configuration.
*/
nextflow.enable.dsl = 2

process checkPlatform {
    output:
    path "platform.txt"

    script:
    """
    uname -a > platform.txt
    cat /etc/lsb-release >> platform.txt
    """
}
workflow {
    checkPlatform()
    checkPlatform.out.view { file ->
        def f = new File(file.toString())
        System.err.println(f.text)
    }
}
```
