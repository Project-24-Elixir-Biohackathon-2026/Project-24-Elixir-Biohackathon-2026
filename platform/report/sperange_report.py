#!/usr/bin/env python3
"""The run report service of the sperange portal.

One Markdown report per workspace, kept on the portal VM (never on the SPE
instance), written by the participant in a browser page and read by every
portal user. Spec: docs/specs/2026-11-06-run-report-service.md.

Files, under REPORTS_DIR:
    <workspace id>.md     the report (created by playbooks/create.yml, role run_report)
    <workspace id>.json   the sidecar: owner, workspace, instance, created, parameters,
                          template_sha256 (the SHA-256 of the initial content)

Routes (Caddy sends /reports* here):
    GET  /reports/                 the list
    GET  /reports/<id>             the editor page (read-only unless the viewer may write)
    GET  /reports/<id>.md          the Markdown, ETag = sha256 of the file
    PUT  /reports/<id>.md          save; If-Match required; 412 when the file changed
    POST /reports/preview          Markdown in, sanitized HTML fragment out
    GET  /reports/static/<file>    the page's CSS and script
    GET  /reports/healthz          200, no login
    GET  /reports/runs             the runs browser (a page; its data comes from the API below)

The API, JSON unless noted, for the browser page and for scripts (the session token
goes in the coder_session_token cookie or in a Coder-Session-Token header; without
one the answer is 401, never a redirect). Everyone logged in may read all of it:
    GET  /reports/api/reports                                   the live reports (the list above as JSON)
    GET  /reports/api/runs                                      every archived run under RUNS_DIR, newest first
    GET  /reports/api/runs/<run>                                one run: parameters, report, chats of both frontends
    GET  /reports/api/runs/<run>/report.md                      the archived report, text/markdown
    GET  /reports/api/runs/<run>/chats/<frontend>/<chat>        one chat as turns (role, time, sanitized HTML)
    GET  /reports/api/runs/<run>/chats/<frontend>/<chat>.md     the chat's Markdown as archived
    GET  /reports/api/runs/<run>/chats/<frontend>/<chat>.json   the chat's export as archived
    GET  /reports/api/runs/<run>/agui/agent-runs.jsonl          the agent's run log (AG-UI runs)
    GET  /reports/api/runs/<run>/agui/journals/<session>.jsonl  one AG-UI session journal as stored
<run> is the archive directory's name (<UTC time>_<instance>), <frontend> is openwebui
or agui, <chat> the file stem (01-title). run.yml's participant e-mail is never served;
neither is canaries.json.

Login is Coder's: the browser's coder_session_token cookie is forwarded to
Coder's users/me endpoint and nowhere else. The report's owner (the sidecar's
username) and Coder owners may write; everyone logged in may read.

Standard library plus python3-markdown and python3-yaml. Environment: CODER_URL
(default http://127.0.0.1:7080), REPORTS_DIR (default /data-share/reports), RUNS_DIR
(default /data-share/runs, the archives written by playbooks/archive.yml), LISTEN
(default 127.0.0.1:7090).
"""
from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import markdown
import yaml

PREFIX = "/reports"
API = PREFIX + "/api/"
COOKIE = "coder_session_token"
TOKEN_HEADER = "Coder-Session-Token"
MAX_BYTES = 1_000_000
CACHE_SECONDS = 30
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# An archive directory (<UTC time>_<instance>), a chat file stem (01-title), a frontend's chats directory.
RUN_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z_[a-z0-9][a-z0-9._-]*$")
CHAT_RE = re.compile(r"^[0-9]+-[a-z0-9][a-z0-9-]*$")
FRONTEND_DIRS = {"openwebui": "chats", "agui": os.path.join("agui", "chats")}
RUNS_CACHE_SECONDS = 10
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2"}
# Scripts only from here, no inline script; inline styles are allowed because the editor
# (EasyMDE on CodeMirror 5) sets some, and a style cannot reach Coder's cookie.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; "
       "font-src 'self'; frame-ancestors 'none'; form-action 'self'")


# --- Markdown -----------------------------------------------------------------

ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "em", "strong", "code", "pre",
    "blockquote", "a", "table", "thead", "tbody", "tr", "th", "td", "del", "sup", "sub", "img", "details",
    "summary", "dl", "dt", "dd", "span", "div",
}
VOID_TAGS = {"br", "hr", "img"}
ALLOWED_ATTRS = {"a": {"href", "title"}, "img": {"src", "alt", "title"}, "th": {"align"}, "td": {"align"},
                 "ol": {"start"}, "code": {"class"}, "span": {"class"}, "div": {"class"}}
SAFE_SCHEMES = ("http://", "https://", "mailto:", "/", "#")


class Sanitizer(HTMLParser):
    """Keeps an allowlist of tags and attributes; every other tag is escaped and shown as text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.out.append(html.escape(self.get_starttag_text() or ""))
            return
        kept = []
        for name, value in attrs:
            if name not in ALLOWED_ATTRS.get(tag, set()):
                continue
            value = value or ""
            if name in ("href", "src") and not value.strip().lower().startswith(SAFE_SCHEMES):
                continue
            kept.append(f' {name}="{html.escape(value, quote=True)}"')
        self.out.append(f"<{tag}{''.join(kept)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")
        elif tag not in ALLOWED_TAGS:
            self.out.append(html.escape(f"</{tag}>"))

    def handle_data(self, data):
        self.out.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass


def render_markdown(text: str) -> str:
    """Markdown to an HTML fragment that cannot carry script: rendered, then reduced to the allowlist."""
    rendered = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    s = Sanitizer()
    s.feed(rendered)
    s.close()
    return "".join(s.out)


# --- storage ------------------------------------------------------------------

class Conflict(Exception):
    pass


class Store:
    def __init__(self, root: str):
        self.root = root
        self.lock = threading.Lock()

    def _md(self, wid):
        return os.path.join(self.root, wid + ".md")

    def _json(self, wid):
        return os.path.join(self.root, wid + ".json")

    def meta(self, wid: str) -> dict | None:
        try:
            with open(self._json(wid), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            return None
        return m if isinstance(m, dict) else None

    def read(self, wid: str) -> tuple[bytes, str] | None:
        try:
            with open(self._md(wid), "rb") as f:
                data = f.read()
        except OSError:
            return None
        return data, etag_of(data)

    def last_saved(self, wid: str) -> str:
        try:
            return iso(os.stat(self._md(wid)).st_mtime)
        except OSError:
            return ""

    def write(self, wid: str, data: bytes, if_match: str) -> str:
        with self.lock:
            current = self.read(wid)
            if current is None:
                raise FileNotFoundError(wid)
            if current[1] != if_match:
                raise Conflict(current[1])
            tmp = self._md(wid) + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, self._md(wid))
            # "last saved" is this host's clock, not the file server's (NFS would use its own).
            now = time.time()
            os.utime(self._md(wid), (now, now))
        return etag_of(data)

    def listing(self) -> list[dict]:
        rows = []
        try:
            names = os.listdir(self.root)
        except OSError:
            names = []
        for name in names:
            wid = name[:-5]
            if not name.endswith(".json") or not UUID_RE.match(wid):
                continue
            m = self.meta(wid)
            if m is None or not os.path.isfile(self._md(wid)):
                continue
            rows.append({**m, "workspace_id": wid, "last_saved": self.last_saved(wid)})
        rows.sort(key=lambda r: r.get("last_saved", ""), reverse=True)
        return rows


# --- the archived runs ---------------------------------------------------------
# playbooks/archive.yml writes one directory per stopped workspace under RUNS_DIR:
# run.yml (parameters), report.md/.json (the report as it was), chats/<nn>-<title>.json|.md
# (Open WebUI), agui/chats/... (AG-UI, rendered the same way), agui/agent-runs.jsonl and
# agui/agui-journals/<session>.jsonl (raw). Read-only here; a listing is cached briefly.

TURN_RE = re.compile(r"^## (?P<role>[^(·\n]+?)(?: \((?P<model>[^)]*)\))?(?: · (?P<rest>.*))?$")
HIDDEN_RUN_KEYS = ("participant_email", "owner_email")


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def public(d: dict) -> dict:
    """A run's or report's metadata without the fields that are not for other participants."""
    return {k: v for k, v in d.items() if k not in HIDDEN_RUN_KEYS}


def split_turns(md: str) -> tuple[dict, list[dict]]:
    """A chat as write_run.py renders it: a title, '- Key: value' facts, then one '## role · time'
    heading per turn (Open WebUI adds the model in parentheses; AG-UI has a few other '##' sections,
    'Compacted', 'Other branches', which become turns of their own kind)."""
    facts: dict[str, str] = {}
    turns: list[dict] = []
    current: dict | None = None
    body: list[str] = []
    in_fence = False

    def close():
        if current is not None:
            text = "\n".join(body).strip("\n")
            current["markdown"] = text
            current["html"] = render_markdown(text)
            turns.append(current)

    for line in md.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            close()
            m = TURN_RE.match(line)
            role = (m.group("role") if m else line[3:]).strip()
            current = {"role": role.lower() if role.lower() in ("user", "assistant", "system", "tool") else "section",
                       "label": role, "model": (m.group("model") or "") if m else "",
                       "at": (m.group("rest") or "") if m else ""}
            body = []
            continue
        if current is None:
            if stripped.startswith("- ") and ": " in stripped:
                k, _, v = stripped[2:].partition(": ")
                facts[k.strip()] = v.strip()
            continue
        body.append(line)
    close()
    return facts, turns


class Runs:
    def __init__(self, root: str):
        self.root = root
        self.lock = threading.Lock()
        self._listing: tuple[float, list[dict]] | None = None

    # ---- paths (every component validated by the caller's regexes; nothing else joins a path)
    def dir(self, rid: str) -> str:
        return os.path.join(self.root, rid)

    def chat_path(self, rid: str, frontend: str, chat: str, ext: str) -> str:
        return os.path.join(self.dir(rid), FRONTEND_DIRS[frontend], chat + ext)

    def exists(self, rid: str) -> bool:
        return bool(RUN_RE.match(rid)) and (os.path.isfile(os.path.join(self.dir(rid), "run.yml"))
                                             or os.path.isfile(os.path.join(self.dir(rid), "report.json")))

    # ---- metadata
    def params(self, rid: str) -> dict:
        try:
            with open(os.path.join(self.dir(rid), "run.yml"), encoding="utf-8") as f:
                y = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            y = None
        if not isinstance(y, dict):
            y = {}
            side = _read_json(os.path.join(self.dir(rid), "report.json"))
            if isinstance(side, dict):  # an older archive without run.yml: what the sidecar knows
                y = {"instance": side.get("instance"), "participant": side.get("owner"),
                     "coder_workspace": side.get("workspace"), **(side.get("parameters") or {})}
        return public(y)

    def report(self, rid: str) -> dict | None:
        md = _read_text(os.path.join(self.dir(rid), "report.md"))
        if md is None:
            return None
        side = _read_json(os.path.join(self.dir(rid), "report.json"))
        side = side if isinstance(side, dict) else {}
        template = side.get("template_sha256")
        filled = hashlib.sha256(md.encode("utf-8")).hexdigest() != template if template else None
        return {"markdown": md, "filled": filled, "workspace_id": side.get("workspace_id"),
                "created": side.get("created")}

    def chats(self, rid: str) -> list[dict]:
        rows = []
        for frontend, sub in FRONTEND_DIRS.items():
            d = os.path.join(self.dir(rid), sub)
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for name in names:
                stem, ext = os.path.splitext(name)
                if ext != ".json" or not CHAT_RE.match(stem) or not os.path.isfile(os.path.join(d, stem + ".md")):
                    continue
                c = _read_json(os.path.join(d, name))
                c = c if isinstance(c, dict) else {}
                chat = c.get("chat") if isinstance(c.get("chat"), dict) else {}
                messages = chat.get("messages") if isinstance(chat.get("messages"), list) else []
                history = (chat.get("history") or {}).get("messages") if isinstance(chat.get("history"), dict) else None
                rows.append({
                    "frontend": frontend, "id": stem,
                    "title": str(c.get("title") or chat.get("title") or stem),
                    "created": when(c.get("created_at")), "updated": when(c.get("updated_at")),
                    "messages": len(history) if isinstance(history, dict) and history else len(messages),
                    "tags": [str(t.get("name") if isinstance(t, dict) else t) for t in (chat.get("tags") or [])
                             if t] if isinstance(chat.get("tags"), list) else [],
                    "archived": bool(c.get("archived")),
                })
        return rows

    def files(self, rid: str) -> dict:
        agui = os.path.join(self.dir(rid), "agui")
        journals = []
        try:
            journals = sorted(n[:-6] for n in os.listdir(os.path.join(agui, "agui-journals"))
                              if n.endswith(".jsonl") and UUID_RE.match(n[:-6]))
        except OSError:
            pass
        return {"agent_runs": os.path.isfile(os.path.join(agui, "agent-runs.jsonl")), "journals": journals}

    def summary(self, rid: str) -> dict:
        params = self.params(rid)
        chats = self.chats(rid)
        report = self.report(rid)
        counts = {f: sum(1 for c in chats if c["frontend"] == f) for f in FRONTEND_DIRS}
        return {
            "id": rid,
            "archived_at": str(params.get("archived_at") or rid.split("_", 1)[0]),
            "instance": str(params.get("instance") or rid.split("_", 1)[-1]),
            "participant": str(params.get("participant") or ""),
            "workspace": str(params.get("coder_workspace") or ""),
            "model": str(params.get("model") or ""),
            "flavor": str(params.get("flavor") or ""),
            "frontends": [str(f) for f in params.get("frontends") or []],
            "workflows": [str(w) for w in params.get("workflows") or []],
            "samples": [str(x) for x in params.get("samples") or []],
            "tiers": [str(x) for x in params.get("tiers") or []],
            "seed": params.get("seed"),
            "chats": counts,
            "report": None if report is None else {"filled": report["filled"], "workspace_id": report["workspace_id"]},
        }

    def listing(self) -> list[dict]:
        now = time.monotonic()
        with self.lock:
            if self._listing and self._listing[0] > now:
                return self._listing[1]
        try:
            names = os.listdir(self.root)
        except OSError:
            names = []
        rows = [self.summary(rid) for rid in sorted(names, reverse=True) if self.exists(rid)]
        with self.lock:
            self._listing = (now + RUNS_CACHE_SECONDS, rows)
        return rows

    def detail(self, rid: str) -> dict:
        d = self.summary(rid)
        d["parameters"] = self.params(rid)
        d["chat_list"] = self.chats(rid)
        report = self.report(rid)
        if report is not None:
            d["report"] = {**report, "html": render_markdown(report["markdown"])}
        d["files"] = self.files(rid)
        return d

    def chat(self, rid: str, frontend: str, chat: str) -> dict | None:
        md = _read_text(self.chat_path(rid, frontend, chat, ".md"))
        if md is None:
            return None
        facts, turns = split_turns(md)
        meta = next((c for c in self.chats(rid) if c["frontend"] == frontend and c["id"] == chat), None)
        title = md.split("\n", 1)[0].lstrip("# ").strip() if md.startswith("# ") else chat
        return {"run": rid, "frontend": frontend, "id": chat, "title": (meta or {}).get("title") or title,
                "meta": meta, "facts": facts, "turns": turns,
                "links": {"markdown": f"{API}runs/{rid}/chats/{frontend}/{chat}.md",
                          "json": f"{API}runs/{rid}/chats/{frontend}/{chat}.json"}}

    def raw(self, rid: str, relpath: str) -> bytes | None:
        """A file of the archive by a path the caller has already validated component by component."""
        try:
            with open(os.path.join(self.dir(rid), relpath), "rb") as f:
                return f.read()
        except OSError:
            return None


def when(t) -> str:
    """Epoch seconds or milliseconds (Open WebUI and AG-UI exports) to '2026-11-03 10:00 UTC'."""
    try:
        s = float(t)
    except (TypeError, ValueError):
        return str(t or "")
    if s > 1e11:
        s /= 1000
    try:
        return iso(s)
    except (OverflowError, OSError, ValueError):
        return str(t)


def etag_of(data: bytes) -> str:
    return '"' + hashlib.sha256(data).hexdigest() + '"'


def iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --- Coder --------------------------------------------------------------------

class Coder:
    """Coder's API as seen with the viewer's session token. Answers to users/me are cached briefly."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.cache: dict[str, tuple[float, dict | None]] = {}
        self.lock = threading.Lock()

    def _get(self, path: str, token: str):
        req = urllib.request.Request(self.url + path, headers={"Coder-Session-Token": token, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                return None
            raise

    def me(self, token: str) -> dict | None:
        now = time.monotonic()
        with self.lock:
            hit = self.cache.get(token)
            if hit and hit[0] > now:
                return hit[1]
        user = self._get("/api/v2/users/me", token)
        if user is not None and not isinstance(user, dict):
            user = None
        with self.lock:
            self.cache[token] = (now + CACHE_SECONDS, user)
            if len(self.cache) > 1000:
                self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
        return user

    def workspace_state(self, token: str, wid: str) -> str | None:
        try:
            ws = self._get(f"/api/v2/workspaces/{wid}", token)
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if not isinstance(ws, dict):
            return None
        build = ws.get("latest_build") or {}
        return str(build.get("status") or "") or None


def is_admin(user: dict) -> bool:
    return any(isinstance(r, dict) and r.get("name") == "owner" for r in user.get("roles") or [])


# --- pages --------------------------------------------------------------------
# The look follows the landing page (platform/site/static/site.css): the same tokens,
# top bar and cards. The editor is EasyMDE (vendored in static/, with Font Awesome 4
# for its toolbar); readers get the rendered report instead of an editor.

def page(title: str, body: str, user: dict | None, editor: bool = False, styles: tuple = (),
         scripts: tuple = ("report.js",)) -> bytes:
    who = html.escape(user.get("username", "")) if user else ""
    extra = (f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/font-awesome.min.css\">"
             f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/easymde.min.css\">" if editor else "")
    extra += "".join(f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/{name}\">" for name in styles)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>{extra}"
        f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/report.css\"></head>"
        "<body><div class=\"wrap\"><header class=\"top\"><a class=\"brand\" href=\"/\">SPE Range</a>"
        f"<nav><a href=\"/workspaces\">Portal</a><a href=\"/threats/\">Catalog</a>"
        f"<a href=\"{PREFIX}/runs\">Runs</a><a href=\"{PREFIX}/\">Reports</a>"
        f"<span class=\"who\">{who}</span></nav></header>{body}</div>"
        + (f"<script src=\"{PREFIX}/static/easymde.min.js\"></script>" if editor else "")
        + "".join(f"<script src=\"{PREFIX}/static/{name}\"></script>" for name in scripts)
        + "</body></html>"
    ).encode()


def runs_page(user: dict) -> bytes:
    """The runs browser: a shell the script fills from the API (list, one run, one chat; the view is in
    the URL's hash so every state has a link). Without script it says where the data is."""
    body = (f"<main class=\"runs\" id=\"runs\" data-api=\"{API}\" data-reports=\"{PREFIX}/\">"
            "<h1>Runs</h1><p class=\"lead\">Every archived run of the range and the live reports of the "
            "workspaces that exist now. Everyone logged in can read them.</p>"
            f"<noscript><p>This page needs JavaScript. The same data is at <a href=\"{API}runs\">{API}runs</a> "
            f"and <a href=\"{API}reports\">{API}reports</a> as JSON.</p></noscript>"
            "<div id=\"view\" class=\"view\" aria-live=\"polite\"><p class=\"muted\">Loading…</p></div></main>")
    return page("Runs", body, user, styles=("runs.css",), scripts=("runs.js",))


def list_page(rows: list[dict], user: dict) -> bytes:
    trs = []
    for r in rows:
        wid = r["workspace_id"]
        trs.append(
            f"<tr><td><a href=\"{PREFIX}/{wid}\">{html.escape(str(r.get('workspace') or wid))}</a></td>"
            f"<td>{html.escape(str(r.get('owner') or ''))}</td>"
            f"<td><code>{html.escape(str(r.get('instance') or ''))}</code></td>"
            f"<td>{html.escape(str(r.get('created') or ''))}</td>"
            f"<td>{html.escape(r.get('last_saved') or '')}</td></tr>"
        )
    table = ("<table><thead><tr><th>Workspace</th><th>Owner</th><th>Instance</th><th>Created</th>"
             "<th>Last saved</th></tr></thead><tbody>" + "".join(trs) + "</tbody></table>"
             if trs else "<p class=\"muted\">No report yet. A report is created with each workspace.</p>")
    body = ("<main class=\"list\"><h1>Run reports</h1><p class=\"lead\">One report per workspace, written by its "
            "owner while testing. Everyone logged in can read them.</p>"
            f"<section class=\"card\">{table}</section></main>")
    return page("Run reports", body, user)


def facts_html(wid: str, meta: dict, state: str | None) -> str:
    facts = [
        ("Workspace", str(meta.get("workspace") or wid)),
        ("Owner", str(meta.get("owner") or "")),
        ("Instance", str(meta.get("instance") or "")),
        ("Created", str(meta.get("created") or "")),
    ]
    if state:
        facts.append(("Workspace", f"{meta.get('workspace') or wid} ({state})"))
        facts.pop(0)
    return "".join(f"<div class=\"fact\"><span class=\"k\">{html.escape(k)}</span>"
                   f"<span class=\"v\">{html.escape(v)}</span></div>" for k, v in facts if v)


def editor_page(wid: str, meta: dict, user: dict, can_edit: bool, state: str | None, last_saved: str,
                content: bytes) -> bytes:
    head = (f"<header class=\"report-head card\"><div class=\"title\"><h1>Run report</h1>"
            f"<div class=\"facts\">{facts_html(wid, meta, state)}</div></div>")
    if can_edit:
        head += ("<div class=\"bar\"><span class=\"hint\">Saved as you type, readable by every portal user.</span>"
                 f"<span id=\"status\" data-last-saved=\"{html.escape(last_saved)}\"></span>"
                 "<button id=\"save\" type=\"button\">Save</button></div></header>")
        body = (f"<main class=\"editor\" data-id=\"{wid}\" data-can-edit=\"1\">{head}"
                "<section class=\"card editor-card\"><textarea id=\"source\"></textarea></section></main>")
    else:
        head += ("<div class=\"bar\"><span class=\"hint\">Read-only: only the owner and portal admins can edit."
                 f"{' Last saved ' + html.escape(last_saved) + '.' if last_saved else ''}</span>"
                 f"<a class=\"raw\" href=\"{PREFIX}/{wid}.md\">Markdown</a></div></header>")
        body = (f"<main class=\"editor\" data-id=\"{wid}\" data-can-edit=\"0\">{head}"
                f"<article class=\"card reading\">{render_markdown(content.decode('utf-8', 'replace'))}</article></main>")
    return page(f"Run report: {meta.get('workspace') or wid}", body, user, editor=can_edit)


def message_page(title: str, text: str, user: dict | None = None) -> bytes:
    return page(title, f"<main class=\"list\"><h1>{html.escape(title)}</h1><p>{html.escape(text)}</p></main>", user)


# --- the server ---------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "sperange-report/1"
    store: Store
    coder: Coder
    runs: Runs

    # ---- helpers
    def send(self, status: int, body: bytes = b"", ctype: str = "text/html; charset=utf-8", headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, obj: dict, headers: dict | None = None):
        self.send(status, json.dumps(obj).encode(), "application/json", headers)

    def token(self) -> str:
        header = self.headers.get(TOKEN_HEADER, "").strip()
        if header:
            return header
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # a malformed cookie header is no session
            return ""
        return c[COOKIE].value if COOKIE in c else ""

    def user(self) -> dict | None:
        """The viewer, or None. Raises on a Coder outage (answered as 502 by the caller)."""
        tok = self.token()
        return self.coder.me(tok) if tok else None

    def same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return urllib.parse.urlsplit(origin).netloc == host

    def route(self) -> tuple[str, str]:
        path = urllib.parse.urlsplit(self.path).path
        if path == PREFIX:
            path = PREFIX + "/"
        if not path.startswith(PREFIX + "/"):
            return "", ""
        return path, path[len(PREFIX) + 1:]

    def log_message(self, fmt, *args):  # no cookie, no query string
        sys.stdout.write("%s %s %s\n" % (self.address_string(), self.command, urllib.parse.urlsplit(self.path).path))
        sys.stdout.flush()

    def login_redirect(self, path: str):
        self.send(HTTPStatus.FOUND, b"", headers={"Location": "/login?redirect=" + urllib.parse.quote(path, safe="")})

    def can_edit(self, meta: dict, user: dict) -> bool:
        return user.get("username") == meta.get("owner") or is_admin(user)

    # ---- methods
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path, rest = self.route()
        if not path:
            return self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        if rest == "healthz":
            return self.send(HTTPStatus.OK, b"ok", "text/plain")
        if rest.startswith("static/"):
            return self.static(rest[len("static/"):])
        try:
            user = self.user()
        except (urllib.error.URLError, OSError, ValueError):
            return self.send(HTTPStatus.BAD_GATEWAY, message_page("Portal unavailable", "Coder did not answer; try again in a moment."))
        if user is None:
            if rest.endswith(".md") or rest.startswith("api/"):
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "not logged in"})
            return self.login_redirect(path)
        if rest == "":
            return self.send(HTTPStatus.OK, list_page(self.store.listing(), user))
        if rest == "runs":
            return self.send(HTTPStatus.OK, runs_page(user))
        if rest.startswith("api/"):
            return self.api(rest[len("api/"):])
        wid, is_md = (rest[:-3], True) if rest.endswith(".md") else (rest, False)
        if not UUID_RE.match(wid):
            return self.send(HTTPStatus.NOT_FOUND, message_page("Not found", "No such report.", user))
        meta = self.store.meta(wid)
        content = self.store.read(wid)
        if meta is None or content is None:
            return self.send(HTTPStatus.NOT_FOUND, message_page(
                "No report yet", "No report exists for this workspace. It is created when the workspace is first "
                "built; if the build is still running, come back in a minute.", user))
        if is_md:
            data, etag = content
            return self.send(HTTPStatus.OK, data, "text/markdown; charset=utf-8", {"ETag": etag})
        state = self.coder.workspace_state(self.token(), wid)
        return self.send(HTTPStatus.OK, editor_page(wid, meta, user, self.can_edit(meta, user), state,
                                                    self.store.last_saved(wid), content[0]))

    # ---- the API (the viewer is logged in; everything here is read-only)
    def api(self, rest: str):
        parts = rest.split("/")
        if parts == ["reports"]:
            return self.send_json(HTTPStatus.OK, {"reports": [public(r) for r in self.store.listing()]})
        if parts == ["runs"]:
            return self.send_json(HTTPStatus.OK, {"runs": self.runs.listing()})
        if len(parts) < 2 or parts[0] != "runs" or not self.runs.exists(parts[1]):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        rid, sub = parts[1], parts[2:]
        if not sub:
            return self.send_json(HTTPStatus.OK, self.runs.detail(rid))
        if sub == ["report.md"]:
            data = self.runs.raw(rid, "report.md")
            return self.send_bytes(data, "text/markdown; charset=utf-8")
        if len(sub) == 3 and sub[0] == "chats" and sub[1] in FRONTEND_DIRS:
            chat, ext = os.path.splitext(sub[2]) if sub[2].endswith((".md", ".json")) else (sub[2], "")
            if not CHAT_RE.match(chat):
                return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            if ext:
                data = self.runs.raw(rid, os.path.join(FRONTEND_DIRS[sub[1]], chat + ext))
                return self.send_bytes(data, "text/markdown; charset=utf-8" if ext == ".md" else "application/json")
            c = self.runs.chat(rid, sub[1], chat)
            if c is None:
                return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return self.send_json(HTTPStatus.OK, c)
        if sub == ["agui", "agent-runs.jsonl"]:
            return self.send_bytes(self.runs.raw(rid, os.path.join("agui", "agent-runs.jsonl")), "application/x-ndjson")
        if len(sub) == 3 and sub[:2] == ["agui", "journals"] and sub[2].endswith(".jsonl") and UUID_RE.match(sub[2][:-6]):
            return self.send_bytes(self.runs.raw(rid, os.path.join("agui", "agui-journals", sub[2])), "application/x-ndjson")
        return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def send_bytes(self, data: bytes | None, ctype: str):
        if data is None:
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        return self.send(HTTPStatus.OK, data, ctype)

    def do_PUT(self):
        path, rest = self.route()
        if not path or not rest.endswith(".md") or not UUID_RE.match(rest[:-3]):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        wid = rest[:-3]
        if not self.same_origin():
            return self.send_json(HTTPStatus.FORBIDDEN, {"error": "cross-origin request"})
        try:
            user = self.user()
        except (urllib.error.URLError, OSError, ValueError):
            return self.send_json(HTTPStatus.BAD_GATEWAY, {"error": "Coder did not answer"})
        if user is None:
            return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "not logged in"})
        meta = self.store.meta(wid)
        if meta is None:
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "no report for this workspace"})
        if not self.can_edit(meta, user):
            return self.send_json(HTTPStatus.FORBIDDEN, {"error": "only the owner and portal admins can edit this report"})
        if_match = self.headers.get("If-Match", "")
        if not if_match:
            return self.send_json(HTTPStatus.PRECONDITION_REQUIRED, {"error": "If-Match required"})
        data = self.body(MAX_BYTES)
        if data is None:
            return self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"the report must stay under {MAX_BYTES // 1000} kB"})
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return self.send_json(HTTPStatus.BAD_REQUEST, {"error": "the report must be UTF-8 text"})
        try:
            etag = self.store.write(wid, data, if_match)
        except Conflict as c:
            return self.send_json(HTTPStatus.PRECONDITION_FAILED,
                                  {"error": "the report changed elsewhere; reload the page", "etag": c.args[0]})
        except FileNotFoundError:
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "no report for this workspace"})
        return self.send_json(HTTPStatus.OK, {"etag": etag, "saved": self.store.last_saved(wid)}, {"ETag": etag})

    def do_POST(self):
        path, rest = self.route()
        if not path or rest != "preview":
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        if not self.same_origin():
            return self.send_json(HTTPStatus.FORBIDDEN, {"error": "cross-origin request"})
        try:
            user = self.user()
        except (urllib.error.URLError, OSError, ValueError):
            return self.send_json(HTTPStatus.BAD_GATEWAY, {"error": "Coder did not answer"})
        if user is None:
            return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "not logged in"})
        data = self.body(MAX_BYTES)
        if data is None:
            return self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too large"})
        text = data.decode("utf-8", errors="replace")
        return self.send(HTTPStatus.OK, render_markdown(text).encode(), "text/html; charset=utf-8")

    def body(self, limit: int) -> bytes | None:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if n > limit:
            # Drain a bounded amount so the client gets the answer instead of a reset
            # mid-upload; past that, the connection is closed after the reply.
            left = min(n, 8 * limit)
            while left > 0:
                chunk = self.rfile.read(min(left, 65536))
                if not chunk:
                    break
                left -= len(chunk)
            self.close_connection = True
            return None
        return self.rfile.read(n)

    def static(self, name: str):
        ext = os.path.splitext(name)[1]
        if "/" in name or name.startswith(".") or ext not in STATIC_TYPES:
            return self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        try:
            with open(os.path.join(STATIC_DIR, name), "rb") as f:
                data = f.read()
        except OSError:
            return self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        self.send(HTTPStatus.OK, data, STATIC_TYPES[ext], {"Cache-Control": "public, max-age=300"})


def make_server(listen: str, reports_dir: str, coder_url: str, runs_dir: str | None = None) -> ThreadingHTTPServer:
    host, _, port = listen.rpartition(":")
    handler = type("BoundHandler", (Handler,), {"store": Store(reports_dir), "coder": Coder(coder_url),
                                                "runs": Runs(runs_dir or os.path.join(os.path.dirname(reports_dir.rstrip("/")), "runs"))})
    srv = ThreadingHTTPServer((host or "127.0.0.1", int(port)), handler)
    srv.daemon_threads = True
    return srv


def main():
    listen = os.environ.get("LISTEN", "127.0.0.1:7090")
    reports_dir = os.environ.get("REPORTS_DIR", "/data-share/reports")
    coder_url = os.environ.get("CODER_URL", "http://127.0.0.1:7080")
    runs_dir = os.environ.get("RUNS_DIR", "/data-share/runs")
    if not os.path.isdir(reports_dir):
        sys.exit(f"sperange-report: REPORTS_DIR {reports_dir} is not a directory")
    if not os.path.isdir(runs_dir):  # the runs browser is then empty, the reports still work
        print(f"sperange-report: RUNS_DIR {runs_dir} is not a directory; no archived runs to show", flush=True)
    srv = make_server(listen, reports_dir, coder_url, runs_dir)
    print(f"sperange-report: {reports_dir} and {runs_dir} on {listen}, Coder at {coder_url}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
