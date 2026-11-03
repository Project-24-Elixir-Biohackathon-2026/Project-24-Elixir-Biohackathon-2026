# `spe_agui_source_dir` is `platform/agui`, not the repository root

Found 2026-11-03, deploying the AG-UI compaction slice 2 worktree to the dev VM.

**Symptom.** `create.yml -e spe_agui_source_dir=<worktree>` fails at `agui : Tracked agent and chat UI sources,
staged`: `git -C <worktree> ls-files -- pydantic-ai-agent copilotkit-chat` lists nothing, then `cd
…/pydantic-ai-agent` fails with "No such file or directory". The running containers are not touched.

**Why.** The role expects the directory that directly holds `pydantic-ai-agent/` and `copilotkit-chat/`
(`inventory/group_vars/all.yml`, `spe_agui_source_dir`'s default `{{ playbook_dir }}/../../agui`). Docs that
said `<worktree>` dated from before the sources moved under `platform/agui/`.

**Works**, from the main checkout's `platform/ansible/`:

```bash
-e spe_agui_source_dir=<worktree>/platform/agui
```
