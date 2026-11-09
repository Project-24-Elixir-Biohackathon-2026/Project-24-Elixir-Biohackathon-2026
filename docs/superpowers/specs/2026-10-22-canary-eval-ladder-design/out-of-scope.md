# Out of scope

| Item | Why | Where it went |
|---|---|---|
| The typed GA4GH tool server (L4's implementation) | a subsystem of its own; this spec fixes only what L4 must satisfy | its own spec, after this one's plan; `BACKLOG.md` until then |
| `spe_agent_sandbox_operations` as a level or negative control | with `run_command` kept, trimming the other operations changes no capability; without it nothing works. Decided against spending runs to show it | not pursued |
| Scoring through Open WebUI (`openwebui` in `spe_frontends`; ladder levels run `[agui]`) | 0013 decision 2: score through the AG-UI agent first, cross-check headline results on Open WebUI later | a later spec, once the matrix exists |
| promptfoo's red-team generator | generated attacks vary between runs, are not tied to our canaries and need model graders | a possible later supplement for breadth |
| Parallel stacks on one VM | only needed if restores are slow | [inputs-for-plan](inputs-for-plan.md), restore time |
| Per-user sandbox isolation, credential proxies, human approval of writes (0011 §3) | not on the leak paths P1–P4 this ladder closes | 0011's profile table, for later levels |
