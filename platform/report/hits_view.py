"""The participant page's HTML (spec *Participant page*; decisions 4, 5, 11): `participant_body`
renders the header, the headline counts and the hits, newest first; `standalone` wraps a body into a
whole, self-contained HTML document (hits.css inlined, no script) for the early output
(`canary_watch.py --archive ... --html PAGE.html`) and for tests. The live service page (slice 3) adds
its own script (notifications, the event stream) around the same body.

The admin page (spec *Admin page*; decision 7): `workspace_rows` reads every workspace's hits and
status file in the hits directory into one summary row each, and `admin_body` renders those rows,
the filters and the hits of all workspaces as one list (each wrapped with the data the filters and
static/hits-admin.js read).

`status` is the watcher's status file (ruling 6: `state`, `since`, `last_poll`, `note`), read by the
live service; `status_line` turns it into the header's clause ("running · watched 3 s ago"), and
`empty_text` into the placeholder text for a hits list with none to show, shared with the live
service's status event so hits.js can keep a placeholder current without a reload. `None` is
reserved for the early output, which is never live (`_header`'s "archived run"): the live service
passes `{}` instead when the workspace has no status file yet, so this one argument cannot be
confused between the two callers.

Every field is passed through html.escape; nothing here logs or raises on a canary value, since the
value is exactly what the page is meant to show (decision 10: to the workspace's owner and Coder
owners only, which the caller has already checked).

Standard library only: the portal runs this from its repository checkout with the system Python.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from canary_hits import HitsFile

NOTICE = "Matching is literal: an encoded, split or paraphrased canary is not seen."
NO_HITS = "No hits yet."
NOT_WATCHED = "Not watched yet."
CAPPED = "hits file full"
ENCRYPTED_NOTICE = "The canary record is encrypted: the watcher cannot match this workspace."
ADMIN_BANNER = "Hits are what each participant's own instance reported."
# A workspace id, the stem of its hits and status files (and of its report sidecar).
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Loud kinds, in the headline's order (spec *Participant page* mockup); quiet kinds, and any hit whose
# kind is unknown or missing, collapse into "also seen" (spec *Hits*).
LOUD_KINDS = ("touched", "answer", "sent", "delivered")
LOUD = frozenset(LOUD_KINDS)  # the same kinds as a set: the event stream's `loud` flag
QUIET_KINDS = ("seen", "args", "prompt")
# The headline's "also seen" label for each quiet kind (mockup: "(metadata, args, prompt)").
# static/hits.js mirrors QUIET_LABELS and this order (QUIET_KINDS then OTHER_LABEL) to keep a
# live-added label in the same place a reload would put it; change both together.
QUIET_LABELS = {"seen": "metadata", "args": "args", "prompt": "prompt"}
OTHER_LABEL = "other"
FRONTEND_LABELS = {"agui": "AG-UI", "openwebui": "Open WebUI"}

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _marked_excerpt(excerpt: dict | None) -> str:
    """The excerpt's text with text[start:end] wrapped in <mark>, each part escaped on its own so the
    mark cannot be escaped away or straddle an entity."""
    if not isinstance(excerpt, dict):
        return ""
    text = excerpt.get("text")
    if not isinstance(text, str):
        return ""
    start, end = excerpt.get("start"), excerpt.get("end")
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(text)):
        return _esc(text)
    return _esc(text[:start]) + "<mark>" + _esc(text[start:end]) + "</mark>" + _esc(text[end:])


def _tool_html(tool: dict | None) -> str:
    if not isinstance(tool, dict):
        return ""
    out = [f'<div class="field tool"><span class="k">tool</span> <code>{_esc(tool.get("name"))}</code>'
           f' <code class="args">{_esc(tool.get("args"))}</code></div>']
    if tool.get("result") is not None:
        out.append(f'<div class="field result"><span class="k">result</span>'
                    f' <code>{_esc(tool.get("result"))}</code></div>')
    return "".join(out)


def hit_html(hit: dict) -> str:
    """One hit's collapsed <details>, as the page lists it and the event stream carries it (ruling 8:
    one renderer, so a hit inserted live reads as one loaded with the page). Its `data-id`,
    `data-kind`, `data-session` (the session id) and `data-run` let the page script place and count it."""
    kind = hit.get("kind")
    loud = "loud" if kind in LOUD else "quiet"
    frontend = FRONTEND_LABELS.get(hit.get("frontend"))
    session = hit.get("session") if isinstance(hit.get("session"), dict) else {}
    canary = hit.get("canary") if isinstance(hit.get("canary"), dict) else {}
    when = hit.get("at") or hit.get("detected")

    summary = (
        f'<summary><span class="time">{_esc(when)}</span> '
        f'<span class="kind kind-{_esc(kind)}">{_esc(kind)}</span> '
        f'<span class="canary-type">{_esc(canary.get("type"))}</span>'
        f' &middot; <span class="canary-file">{_esc(canary.get("file"))}</span></summary>'
    )

    trace = []
    if frontend:
        trace.append(f'<div class="field frontend">{_esc(frontend)}</div>')
    if session.get("title"):
        trace.append(f'<div class="field session">session &quot;{_esc(session.get("title"))}&quot;</div>')
    if hit.get("run"):
        trace.append(f'<div class="field run">run {_esc(hit.get("run"))}</div>')
    if hit.get("prompt"):
        trace.append(f'<div class="field prompt"><span class="k">prompt</span> '
                      f'&quot;{_esc(hit.get("prompt"))}&quot;</div>')
    trace.append(_tool_html(hit.get("tool")))
    trace.append(f'<div class="field excerpt"><span class="k">excerpt</span> {_marked_excerpt(hit.get("excerpt"))}</div>')

    data = (f'data-id="{_esc(hit.get("id"))}" data-kind="{_esc(kind)}" '
            f'data-session="{_esc(session.get("id"))}" data-run="{_esc(hit.get("run"))}"')
    return f'<details class="hit {loud}" {data}>{summary}<div class="trace">{"".join(trace)}</div></details>'


def _counts(hits: list[dict]) -> dict[str, int]:
    """Hits per kind; a hit whose kind is unknown or missing counts as OTHER_LABEL, a quiet one."""
    out = {k: 0 for k in LOUD_KINDS + QUIET_KINDS + (OTHER_LABEL,)}
    for h in hits:
        kind = h.get("kind")
        out[kind if kind in LOUD_KINDS or kind in QUIET_KINDS else OTHER_LABEL] += 1
    return out


def _headline(hits: list[dict]) -> str:
    counts = _counts(hits)
    loud_total = sum(counts[k] for k in LOUD_KINDS)
    quiet_total = len(hits) - loud_total
    per_kind = " &middot; ".join(f"{_esc(k)} {counts[k]}" for k in LOUD_KINDS)
    out = (f'<div class="headline"><span class="leaks">{loud_total} leak{"" if loud_total == 1 else "s"}</span>'
           f'<span class="per-kind">{per_kind}</span>')
    if quiet_total:
        quiet_kinds = ", ".join([QUIET_LABELS[k] for k in QUIET_KINDS if counts[k]]
                                + ([OTHER_LABEL] if counts[OTHER_LABEL] else []))
        out += f'<span class="also-seen">also seen: {quiet_total} ({_esc(quiet_kinds)})</span>'
    out += "</div>"
    return out


def _epoch(value: object) -> float | None:
    """An `_iso`-formatted (canary_watch.py) timestamp as epoch seconds, or None for anything else
    (a status file is the watcher's own write, but a clock or a crash mid-write can still leave it
    short or malformed; the line is then just left out)."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def status_line(status: dict | None, now: float) -> str:
    """The header's live status clause (ruling 6: the watcher's status file: `state`, `since`,
    `last_poll`, `note`): "running · watched 3 s ago", "stopped" (or "stopped · archive incomplete"
    when `note` is set), "not reachable since 14:02", "hits file full" (state `capped`; a note that says
    more is appended as `stopped`'s is).
    `None`, or a dict with no state yet (discovered but never polled, or simply no status file on
    disk): "not watched yet". Anything else that is not a dict (a caller passing plain text) is
    shown as-is; the caller escapes it."""
    if status is None:
        return "not watched yet"
    if not isinstance(status, dict):
        return str(status)
    state, note = status.get("state"), status.get("note")
    if not state:
        return "not watched yet"
    if state == "running":
        watched = _epoch(status.get("last_poll"))
        return "running" if watched is None else f"running · watched {max(0, round(now - watched))} s ago"
    if state == "stopped":
        return f"stopped · {note}" if note else "stopped"
    if state == "unreachable":
        since = status.get("since")
        return f"not reachable since {since[11:16]}" if isinstance(since, str) and len(since) >= 16 else "not reachable"
    if state == "capped":
        # The watcher's own note for this state is the same words: appended only when it says more.
        return f"{CAPPED} · {note}" if note and note != CAPPED else CAPPED
    if state == "encrypted":
        return "canary record is encrypted"
    return str(state)


def empty_text(status: dict | None) -> str:
    """The text for a hits list with none to show: `participant_body`'s placeholder, and the
    status event's `empty` field so hits.js can keep an already-shown placeholder current without
    a reload. ENCRYPTED_NOTICE when the watcher found the record encrypted; NOT_WATCHED for a
    workspace discovered but never polled yet (a status dict with no `state`); else NO_HITS (an
    archived run, or a watched workspace with no hits)."""
    state = status.get("state") if isinstance(status, dict) else None
    if state == "encrypted":
        return ENCRYPTED_NOTICE
    if isinstance(status, dict) and not state:
        return NOT_WATCHED
    return NO_HITS


def _header(meta: dict, hits: list[dict], status: dict | None, now: float) -> str:
    label = meta.get("instance") or meta.get("workspace") or "workspace"
    owner = meta.get("owner")
    text = "archived run" if status is None else status_line(status, now)
    # #hits-status: the live service's script sets its textContent on every status event
    # (slice 3); the early output (standalone, no script) never updates it.
    head = f'<h1>Canary hits &middot; {_esc(label)} (<span id="hits-status">{_esc(text)}</span>)</h1>'
    if owner:
        head += f'<p class="owner muted">owner {_esc(owner)}</p>'
    return head + _headline(hits)


def participant_body(meta: dict, hits: list[dict], status: dict | None) -> str:
    """The participant page's body (spec *Participant page*): header (workspace, status), the
    headline counts, the literal-matching notice, then the loud hits newest first, each collapsed
    under <details>, then the quiet ones (and any of unknown kind) newest first inside one collapsed
    "also seen (N)" block (spec *Hits*), left out when there are none. `meta` is
    `workspace`/`instance`/`owner` (canary_watch.archive_meta's shape, or the report sidecar's);
    `status` is None for an archived run, else the watcher's status file (or `{}` for a live
    workspace with none yet). A workspace whose record is encrypted (`status["state"] ==
    "encrypted"`) shows that instead of any hits; otherwise, with none to show, "No hits yet." for an
    archived run or a watched one, "Not watched yet." for one with no status yet."""
    now = time.time()
    state = status.get("state") if isinstance(status, dict) else None
    ordered = sorted(hits, key=lambda h: str(h.get("at") or h.get("detected") or ""), reverse=True)
    loud = [h for h in ordered if h.get("kind") in LOUD_KINDS]
    quiet = [h for h in ordered if h.get("kind") not in LOUD_KINDS]
    items = "".join(hit_html(h) for h in loud)
    if quiet:
        items += (f'<details class="also-seen"><summary>also seen ({len(quiet)})</summary>'
                  f'{"".join(hit_html(h) for h in quiet)}</details>')
    if state == "encrypted":
        items = f'<p class="muted">{_esc(ENCRYPTED_NOTICE)}</p>'
    elif not items:
        # "placeholder": the class hits.js removes once a live hit arrives, and whose text a
        # status event keeps current meanwhile (a hit cannot change the encrypted notice above,
        # so that one stays plain "muted").
        items = f'<p class="muted placeholder">{_esc(empty_text(status))}</p>'
    # The two buttons below are static, `hidden` until hits.js (slice 3) removes the attribute:
    # with no script (the standalone early output), they stay invisible. hits.js builds no HTML
    # of its own but these two, with document.createElement + textContent, so they are rendered
    # here once, where hit_html's escaping discipline already lives.
    actions = ('<div class="hits-actions">'
               '<button type="button" id="notify-btn" class="btn" hidden>Notify me</button>'
               '<button type="button" id="group-toggle" class="btn" hidden>Group by run</button>'
               '</div>')
    return (
        '<main class="hits">'
        f'<header class="report-head card">{_header(meta, hits, status, now)}'
        f'<p class="notice muted">{_esc(NOTICE)}</p>{actions}</header>'
        f'<section class="card hit-list">{items}</section>'
        '</main>'
    )


# --- the admin page (spec *Admin page*) -------------------------------------------------------------

def read_status(path: str) -> dict | None:
    """A watcher status file (ruling 6), or None: no file, or one that is not a JSON object (the
    watcher could be mid-write; never raises on it)."""
    try:
        with open(path, encoding="utf-8") as f:
            status = json.load(f)
    except (OSError, ValueError):
        return None
    return status if isinstance(status, dict) else None


def scan_ids(hits_dir: str) -> list[str] | None:
    """Every workspace the hits directory knows: a `<uuid>.jsonl` or a `<uuid>.status.json`; None
    when the directory cannot be listed (the admin stream then tells a failed scan from an empty one)."""
    try:
        names = os.listdir(hits_dir)
    except OSError:
        return None
    out = set()
    for name in names:
        for suffix in (".jsonl", ".status.json"):
            if name.endswith(suffix) and UUID_RE.match(name[:-len(suffix)]):
                out.add(name[:-len(suffix)])
    return sorted(out)


def workspace_ids(hits_dir: str) -> list[str]:
    """`scan_ids`, with an unlistable directory read as an empty one."""
    return scan_ids(hits_dir) or []


def read_all(hits_dir: str) -> dict[str, list[dict]]:
    """Every workspace's hits, by workspace id, each tagged with that id as `workspace` (the file's
    name says whose hits they are, whatever a record says). A file that cannot be read (bad
    permissions, a directory by that name) counts as no hits, logged with the workspace id and the
    error's class only, so its row and every other workspace still render."""
    out = {}
    for wid in workspace_ids(hits_dir):
        try:
            hits = HitsFile(os.path.join(hits_dir, wid + ".jsonl")).read()
        except OSError as e:
            sys.stdout.write(f"hits read {wid}: {type(e).__name__}, shown as no hits\n")
            sys.stdout.flush()
            hits = []
        out[wid] = [h | {"workspace": wid} for h in hits]
    return out


def newest_first(hits: list[dict]) -> list[dict]:
    """The admin page's order across workspaces (its list, hits.json and their caps): newest first by
    `detected`, then by id (a file's later line first). `detected` is the watcher's clock; `at` comes
    from the instance's own journal, which a participant controls, so one workspace's far-future `at`
    could otherwise top the list for good and push every other workspace past the caps."""
    return sorted(hits, key=lambda h: (str(h.get("detected") or ""),
                                       h.get("id") if isinstance(h.get("id"), int) else 0), reverse=True)


def workspace_rows(hits_dir: str, metas: dict[str, dict | None],
                   hits: dict[str, list[dict]] | None = None) -> list[dict]:
    """One row per workspace in the hits directory: `workspace` (the id), `name`, `owner` and
    `instance` (from its report sidecar in `metas`, else from its newest hit: a deleted workspace's
    sidecar is gone but its hits stay), a count per loud kind, `quiet` (every other hit), `newest` (the
    newest hit's `detected`) and `status` (the status line). Newest first; rows with no hit last.
    `hits` is `read_all(hits_dir)` when the caller already has it."""
    hits = read_all(hits_dir) if hits is None else hits
    now = time.time()
    rows = []
    for wid in workspace_ids(hits_dir):
        own = hits.get(wid, [])
        meta = metas.get(wid) or {}
        detected = [str(h["detected"]) for h in own if h.get("detected")]
        latest = max(own, key=lambda h: str(h.get("detected") or ""), default={})
        counts = _counts(own)
        row = {"workspace": wid, "name": meta.get("workspace") or wid,
               "owner": meta.get("owner") or latest.get("owner"),
               "instance": meta.get("instance") or latest.get("instance")}
        row.update({k: counts[k] for k in LOUD_KINDS})
        row["quiet"] = len(own) - sum(counts[k] for k in LOUD_KINDS)
        row["newest"] = max(detected) if detected else None
        row["status"] = status_line(read_status(os.path.join(hits_dir, wid + ".status.json")), now)
        rows.append(row)
    rows.sort(key=lambda r: r["name"])
    rows.sort(key=lambda r: r["newest"] or "", reverse=True)  # stable: no hit ("") last, by name
    return rows


def _filter(key: str, label: str, values: list[tuple[str, str]]) -> str:
    options = "".join(f'<option value="{_esc(v)}">{_esc(text)}</option>' for v, text in values)
    return (f'<label class="filter">{_esc(label)} <select data-filter="{_esc(key)}">'
            f'<option value="">all</option>{options}</select></label>')


def _hit_facets(hit: dict) -> dict[str, str]:
    """What the filters match a hit on, as its wrapper's data-* carry it (hits-admin.js reads the
    same four from a live hit's event)."""
    canary = hit.get("canary") if isinstance(hit.get("canary"), dict) else {}
    return {"kind": str(hit.get("kind") or ""), "type": str(canary.get("type") or ""),
            "frontend": str(hit.get("frontend") or ""), "workspace": str(hit.get("workspace") or "")}


def admin_body(rows: list[dict], hits: list[dict], states: dict[str, str | None], more: int = 0) -> str:
    """The admin page's body (spec *Admin page*): the literal-matching notice (decision 11), the
    workspace table (each name links to its participant page; `states` the Coder state per
    workspace, blank when the lookup failed), the four filters built from the values present, then
    `hits` (already newest first and capped, each with its `workspace`), and a line saying how many
    `more` there are. Each hit is `hit_html` inside a `div.admin-hit` carrying its facets as data-*
    and its workspace's name; each count cell carries the kind it counts (`data-kind`, or
    `data-quiet`) so hits-admin.js bumps the right one from a live hit's kind without a list of its own."""
    names = {r["workspace"]: r["name"] for r in rows}
    trs = []
    for r in rows:
        wid = r["workspace"]
        cells = "".join(f'<td class="count" data-kind="{_esc(k)}">{r[k]}</td>' for k in LOUD_KINDS)
        trs.append(
            f'<tr data-workspace="{_esc(wid)}"><td><a href="/reports/{_esc(wid)}/hits">{_esc(r["name"])}</a></td>'
            f'<td>{_esc(r["owner"])}</td><td><code>{_esc(r["instance"])}</code></td>'
            f'<td class="state">{_esc(states.get(wid))}</td>{cells}'
            f'<td class="count" data-quiet="1">{r["quiet"]}</td>'
            f'<td class="newest">{_esc(r["newest"])}</td><td class="status">{_esc(r["status"])}</td></tr>')
    head = "".join(f"<th>{_esc(k)}</th>" for k in LOUD_KINDS)
    table = ('<table class="workspaces"><thead><tr><th>Workspace</th><th>Owner</th><th>Instance</th>'
             f'<th>State</th>{head}<th>also seen</th><th>Newest (detected)</th><th>Watcher</th></tr></thead>'
             f'<tbody>{"".join(trs)}</tbody></table>'
             if trs else f'<p class="muted">{_esc(NOT_WATCHED)}</p>')

    facets = [_hit_facets(h) for h in hits]

    def present(key: str) -> list[str]:
        return sorted({f[key] for f in facets if f[key]})
    filters = ('<div class="filters">'
               + _filter("kind", "kind", [(v, v) for v in present("kind")])
               + _filter("type", "canary type", [(v, v) for v in present("type")])
               + _filter("frontend", "frontend", [(v, FRONTEND_LABELS.get(v, v)) for v in present("frontend")])
               + _filter("workspace", "workspace", [(v, names.get(v, v)) for v in present("workspace")])
               + '</div>')

    items = []
    for hit, facet in zip(hits, facets):
        data = " ".join(f'data-{k}="{_esc(v)}"' for k, v in facet.items())
        wid = facet["workspace"]
        items.append(f'<div class="admin-hit" {data}><div class="hit-workspace">'
                     f'<a href="/reports/{_esc(wid)}/hits">{_esc(names.get(wid, wid))}</a></div>'
                     f'{hit_html(hit)}</div>')
    listing = "".join(items) or f'<p class="muted placeholder">{_esc(NO_HITS)}</p>'
    tail = f'<p class="more muted">{more} more, older: see each workspace\'s page.</p>' if more else ""
    return (
        '<main class="hits admin">'
        '<header class="report-head card"><h1>Canary hits &middot; all workspaces</h1>'
        f'<p class="notice muted">{_esc(NOTICE)}</p></header>'
        f'<section class="card workspace-list">{table}</section>'
        f'<p class="banner">{_esc(ADMIN_BANNER)}</p>{filters}'
        f'<section class="card hit-list" id="admin-hits">{listing}</section>{tail}'
        '</main>'
    )


def standalone(title: str, body: str) -> str:
    """A whole, self-contained HTML document: `body` wrapped with hits.css inlined into a <style>
    block, no script and no other external reference (the early output, served from the portal's
    shared storage with no service behind it)."""
    css = (STATIC_DIR / "hits.css").read_text(encoding="utf-8")
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_esc(title)}</title><style>{css}</style></head>"
        f"<body><div class=\"wrap\">{body}</div></body></html>"
    )
