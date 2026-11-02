#!/usr/bin/env python3
"""Turn an OpenWebUI export bundle into a readable run directory.

    write_run.py <bundle.json> <run dir> <report note title>

Can be re-run on an archived run to re-render it with a newer version of
this script: write_run.py <run dir>/openwebui-export.json <run dir> "Run report".

Writes report.md (the participant's "Run report" note), chats/NN-<title>.md
and .json (active branch of each chat, with tags), notes/ for any other
notes, index.md (overview) and openwebui-export.json (the raw bundle).
Stdlib only. write_agui_run.py imports slug() and fence() from here.
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


def main(argv):
    bundle_path, run_dir, report_title = argv[:3]
    with open(bundle_path) as f:
        b = json.load(f)

    tag_names = {t["id"]: t["name"] for t in b.get("tags") or []}
    os.makedirs(run_dir, exist_ok=True)
    raw = os.path.join(run_dir, "openwebui-export.json")
    if not (os.path.exists(raw) and os.path.samefile(bundle_path, raw)):  # re-rendering in place
        shutil.copy(bundle_path, raw)

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
