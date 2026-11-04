#!/usr/bin/env python3
"""Turn an OpenWebUI export bundle into a readable run directory.

    write_run.py <bundle.json> <run dir> <report note title>

Can be re-run on an archived run to re-render it with a newer version of
this script: write_run.py <run dir>/openwebui-export.json <run dir> "Run report",
and for the AG-UI part, <run dir>/agui/openwebui-export.json <run dir>/agui "Run report". Render
agui/ first: Open WebUI's index.md links it when it is there.

Writes report.md (the participant's "Run report" note), chats/NN-<title>.md
and .json (active branch of each chat, with tags), notes/ for any other
notes, index.md (overview) and openwebui-export.json (the raw bundle).

A bundle with spe_archive_mode is the AG-UI chat UI's export (one assistant
message per run, with spe_run, spe_ignored and, for a /compact run, spe_command):
write_agui() renders it instead, escaping or fencing every text, with each
run's status, its ignored content, and a compaction marker or a refused or
failed /compact run shown as requested by the participant; it links
agui-journals/ and agent-runs.jsonl when they are in the run directory. There
is no report.
Stdlib only.
"""
import datetime
import json
import os
import re
import shutil
import sys


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:50] or "untitled"


def when(t):
    if not t:
        return ""
    t = float(t)
    while t > 1e11:  # OpenWebUI mixes s, ms and ns timestamps
        t /= 1000
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def active_branch(chat):
    """Messages along the branch the participant last looked at."""
    hist = chat.get("history") or {}
    msgs = hist.get("messages") or {}
    cur, out = hist.get("currentId"), []
    while cur and cur in msgs:
        out.append(msgs[cur])
        cur = msgs[cur].get("parentId")
    return out[::-1] if out else (chat.get("messages") or [])


def fence(text, lang=""):
    """A code fence one backtick longer than the longest backtick run inside (at least three)."""
    text = text.rstrip("\n")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{text}\n{ticks}"


def texts(parts):
    if isinstance(parts, str):
        return parts
    return "".join(p.get("text", "") for p in parts or [] if isinstance(p, dict))


def render_message(m):
    """Assistant turns keep the full trace in m["output"]: reasoning, tool
    calls, tool results and text, in order. Fall back to m["content"]."""
    out = []
    for it in m.get("output") or []:
        t = it.get("type")
        if t == "message":
            out.append(texts(it.get("content")).strip())
        elif t == "reasoning":
            out.append("<details><summary>Reasoning</summary>\n\n"
                       + texts(it.get("content")).strip() + "\n\n</details>")
        elif t == "function_call":
            args = it.get("arguments") or ""
            try:
                args = json.dumps(json.loads(args), indent=2, ensure_ascii=False)
            except ValueError:
                pass
            out.append(f"**Tool call `{it.get('name')}`**\n\n" + fence(args, "json"))
        elif t == "function_call_output":
            out.append("<details><summary>Tool result</summary>\n\n"
                       + fence(texts(it.get("output"))) + "\n\n</details>")
        else:
            out.append(fence(json.dumps(it, indent=2, ensure_ascii=False), "json"))
    if not out:
        return (m.get("content") or "").strip()
    return "\n\n".join(x for x in out if x)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# AG-UI bundles: the chat UI's exporter writes this same shape plus `spe_archive_mode` (live or final), one
# assistant message per run carrying `spe_run` (its status), `spe_ignored` (what the client sent that was not
# used) and, for a command run (spec §15), `spe_command` (its name and focus, refused and failed runs
# included). Everything in them came from a participant or a model, so it is rendered fenced or escaped.

MARKER_PREFIX = "spe-compaction-"
IGNORED_HEADING = "## sent by the client, not used"
STATUS_NOTES = {
    "failed": "the agent's stream ended in an error, or without a final event",
    "cancelled": "stopped by the participant before it ended",
    "aborted": "the chat UI could not save the run, so it ended it",
    "refused": "the chat UI did not call the agent (the reason follows)",
    "incomplete": "no end was recorded; in a live archive the run may still have been going",
}
ARCHIVE_MODES = {
    "live": "live, copied while the chat UI and the agent kept running (a run marked incomplete may still "
            "have been going)",
    "final": "final, copied after the chat UI and the agent had stopped",
}
AGUI_HEADER = ["| # | Session | Tags | Created | Runs | Compactions | State |", "|---|---|---|---|---|---|---|"]


def one_line(s):
    return " ".join(str(s or "").split())


def md_inline(s):
    """Untrusted text as one line of Markdown text: every character that could start markup is escaped."""
    return re.sub(r"([\\`*_\[\]<>|#&])", r"\\\1", one_line(s))


def code_span(s):
    """Untrusted text as one inline code span, its backtick run longer than any inside."""
    s = one_line(s)
    ticks = "`" * (max((len(r) for r in re.findall(r"`+", s)), default=0) + 1)
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{ticks}{pad}{s}{pad}{ticks}"


def when_iso(iso):
    """'2026-11-03T11:00:00.000Z' -> '2026-11-03 11:00 UTC'; anything unparsable escaped as given."""
    if not iso:
        return ""
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return md_inline(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def pretty_args(raw):
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(raw or "")


def count_run_log(path):
    """(runs, title calls) in a run log. A run line has no "type" field; `/title`'s calls are logged with
    `"type": "title"` so evaluations see them, but they are not agent runs. A line that fails to parse is
    counted as a run, as every line was before `/title` existed."""
    runs = titles = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            if isinstance(record, dict) and record.get("type") == "title":
                titles += 1
            else:
                runs += 1
    return runs, titles


def is_compaction(item_or_message):
    """The agent's compaction marker: an assistant message, or a message output item, whose id has the prefix."""
    d = item_or_message
    return (isinstance(d, dict) and d.get("type", "message") == "message" and d.get("role") == "assistant"
            and str(d.get("id") or "").startswith(MARKER_PREFIX))


def render_status(run):
    """One line for a run that did not complete; "" for a completed one and for a message that is no run's."""
    status = run.get("status") if isinstance(run, dict) else None
    if not status or status == "completed":
        return ""
    line = f"**Run {md_inline(status)}**: {STATUS_NOTES.get(status, 'a status this script does not know')}."
    return f"{line} Error: {md_inline(run['error'])}" if run.get("error") else line


def render_ignored(entries):
    """What the client sent with a run that the chat UI did not use: each entry's kind, its content fenced."""
    entries = [e for e in entries or [] if isinstance(e, dict)]
    if not entries:
        return ""
    out = [IGNORED_HEADING, "",
           "The client sent this with the run below; the agent never received it.", ""]
    for e in entries:
        kind, message = md_inline(e.get("kind")) or "?", e.get("message")
        if isinstance(message, dict):
            out += [f"**{kind}**: {md_inline(message.get('role')) or '?'} message {code_span(message.get('id'))}", "",
                    fence(json.dumps(message, indent=2, ensure_ascii=False), "json"), ""]
        else:
            out += [f"**{kind}**: message {code_span(message)}", ""]
    return "\n".join(out[:-1])


def render_command(cmd):
    """A command run's line (spec §15, *The archive*): who asked, and the focus fenced."""
    if not isinstance(cmd, dict) or cmd.get("name") != "compact":
        return ""
    out = "*Requested by the participant (`/compact`)*"
    focus = cmd.get("focus")
    if isinstance(focus, str) and focus:
        out += "\n\n" + fence(focus)
    return out


def render_output(m):
    """A run's output items in order: text and results fenced, tool calls with fenced arguments, a marker as a
    Compacted section naming who asked for it. A command run with no marker (refused, failed or cancelled)
    shows that same line on its own, after the run's status."""
    cmd = render_command(m.get("spe_command"))
    out = []
    for it in m.get("output") or []:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if is_compaction(it):
            out.append("## Compacted\n\n" + (cmd + "\n\n" if cmd else "")
                       + "From here the model saw this summary instead of the messages above.\n\n"
                       + fence(texts(it.get("content"))))
            cmd = ""
        elif t == "message":
            if texts(it.get("content")).strip():
                out.append(fence(texts(it.get("content"))))
        elif t == "reasoning":
            out.append("<details><summary>Reasoning</summary>\n\n" + fence(texts(it.get("content")))
                       + "\n\n</details>")
        elif t == "function_call":
            out.append(f"**Tool call** {code_span(it.get('name'))}\n\n"
                       + fence(pretty_args(it.get("arguments")), "json"))
        elif t == "function_call_output":
            out.append("<details><summary>Tool result</summary>\n\n" + fence(texts(it.get("output")))
                       + "\n\n</details>")
        else:
            out.append(fence(json.dumps(it, indent=2, ensure_ascii=False), "json"))
    if not out and str(m.get("content") or "").strip():
        out.append(fence(str(m["content"])))
    if cmd:
        out.insert(0, cmd)
    return "\n\n".join(out)


def render_agui_message(m, off_branch=False):
    role = m.get("role", "?")
    head = f"## {md_inline(role) or '?'} · {when(m.get('timestamp'))}"
    if off_branch:
        parent = m.get("parentId")
        head += f" · after {code_span(parent)}" if parent else " · first message"
    lines = []
    if role == "assistant":
        ignored = render_ignored(m.get("spe_ignored"))
        if ignored:  # sent with the user's turn above, so between the two turns
            lines += [ignored, ""]
        lines += [head, ""]
        status = render_status(m.get("spe_run"))
        if status:
            lines += [status, ""]
        body = render_output(m)
    else:
        lines += [head, ""]
        text = texts(m.get("content"))
        body = fence(text) if text.strip() else ""
    if body:
        lines += [body, ""]
    return lines


def agui_branch(chat):
    """The messages along currentId, oldest first, like active_branch() but stopping at a message already seen:
    the parent links came from a client, and a forged cycle must not hang the archive."""
    msgs = (chat.get("history") or {}).get("messages") or {}
    cur, out, seen = (chat.get("history") or {}).get("currentId"), [], set()
    while isinstance(cur, str) and cur in msgs and cur not in seen and isinstance(msgs[cur], dict):
        seen.add(cur)
        out.append(msgs[cur])
        cur = msgs[cur].get("parentId")
    return out[::-1]


def history_of(c):
    msgs = ((c.get("chat") or {}).get("history") or {}).get("messages") or {}
    return [m for m in msgs.values() if isinstance(m, dict)]


def agui_state(c):
    deleted = (c.get("meta") or {}).get("spe_deleted_at")
    if deleted:
        return f"deleted {when_iso(deleted)}"
    return "hidden" if c.get("archived") else "active"


def agui_runs(c):
    return [m["spe_run"] for m in history_of(c) if isinstance(m.get("spe_run"), dict)]


def render_agui_chat(c):
    tags = [one_line(t) for t in (c.get("meta") or {}).get("tags") or []]
    counts = {}
    for r in agui_runs(c):
        counts[str(r.get("status"))] = counts.get(str(r.get("status")), 0) + 1
    runs = f"{sum(counts.values())} (" + ", ".join(f"{md_inline(k)} {v}" for k, v in sorted(counts.items())) + ")" \
        if counts else "0"
    lines = []
    if (c.get("meta") or {}).get("spe_deleted_at"):
        lines += [f"Deleted by the participant at {when_iso(c['meta']['spe_deleted_at'])}.", ""]
    lines += [
        f"# {md_inline(c.get('title')) or 'Untitled'}",
        "",
        f"- Session: {code_span(c.get('id'))}",
        f"- Created: {when(c.get('created_at'))}",
        f"- Updated: {when(c.get('updated_at'))}",
        f"- Tags: {md_inline(', '.join(tags)) or '-'}",
        f"- State: {agui_state(c)}",
        f"- Runs: {runs}",
        "",
    ]
    branch = agui_branch(c.get("chat") or {})
    for m in branch:
        lines += render_agui_message(m)
    on_branch = {m.get("id") for m in branch}
    rest = [m for m in history_of(c) if m.get("id") not in on_branch]
    if rest:
        lines += ["## Other branches", "",
                  "Messages not on the branch above, in the order they were recorded; each names the message "
                  "it follows.", ""]
        for m in rest:
            lines += render_agui_message(m, off_branch=True)
    return "\n".join(lines)


def write_agui(b, run_dir):
    chats = sorted((c for c in b.get("chats") or [] if isinstance(c, dict)),
                   key=lambda c: (c.get("created_at") or 0, str(c.get("id") or "")))
    chats_dir = os.path.join(run_dir, "chats")
    # A re-render starts chats/ afresh, so no chat is left under an old title.
    if os.path.islink(chats_dir):
        os.unlink(chats_dir)
    elif os.path.isdir(chats_dir):
        shutil.rmtree(chats_dir)
    rows = []
    for i, c in enumerate(chats, 1):
        name = f"{i:02d}-{slug(one_line(c.get('title')))}"
        write(os.path.join(chats_dir, name + ".md"), render_agui_chat(c))
        write(os.path.join(chats_dir, name + ".json"), json.dumps(c, indent=1))
        compactions = sum(1 for m in history_of(c) for it in m.get("output") or [] if is_compaction(it))
        tags = md_inline(", ".join(one_line(t) for t in (c.get("meta") or {}).get("tags") or [])) or "-"
        rows.append(f"| {i:02d} | [{md_inline(c.get('title')) or 'Untitled'}](chats/{name}.md) | {tags} "
                    f"| {when(c.get('created_at'))} | {len(agui_runs(c))} | {compactions} | {agui_state(c)} |")

    mode = b.get("spe_archive_mode")
    log = os.path.join(run_dir, "agent-runs.jsonl")
    # The archive renders into <run>/agui/, beside Open WebUI's part; run.yml is then one level up.
    name = os.path.basename(run_dir.rstrip("/"))
    up = "../" if name == "agui" else ""
    if up:
        name = os.path.basename(os.path.dirname(run_dir.rstrip("/"))) + ", AG-UI chat"
    index = [
        f"# Run {name}",
        "",
        "- Frontend: agui (CopilotKit chat). The AG-UI frontend has no run report.",
        f"- Archive: {ARCHIVE_MODES.get(mode) or md_inline(mode)}",
        f"- Exported: {when(b.get('exported_at'))}",
        f"- Parameters and canary record: [run.yml]({up}run.yml), {up}canaries.json",
    ]
    if os.path.isdir(os.path.join(run_dir, "agui-journals")):
        index.append("- Session journals as stored (hidden and deleted included): [agui-journals/](agui-journals/)")
    if os.path.isfile(log):
        runs, titles = count_run_log(log)
        suffix = f" + {titles} title call{'s' if titles != 1 else ''}" if titles else ""
        index.append(f"- Agent run log: [agent-runs.jsonl](agent-runs.jsonl), {runs} runs{suffix}")
    else:
        index.append("- Agent run log: none (no run reached the agent)")
    index.append("")
    index += [*AGUI_HEADER, *rows, ""] if rows else ["No session was recorded.", ""]
    write(os.path.join(run_dir, "index.md"), "\n".join(index))
    hidden = sum(1 for c in chats if agui_state(c) == "hidden")
    deleted = sum(1 for c in chats if agui_state(c).startswith("deleted"))
    print(f"{len(chats)} sessions ({hidden} hidden, {deleted} deleted), {md_inline(mode)} archive, "
          f"{'run log' if os.path.isfile(log) else 'no run log'}")


def main(argv):
    bundle_path, run_dir, report_title = argv[:3]
    with open(bundle_path) as f:
        b = json.load(f)

    tag_names = {t["id"]: t["name"] for t in b.get("tags") or []}
    os.makedirs(run_dir, exist_ok=True)
    raw = os.path.join(run_dir, "openwebui-export.json")
    if os.path.isfile(raw) and not os.path.samefile(bundle_path, raw):
        with open(raw) as f:
            kept = json.load(f)
        if ("spe_archive_mode" in kept) != ("spe_archive_mode" in b):
            # An AG-UI bundle into Open WebUI's run directory (or the reverse) would replace its only raw export.
            sys.exit(f"write_run.py: {raw} is the other frontend's export; the AG-UI part renders into <run>/agui")
    if not (os.path.exists(raw) and os.path.samefile(bundle_path, raw)):  # re-rendering in place
        shutil.copy(bundle_path, raw)

    if "spe_archive_mode" in b:  # an AG-UI bundle: the chat UI's exporter
        write_agui(b, run_dir)
        return

    # Notes: the run report, plus anything else the participant wrote.
    report = None
    for n in b.get("notes") or []:
        md = ((n.get("data") or {}).get("content") or {}).get("md") or ""
        if n.get("title") == report_title and report is None:
            report = md
            write(os.path.join(run_dir, "report.md"), md)
        else:
            write(os.path.join(run_dir, "notes", slug(n.get("title")) + ".md"), md)

    template = (b.get("report_template_md") or "").strip()
    if report is None:
        report_state = f'missing (no "{report_title}" note)'
    elif template and report.strip() == template:
        report_state = "**not filled in**"
    else:
        report_state = "filled in"

    # Chats, oldest first.
    rows = []
    chats = sorted(b.get("chats") or [], key=lambda c: c.get("created_at") or 0)
    for i, c in enumerate(chats, 1):
        msgs = active_branch(c.get("chat") or {})
        tags = [tag_names.get(t, t) for t in (c.get("meta") or {}).get("tags") or []]
        name = f"{i:02d}-{slug(c.get('title'))}"
        lines = [
            f"# {c.get('title') or 'Untitled'}",
            "",
            f"- Created: {when(c.get('created_at'))}",
            f"- Updated: {when(c.get('updated_at'))}",
            f"- Tags: {', '.join(tags) or '-'}",
            f"- Archived in OpenWebUI: {'yes' if c.get('archived') else 'no'}",
            "",
        ]
        for m in msgs:
            who = m.get("role", "?")
            if who == "assistant" and m.get("model"):
                who += f" ({m['model']})"
            lines += [f"## {who} · {when(m.get('timestamp'))}", "", render_message(m), ""]
        write(os.path.join(run_dir, "chats", name + ".md"), "\n".join(lines))
        write(os.path.join(run_dir, "chats", name + ".json"), json.dumps(c, indent=1))
        link = re.sub(r"([\[\]|])", r"\\\1", c.get("title") or "Untitled")
        rows.append(f"| [{link}](chats/{name}.md) | {', '.join(tags) or '-'} "
                    f"| {'yes' if c.get('archived') else ''} | {len(msgs)} | {when(c.get('created_at'))} |")

    index = [
        f"# Run {os.path.basename(run_dir.rstrip('/'))}",
        "",
        f"- Exported: {when(b.get('exported_at'))}",
        f"- Report: [report.md](report.md), {report_state}",
        "- Parameters and canary record: [run.yml](run.yml), canaries.json",
        *(["- AG-UI chat sessions: [agui/](agui/index.md)"]
          if os.path.isfile(os.path.join(run_dir, "agui", "index.md")) else []),
        "",
        "| Chat | Tags | Archived | Messages | Created |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    write(os.path.join(run_dir, "index.md"), "\n".join(index))
    print(f"{len(chats)} chats, report {report_state}")


if __name__ == "__main__":
    main(sys.argv[1:])
