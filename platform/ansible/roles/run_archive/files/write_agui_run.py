#!/usr/bin/env python3
"""Turn an AG-UI chat-sessions bundle into a readable run directory.

    write_agui_run.py <bundle dir> <run dir>

<bundle dir> holds sessions/ (one <id>.json per session, as the chat UI stores
them) and, when a run reached the agent, agent-runs.jsonl (the agent's run log).
Given an archived run directory instead (agui-sessions/, agent-runs.jsonl if
there was one), it re-renders that directory in place:

    write_agui_run.py <run dir> <run dir>

Writes index.md (one row per session: title, tags, created, runs, state),
chats/NN-<title>.md and .json (NN in created_at order; the .json is the
session file as stored), agui-sessions/ (the raw files, untouched) and
agent-runs.jsonl. Hidden and deleted sessions are included. Stdlib only;
slug() and fence() come from write_run.py in the same directory.
"""
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_run import fence, slug, write  # noqa: E402


def when(iso):
    """'2026-10-29T10:02:11.123Z' -> '2026-10-29 10:02 UTC'; anything unparsable as given."""
    if not iso:
        return ""
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def one_line(s):
    return " ".join(str(s or "").split())


def title_of(rec):
    return one_line(rec.get("title")) or "Untitled"


def text_of(content):
    """AG-UI content: a string, or a list of parts of which only text parts are shown."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                out.append(str(part.get("text") or ""))
            elif isinstance(part, dict):
                out.append(f"[{part.get('type', 'unknown')} part]")
        return "\n".join(out)
    return json.dumps(content, ensure_ascii=False)


def pretty_args(raw):
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(raw or "")


def state_of(rec):
    if rec.get("deleted_at"):
        return f"deleted {when(rec['deleted_at'])}"
    return "hidden" if rec.get("hidden") else "active"


def runs_summary(rec):
    runs = [r for r in rec.get("runs") or [] if isinstance(r, dict)]
    counts = {}
    for r in runs:
        counts[r.get("status", "?")] = counts.get(r.get("status", "?"), 0) + 1
    detail = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    return f"{len(runs)} ({detail})" if runs else "0"


TEXT_ROLES = ("user", "assistant", "system", "developer")


def render_messages(messages):
    """User and assistant text; each tool call with its arguments and result, fenced."""
    results = {m.get("toolCallId"): m for m in messages
               if isinstance(m, dict) and m.get("role") == "tool"}
    # A result is shown at its call, wherever the call is; only one with no call stands alone.
    call_ids = {call.get("id") for m in messages
                if isinstance(m, dict) and m.get("role") in TEXT_ROLES
                for call in m.get("toolCalls") or [] if isinstance(call, dict)} - {None}
    out = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "?")
        if role == "tool":
            if m.get("toolCallId") in call_ids:
                continue
            out += ["## tool result (no matching call)", "", fence(text_of(m.get("content"))), ""]
            continue
        if role in TEXT_ROLES:
            out += [f"## {role}", ""]
            text = text_of(m.get("content")).strip()
            if text:
                out += [text, ""]
            for call in m.get("toolCalls") or []:
                fn = call.get("function") or {}
                out += [f"**Tool call `{one_line(fn.get('name')) or '?'}`**", "",
                        fence(pretty_args(fn.get("arguments")), "json"), ""]
                result = results.get(call.get("id")) if call.get("id") is not None else None
                if result is not None:
                    label = "Tool error" if result.get("error") else "Tool result"
                    body = text_of(result.get("content"))
                    if result.get("error"):
                        body = (body + "\n" if body else "") + str(result.get("error"))
                    out += [f"<details><summary>{label}</summary>", "", fence(body), "", "</details>", ""]
                else:
                    out += ["(no result recorded)", ""]
            continue
        out += [f"## {one_line(role)}", "", fence(json.dumps(m, indent=2, ensure_ascii=False), "json"), ""]
    return out


def render_session(rec):
    lines = []
    if rec.get("deleted_at"):
        lines += [f"Deleted by the participant at {when(rec['deleted_at'])}.", ""]
    tags = [one_line(t) for t in rec.get("tags") or []]
    lines += [
        f"# {title_of(rec)}",
        "",
        f"- Session: `{one_line(rec.get('id'))}`",
        f"- Created: {when(rec.get('created_at'))}",
        f"- Updated: {when(rec.get('updated_at'))}",
        f"- Tags: {', '.join(tags) or '-'}",
        f"- State: {state_of(rec)}",
        f"- Runs: {runs_summary(rec)}",
        "",
    ]
    lines += render_messages(rec.get("messages") or [])
    return "\n".join(lines)


def load_sessions(sessions_dir):
    """[(file name, record)] for every readable <id>.json, and the names of unreadable ones."""
    records, unreadable = [], []
    for name in sorted(os.listdir(sessions_dir)):
        path = os.path.join(sessions_dir, name)
        if not name.endswith(".json") or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            unreadable.append(name)
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("messages", []), list):
            unreadable.append(name)
            continue
        records.append((name, rec))
    records.sort(key=lambda nr: (str(nr[1].get("created_at") or ""), str(nr[1].get("id") or ""), nr[0]))
    return records, unreadable


def count_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if line.strip())


def same(a, b):
    return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    bundle, run_dir = argv
    if os.path.isdir(os.path.join(bundle, "sessions")):
        src = os.path.join(bundle, "sessions")
    elif os.path.isdir(os.path.join(bundle, "agui-sessions")):
        src = os.path.join(bundle, "agui-sessions")
    else:
        print(f"{bundle}: neither sessions/ nor agui-sessions/", file=sys.stderr)
        return 2
    chats_dir = os.path.join(run_dir, "chats")
    if os.path.realpath(src).startswith(os.path.realpath(chats_dir) + os.sep) or same(src, chats_dir):
        print(f"{src}: inside {chats_dir}, which a render replaces", file=sys.stderr)
        return 2
    os.makedirs(run_dir, exist_ok=True)
    raw_dir = os.path.join(run_dir, "agui-sessions")
    if not same(src, raw_dir):
        os.makedirs(raw_dir, exist_ok=True)
        for name in sorted(os.listdir(src)):
            if os.path.isfile(os.path.join(src, name)):
                shutil.copyfile(os.path.join(src, name), os.path.join(raw_dir, name))
    log_src = os.path.join(bundle, "agent-runs.jsonl")
    log_dst = os.path.join(run_dir, "agent-runs.jsonl")
    has_log = os.path.isfile(log_src)
    if has_log and not same(log_src, log_dst):
        shutil.copyfile(log_src, log_dst)

    records, unreadable = load_sessions(raw_dir)
    # A re-render starts chats/ afresh, so no chat is left under an old title.
    if os.path.islink(chats_dir):
        os.unlink(chats_dir)
    elif os.path.isdir(chats_dir):
        shutil.rmtree(chats_dir)
    rows = []
    for i, (name, rec) in enumerate(records, 1):
        stem = f"{i:02d}-{slug(title_of(rec))}"
        write(os.path.join(run_dir, "chats", stem + ".md"), render_session(rec))
        shutil.copyfile(os.path.join(raw_dir, name), os.path.join(run_dir, "chats", stem + ".json"))
        link = re.sub(r"([\[\]|\\])", r"\\\1", title_of(rec))
        tags = ", ".join(one_line(t) for t in rec.get("tags") or []) or "-"
        rows.append(f"| {i:02d} | [{link}](chats/{stem}.md) | {tags} | {when(rec.get('created_at'))} "
                    f"| {len(rec.get('runs') or [])} | {state_of(rec)} |")

    index = [
        f"# Run {os.path.basename(os.path.abspath(run_dir))}",
        "",
        "- Frontend: agui (CopilotKit chat). The AG-UI frontend has no run report.",
        "- Parameters and canary record: [run.yml](run.yml), canaries.json",
        "- Session files as stored (hidden and deleted included): [agui-sessions/](agui-sessions/)",
    ]
    if has_log:
        index.append(f"- Agent run log: [agent-runs.jsonl](agent-runs.jsonl), {count_lines(log_src)} runs")
    else:
        index.append("- Agent run log: none (no run reached the agent)")
    index.append("")
    if rows:
        index += ["| # | Session | Tags | Created | Runs | State |", "|---|---|---|---|---|---|", *rows, ""]
    else:
        index += ["No session was recorded.", ""]
    if unreadable:
        index += ["Unreadable session files (kept in agui-sessions/): "
                  + ", ".join(f"`{n}`" for n in unreadable), ""]
    write(os.path.join(run_dir, "index.md"), "\n".join(index))
    hidden = sum(1 for _, r in records if r.get("hidden") and not r.get("deleted_at"))
    deleted = sum(1 for _, r in records if r.get("deleted_at"))
    print(f"{len(records)} sessions ({hidden} hidden, {deleted} deleted), "
          f"{'run log' if has_log else 'no run log'}, {len(unreadable)} unreadable")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
