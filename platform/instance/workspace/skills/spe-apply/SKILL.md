---
name: spe-apply
description: Apply changes in the repository clone to this SPE instance's chat frontend (build images if needed, recreate containers, wait for health). Use after editing anything that is not a live bind mount; see AGENTS.md for what is live.
---

# spe-apply

Run on this VM, as the workspace user:

```bash
spe-apply            # build what the active frontend needs, then up; the usual choice
spe-apply up         # only recreate containers: compose file or agent.yaml changed
spe-apply build agent    # one image (agent, chat-ui, sandbox); then `spe-apply up`
spe-apply status     # containers and the agent's health
spe-apply logs agent # follow a service's logs (agent, sandbox, chat-ui, chat-ui-dev, open-webui, open-terminal)
```

It reads `~/spe-frontend/.env`, builds images from `~/sperange`, runs `docker compose up -d` on `~/spe-frontend/docker-compose.yml` and waits until the frontend answers. It prints what it built and which containers it recreated; secrets never appear in its output. A failed build leaves the running containers as they are.

Do not use `docker compose up --build` by hand: the compose file has no build sections, so it rebuilds nothing. Do not restart the workspace to apply a change: that destroys the VM.
