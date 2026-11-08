# The AG-UI all-features check (Playwright, through a tunnel)

`agui-all-features-check.py` (next to this note) drives the AG-UI chat of a deployed instance in headless
Chromium and prints one PASS/FAIL line per feature: theme (dark at `DOMContentLoaded`, toggle top right), sidebar
width kept over a reload, New chat, a tool-using run (cards grouped under "Explored …"), the model title, rename
from the header, `/compact <focus>` (one divider), and all of it again after a reload. It waits for each run on
the `run_end` lines of the `chat-ui` journals over SSH. About five paid model calls. 17/17 on denbi-agui-01,
2026-11-04 (#36). On Anthropic `claude-haiku-5-5` (2026-11-08) every line passes, but "tool calls grouped" says
`groups=0 cards=4`: Haiku makes one call per model step, and only one response's calls are grouped.

```bash
ss -ltn | grep -q ':13000 ' || ssh -f -N -L 13000:127.0.0.1:3000 agent-service-1
SPE_HOST=agent-service-1 python3 docs/knowledge/agui-all-features-check.py <scratch dir>   # screenshots 1-3
```

- **No `-F ~/.ssh/config`** (`ssh: Could not resolve hostname agent-service-1`): on this guest the host alias
  comes from `/etc/ssh/ssh_config`'s include of the host's config, which `-F` skips; the script's `vm()` hung
  waiting for a `run_end` it could not read. Plain `ssh` works.
- **Check the tunnel's port, not `pgrep -f "…13000…"`**: the pattern matches the shell running it, so no tunnel
  is started and `goto` fails with `ERR_CONNECTION_REFUSED` (`pkill-self-match.md`).
- **Selectors that misled**: the header's rename field is labelled "Chat title" (the sidebar's is "Session
  title"); a tool group's own header is `:scope > summary` (each card inside has a `summary` too).
- **The run wait is global**: `send()` returns when the `run_end` count across *all* journals rises, so a run
  ending in another session passes it. Fine for one session at a time; for the multi-session and mid-run
  switching checks, count in the tested session's journal (`/data/sessions/<id>.jsonl`) only.
- **Screenshots show canary names** (e.g. a file the model names in an answer): keep them out of anything
  public, such as an upstream PR.
- **The archive is on the controller**: `archive.yml` says "Run saved to /data-share/runs/…", a path on the
  machine that ran Ansible (`spe_runs_root`), not on the VM.
