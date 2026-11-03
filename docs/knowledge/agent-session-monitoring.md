# Monitoring the unattended Claude sessions on this VM

The two tool sessions (the `/compact` track and the AG-UI chat improvements) must keep going on
their own: when idle, dead or blocked they are woken up through the methodology's own machinery,
never worked-on or approved by a monitor.

## What the supervisor tick does (`supervise.sh`)

One tick every 10 min over every `unattended=1` registry entry: it resumes a dead run
(`next-session.sh --resume`), starts a lost handoff (`next-session.sh <handoff>`), and restarts a
run whose gate PR gained `approved` (the `waiting-on-user` label is removed by a session or the
user, not by a monitor). Anything it can't fix is a PR comment plus an inbox item
(`status.sh`, `inbox.sh list`).

## The install fails on this VM: no systemd user bus, no cron

`supervise.sh --install` writes `~/.config/systemd/user/agent-supervise.{service,timer}` and then
`systemctl --user enable --now` fails here:

    Failed to connect to user scope bus via local transport: $DBUS_SESSION_BUS_ADDRESS and
    $XDG_RUNTIME_DIR not defined

There is no systemd user manager (no `/run/user/<uid>/bus`) and no `crontab` on the VM. So the
units are dormant; the ticks run from two detached daemons instead.

## The two daemons (both in `~/.local/bin/`, logs in `~/.local/state/agent-sessions/`)

- `agent-watchdog.sh` → `watchdog.log`: one `supervise.sh` tick every 10 min (the file already has
  its own flock, so ticks never overlap).
- `agent-selfmonitor.sh` → `selfmonitor.log`: cross-check every 10 min, offset from the tick —
  restarts the watchdog if its process or its last tick output is > 20 min old, and for every
  `unattended=1` entry checks `status.sh` directly: a run dead across two consecutive checks
  (~20 min, in `supervise.log` the tick left no action) is resumed directly
  (`next-session.sh --resume <worktree>`); a live session idle > 25 min (transcript column) forces
  an extra tick so the stall check runs. It implements and decides nothing else.

Started detached (`setsid nohup … &`); after a VM restart bring both up with:

    setsid nohup ~/.local/bin/agent-watchdog.sh >/dev/null 2>&1 &
    setsid nohup ~/.local/bin/agent-selfmonitor.sh >/dev/null 2>&1 &

If the VM ever gets a systemd user bus or cron, delete the daemons and `supervise.sh --install`.
Only the *current* runs of a track are `unattended=1` (the two live ones were flipped by hand,
2026-11-03); newly chained sessions inherit it, registry entries with `unattended=0` are left
alone as "a person's own".
