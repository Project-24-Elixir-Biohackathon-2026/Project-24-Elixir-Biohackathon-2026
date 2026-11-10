"""The participant page's HTML (spec *Participant page*; decisions 4, 5, 11): `participant_body`
renders the header, the headline counts and the hits, newest first; `standalone` wraps a body into a
whole, self-contained HTML document (hits.css inlined, no script) for the early output
(`canary_watch.py --archive ... --html PAGE.html`) and for tests. The live service page (slice 3) adds
its own script (notifications, the event stream) around the same body.

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
import time
from datetime import datetime, timezone
from pathlib import Path

NOTICE = "Matching is literal: an encoded, split or paraphrased canary is not seen."
NO_HITS = "No hits yet."
NOT_WATCHED = "Not watched yet."
CAPPED = "hits file full"
ENCRYPTED_NOTICE = "The canary record is encrypted: the watcher cannot match this workspace."

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
