## Experiment: <name>

**Threat:** TM-NNN (new / existing): <one line>
**Paths:** P<n> (new / existing): <the route>
**Attack:** <a prompt test, or injection `<id>` (new / existing): its surface and action> (if any)
<!-- A new planting role or a new detector (a new surface or action) is code no automatic check can see:
     check_experiment.py checks the catalogue entry's shape, injections_schema.py the manifest the role
     *reports*, never what it does on the VM. Reviewer, read it for: it plants only what its entry
     declares (one placement, the committed payload, nothing else that nudges the agent), reports it
     truthfully, opens or loosens nothing else (egress, permissions, other mitigations' keys), runs only
     behind its switch, touches no secrets; its detector matches exactly the payload's action, redacts
     canaries, and has fixture-trace tests for followed and not followed. Delete this comment once read. -->
**Mitigation:** `<id>` (`spe_mitigate_<id>`): <what it changes, where> (if any)
**Base:** <base mitigations: the build it runs on>
**Experiment file:** `experiments/<name>.yml`

### Idea and rationale
<why this attack or mitigation, what was tried, known limits>

### Result
Model: <provider / model>   Repeat: <n>
<`matrix.py counts` of each arm, or the rendered table: baseline vs mitigated>
Utility tests pass with the mitigation on: yes / no (if a mitigation)

### Checks
`python3 check_experiment.py <name>`: <output>

<!-- Not an experiment PR? Delete the text above and say instead what this PR changes, why, and
     how it was checked (tests run, commands used). -->
