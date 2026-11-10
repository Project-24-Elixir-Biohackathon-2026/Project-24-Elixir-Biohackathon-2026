"""The participant page's HTML (spec *Participant page*; decisions 4, 5, 11): `participant_body`
renders the header, the headline counts and the hits, newest first; `standalone` wraps a body into a
whole, self-contained HTML document (hits.css inlined, no script) for the early output
(`canary_watch.py --archive ... --html PAGE.html`) and for tests. The live service page (slice 3) adds
its own script (notifications, the event stream) around the same body.

Every field is passed through html.escape; nothing here logs or raises on a canary value, since the
value is exactly what the page is meant to show (decision 10: to the workspace's owner and Coder
owners only, which the caller has already checked).

Standard library only: the portal runs this from its repository checkout with the system Python.
"""
from __future__ import annotations

import html
from pathlib import Path

NOTICE = "Matching is literal: an encoded, split or paraphrased canary is not seen."

# Loud kinds, in the headline's order (spec *Participant page* mockup); quiet kinds, and any hit whose
# kind is unknown or missing, collapse into "also seen" (spec *Hits*).
LOUD_KINDS = ("touched", "answer", "sent", "delivered")
QUIET_KINDS = ("seen", "args", "prompt")
# The headline's "also seen" label for each quiet kind (mockup: "(metadata, args, prompt)").
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


def _hit_html(hit: dict) -> str:
    kind = hit.get("kind")
    loud = "loud" if kind in LOUD_KINDS else "quiet"
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

    return f'<details class="hit {loud}">{summary}<div class="trace">{"".join(trace)}</div></details>'


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


def _status_text(status: dict | None) -> str:
    """The header's status clause: "archived run" for the early output (status None, decision 1's
    live polling does not apply to an archive scan); the live service (slice 3) passes a status dict
    (running/not reachable, watched N s ago) whose shape that slice defines."""
    if status is None:
        return "archived run"
    if isinstance(status, dict) and isinstance(status.get("text"), str):
        return status["text"]
    return str(status)  # plain: _header escapes it


def _header(meta: dict, hits: list[dict], status: dict | None) -> str:
    label = meta.get("instance") or meta.get("workspace") or "workspace"
    owner = meta.get("owner")
    head = f'<h1>Canary hits &middot; {_esc(label)} ({_esc(_status_text(status))})</h1>'
    if owner:
        head += f'<p class="owner muted">owner {_esc(owner)}</p>'
    return head + _headline(hits)


def participant_body(meta: dict, hits: list[dict], status: dict | None) -> str:
    """The participant page's body (spec *Participant page*): header (workspace, status), the
    headline counts, the literal-matching notice, then the loud hits newest first, each collapsed
    under <details>, then the quiet ones (and any of unknown kind) newest first inside one collapsed
    "also seen (N)" block (spec *Hits*), left out when there are none. `meta` is
    `workspace`/`instance`/`owner` (canary_watch.archive_meta's shape); `status` is None for an
    archived run."""
    ordered = sorted(hits, key=lambda h: str(h.get("at") or h.get("detected") or ""), reverse=True)
    loud = [h for h in ordered if h.get("kind") in LOUD_KINDS]
    quiet = [h for h in ordered if h.get("kind") not in LOUD_KINDS]
    items = "".join(_hit_html(h) for h in loud)
    if quiet:
        items += (f'<details class="also-seen"><summary>also seen ({len(quiet)})</summary>'
                  f'{"".join(_hit_html(h) for h in quiet)}</details>')
    if not items:
        items = '<p class="muted">No hits yet.</p>'
    return (
        '<main class="hits">'
        f'<header class="report-head card">{_header(meta, hits, status)}'
        f'<p class="notice muted">{_esc(NOTICE)}</p></header>'
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
