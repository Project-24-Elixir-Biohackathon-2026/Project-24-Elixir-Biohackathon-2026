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
    GET  /reports/<id>/hits        the canary hit viewer's participant page (spec *Participant
                                    page*); 403 for anyone but the workspace's owner and Coder owners
    GET  /reports/<id>/hits.json   the same hits as JSON, ?after=<id> for only the new ones
    GET  /reports/<id>/hits/events the same hits live, as server-sent events (decision 6); resumes
                                    past Last-Event-ID (else ?after=<id>); ends after 30 minutes,
                                    503 past 200 open streams (ruling 7)
    GET  /reports/static/<file>    the page's CSS and script
    GET  /reports/healthz          200, no login

Login is Coder's: the browser's coder_session_token cookie is forwarded to
Coder's users/me endpoint and nowhere else. The report's owner (the sidecar's
username) and Coder owners may write; everyone logged in may read. The hits
routes are narrower (decision 10): only the workspace's owner and Coder owners.

Standard library plus python3-markdown. Environment: CODER_URL (default
http://127.0.0.1:7080), REPORTS_DIR (default /data-share/reports), HITS_DIR
(default /data-share/canary-hits, the canary hit viewer's watcher output), LISTEN
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canary_hits import HitsFile  # noqa: E402
from hits_view import LOUD, empty_text, hit_html, participant_body, status_line  # noqa: E402

PREFIX = "/reports"
COOKIE = "coder_session_token"
MAX_BYTES = 1_000_000
CACHE_SECONDS = 30
HITS_DIR = "/data-share/canary-hits"
# The event stream (ruling 7): one thread per open stream, so both its life and their number are bounded.
STREAM_SECONDS = 30 * 60  # then it ends; EventSource reconnects with Last-Event-ID
STREAM_MAX = 200  # open streams per server; past it, 503
STREAM_POLL = 0.5  # seconds between looks at the hits and status files (decision 6: a hit shown within 2 s)
STREAM_READ = 1 << 20  # bytes of the hits file read per look at most (a catch-up takes several)
STREAM_PING = 15  # seconds with nothing sent before a ": ping" comment (keeps proxies from closing it)
STREAM_WRITE_TIMEOUT = 30  # seconds a write may block (a client that stops reading); then the stream ends
STREAM_STATUS_REFRESH = 10  # seconds before an unchanged status is resent, so "watched N s ago" ages live
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
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

def page(title: str, body: str, user: dict | None, editor: bool = False, scripts: tuple[str, ...] = (),
         styles: tuple[str, ...] = ()) -> bytes:
    """`scripts` and `styles` are file names under `static/` (the hits page's `hits.js`,
    `hits.css`), linked absolute like the page's own (`{PREFIX}/static/<name>`); always with a
    `src`/`href`, never inline (the CSP forbids inline script)."""
    who = html.escape(user.get("username", "")) if user else ""
    extra = (f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/font-awesome.min.css\">"
             f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/easymde.min.css\">" if editor else "")
    extra += "".join(f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/{html.escape(name)}\">" for name in styles)
    tail_scripts = "".join(f"<script src=\"{PREFIX}/static/{html.escape(name)}\"></script>" for name in scripts)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>{extra}"
        f"<link rel=\"stylesheet\" href=\"{PREFIX}/static/report.css\"></head>"
        "<body><div class=\"wrap\"><header class=\"top\"><a class=\"brand\" href=\"/\">SPE Range</a>"
        f"<nav><a href=\"/workspaces\">Portal</a><a href=\"{PREFIX}/\">Reports</a>"
        f"<span class=\"who\">{who}</span></nav></header>{body}</div>"
        + (f"<script src=\"{PREFIX}/static/easymde.min.js\"></script>" if editor else "")
        + tail_scripts
        + f"<script src=\"{PREFIX}/static/report.js\"></script></body></html>"
    ).encode()


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
    hits_dir: str | None = None

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

    def can_see_hits(self, meta: dict | None, user: dict) -> bool:
        """Decision 10: the workspace's owner and Coder owners; a workspace with no report sidecar
        (`meta` None) is visible to admins only. `meta.get`: a sidecar with no `owner` means only
        admins, not a KeyError (500)."""
        return is_admin(user) or (meta is not None and user["username"] == meta.get("owner"))

    # ---- the canary hit viewer's pages (spec *Participant page*)

    def _hits_path(self, wid: str) -> str | None:
        return os.path.join(self.hits_dir, wid + ".jsonl") if self.hits_dir else None

    def _status_path(self, wid: str) -> str | None:
        return os.path.join(self.hits_dir, wid + ".status.json") if self.hits_dir else None

    def read_hits(self, wid: str, after: int = 0) -> list[dict]:
        path = self._hits_path(wid)
        return HitsFile(path).read(after=after) if path else []

    def read_status(self, wid: str) -> dict | None:
        """The watcher's status file (ruling 6), or None: no `hits_dir`, no file, or one that is
        not valid JSON or not an object (never raises on it: untrusted only in the sense that the
        watcher could be mid-write, never the participant's)."""
        path = self._status_path(wid)
        if not path:
            return None
        try:
            with open(path, encoding="utf-8") as f:
                status = json.load(f)
        except (OSError, ValueError):
            return None
        return status if isinstance(status, dict) else None

    def hits_page(self, wid: str, user: dict) -> None:
        if not UUID_RE.match(wid):
            return self.send(HTTPStatus.NOT_FOUND, message_page("Not found", "No such workspace.", user))
        meta = self.store.meta(wid)
        if not self.can_see_hits(meta, user):
            return self.send(HTTPStatus.FORBIDDEN, message_page(
                "Forbidden", "Only the workspace's owner and Coder owners can see its canary hits.", user))
        hits = self.read_hits(wid)
        status = self.read_status(wid)
        label = (meta or {}).get("workspace") or wid
        body_meta = meta if meta is not None else {"workspace": wid}
        body_status = status if status is not None else {}  # {}: "not watched yet", never "archived run"
        last = hits[-1]["id"] if hits else 0
        content = (f'<section id="hits" data-wid="{html.escape(wid)}" data-last="{last}">'
                   f'{participant_body(body_meta, hits, body_status)}</section>')
        return self.send(HTTPStatus.OK, page(f"Canary hits · {label}", content, user,
                                             scripts=("hits.js",), styles=("hits.css",)))

    def hits_json(self, wid: str, user: dict) -> None:
        if not UUID_RE.match(wid):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        meta = self.store.meta(wid)
        if not self.can_see_hits(meta, user):
            return self.send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        after = 0
        if "after" in query:
            try:
                after = int(query["after"][-1])
            except ValueError:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": "after must be an integer"})
        return self.send_json(HTTPStatus.OK, {"workspace": wid, "status": self.read_status(wid),
                                              "hits": self.read_hits(wid, after)})

    def hits_events(self, wid: str, user: dict) -> None:
        """The event stream (spec *Participant page*; decision 6, ruling 7). Not sent through `send`: no
        Content-Length, and each event is written as it is found. Its timings and cap are the server's
        attributes (`make_server`), so tests can shorten them."""
        if not UUID_RE.match(wid):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        if not self.can_see_hits(self.store.meta(wid), user):
            return self.send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
        srv = self.server
        with srv.streams_lock:
            if srv.streams >= srv.stream_max:
                full = True
            else:
                full, srv.streams = False, srv.streams + 1
        if full:
            return self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "too many open streams"},
                                  {"Retry-After": "60"})
        try:
            self.close_connection = True
            # A client that stops reading would otherwise block wfile.write forever, past the 30-minute
            # bound and holding its stream slot; the timeout makes the TimeoutError catch below real.
            self.connection.settimeout(srv.stream_write_timeout)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.flush()
            if self.command != "HEAD":
                self._stream(wid, self._stream_start())
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            pass  # the viewer went away, or stopped reading
        finally:
            with srv.streams_lock:
                srv.streams -= 1

    def _stream_start(self) -> int:
        """Where the stream resumes: Last-Event-ID when it is an integer, else ?after=, else 0."""
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        for value in (self.headers.get("Last-Event-ID"), (query.get("after") or [None])[-1]):
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                continue
        return 0

    def _stream(self, wid: str, start: int) -> None:
        srv = self.server
        hits_path, status_path = self._hits_path(wid), self._status_path(wid)
        lines, offset = 0, 0  # complete lines passed so far, and the byte offset after them
        inode = None  # the hits file's, once seen: a file replaced or cut ends the stream
        caught_up = False  # `start` reached, or clamped to the file's end once the end was read
        in_long_line = False  # inside a line longer than one read, skipped (it still counts as a line)
        status_seen = None  # the status file's (mtime, inode) last sent; None: never sent
        status_sent = time.monotonic()  # when a status event was last sent; also refreshes it
        ends = time.monotonic() + srv.stream_seconds
        last_sent = time.monotonic()
        while time.monotonic() < ends:
            out = []
            data = b""
            if hits_path:
                try:
                    with open(hits_path, "rb") as f:
                        st = os.fstat(f.fileno())
                        if inode is not None and (st.st_ino != inode or st.st_size < offset):
                            return  # replaced or cut: the browser reconnects and is clamped afresh
                        inode = st.st_ino
                        f.seek(offset)
                        data = f.read(srv.stream_read)
                except FileNotFoundError:
                    if inode is not None:
                        return  # removed after it was read
                    caught_up = True  # no hits yet: nothing to skip, the first hit is id 1
                except OSError as e:  # the class only: no path but the workspace id, no content
                    sys.stdout.write(f"hits stream {wid}: {type(e).__name__}, ended\n")
                    sys.stdout.flush()
                    return
            at_end = len(data) < srv.stream_read
            if in_long_line:
                nl = data.find(b"\n")
                offset += len(data) if nl < 0 else nl + 1
                if nl >= 0:
                    lines, in_long_line = lines + 1, False
                data = b"" if nl < 0 else data[nl + 1:]
            # Only complete lines: a line still being written is read again on the next look.
            complete = data[:data.rfind(b"\n") + 1]
            if not complete and len(data) >= srv.stream_read:  # a whole read and no line end: too long
                offset, in_long_line = offset + len(data), True
            for raw in complete.split(b"\n")[:-1]:
                lines += 1
                offset += len(raw) + 1
                if lines <= start and not caught_up:
                    continue
                event = self._hit_event(lines, raw)
                if event:
                    out.append(event)
            if at_end:
                caught_up = True  # a start past the end is clamped to it: nothing replayed, no error
            if status_path:
                try:
                    st = os.stat(status_path)
                    stamp = (st.st_mtime_ns, st.st_ino)
                except OSError:
                    stamp = None
                now_mono = time.monotonic()
                # Resent on change, or unchanged past stream_status_refresh: "watched N s ago"
                # would otherwise freeze once the watcher stops touching the status file.
                if stamp is not None and (stamp != status_seen or now_mono - status_sent >= srv.stream_status_refresh):
                    status_seen, status_sent = stamp, now_mono
                    status = self.read_status(wid) or {}
                    line = status_line(status, time.time())
                    out.append("event: status\ndata: " + json.dumps({"line": line, "empty": empty_text(status)}) + "\n\n")
            if not out and time.monotonic() - last_sent >= srv.stream_ping:
                out.append(": ping\n\n")
            if out:
                self.wfile.write("".join(out).encode())
                self.wfile.flush()
                last_sent = time.monotonic()
            time.sleep(srv.stream_poll)

    @staticmethod
    def _hit_event(n: int, raw: bytes) -> str | None:
        """Line `n` of the hits file as an event, its id the line number (the hit's id); None for a line
        that does not parse (a crash's partial line), which still counts as a line."""
        try:
            hit = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return None
        if not isinstance(hit, dict):
            return None
        canary = hit.get("canary") if isinstance(hit.get("canary"), dict) else {}
        kind = hit.get("kind")
        data = {"id": n, "kind": kind, "loud": kind in LOUD, "type": canary.get("type"),
                "frontend": hit.get("frontend"), "html": hit_html(hit)}
        return f"id: {n}\nevent: hit\ndata: {json.dumps(data)}\n\n"

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
            if rest.endswith(".md") or rest.endswith("/hits.json") or rest.endswith("/hits/events"):
                return self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "not logged in"})
            return self.login_redirect(path)  # the page asked for, the hits page included
        if rest == "":
            return self.send(HTTPStatus.OK, list_page(self.store.listing(), user))
        if rest.endswith("/hits/events"):
            return self.hits_events(rest[:-len("/hits/events")], user)
        if rest.endswith("/hits.json"):
            return self.hits_json(rest[:-len("/hits.json")], user)
        if rest.endswith("/hits"):
            return self.hits_page(rest[:-len("/hits")], user)
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


def make_server(listen: str, reports_dir: str, coder_url: str, hits_dir: str | None = None) -> ThreadingHTTPServer:
    host, _, port = listen.rpartition(":")
    handler = type("BoundHandler", (Handler,), {"store": Store(reports_dir), "coder": Coder(coder_url),
                                                 "hits_dir": hits_dir})
    srv = ThreadingHTTPServer((host or "127.0.0.1", int(port)), handler)
    srv.daemon_threads = True
    srv.streams, srv.streams_lock = 0, threading.Lock()  # open event streams (ruling 7)
    srv.stream_max, srv.stream_seconds = STREAM_MAX, STREAM_SECONDS
    srv.stream_poll, srv.stream_ping, srv.stream_read = STREAM_POLL, STREAM_PING, STREAM_READ
    srv.stream_write_timeout = STREAM_WRITE_TIMEOUT
    srv.stream_status_refresh = STREAM_STATUS_REFRESH
    return srv


def main():
    listen = os.environ.get("LISTEN", "127.0.0.1:7090")
    reports_dir = os.environ.get("REPORTS_DIR", "/data-share/reports")
    hits_dir = os.environ.get("HITS_DIR", HITS_DIR)
    coder_url = os.environ.get("CODER_URL", "http://127.0.0.1:7080")
    if not os.path.isdir(reports_dir):
        sys.exit(f"sperange-report: REPORTS_DIR {reports_dir} is not a directory")
    srv = make_server(listen, reports_dir, coder_url, hits_dir)
    print(f"sperange-report: {reports_dir} on {listen}, Coder at {coder_url}, hits in {hits_dir}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
