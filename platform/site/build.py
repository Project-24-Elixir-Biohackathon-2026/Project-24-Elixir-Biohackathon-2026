#!/usr/bin/env python3
"""Build the sperange site: the landing page and the threat catalog page.

Reads threats/TM-*.md and vocabulary.yaml through the repository's validate.py
(the build fails if the catalog does not validate) and writes:

  <out>/index.html          landing/index.html with static/site.css inlined
  <out>/threats/index.html  the catalog: a sortable, filterable table and
                            every entry rendered in full

The output directory is replaced atomically, so a web server pointed at it
never serves a half-written tree.

Usage:
    python3 build.py [--repo-root DIR] [--out DIR]

Dependencies: pyyaml, markdown (Ubuntu: python3-yaml python3-markdown).
"""

import argparse
import html
import re
import shutil
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[1]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Threats | sperange</title>
<meta name="description" content="The threat model catalog for AI agents in Secure Processing Environments, with the status of each threat.">
<style>
{{CSS}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="/">sperange</a>
    <nav>
      <a href="/workspaces">Workspaces</a>
      <a href="/threats/" aria-current="page">Threats</a>
    </nav>
  </header>

  <section class="page-title">
    <h1>Threat catalog</h1>
    <p>What the SPE instances are tested for. Click a column to sort, filter by
    status or entry point, or search. Each row links to the full entry below.</p>
  </section>

  <div class="controls">
    <label>Status
      <select id="f-status"><option value="">all</option>{{STATUS_OPTIONS}}</select>
    </label>
    <label>Entry point
      <select id="f-entry"><option value="">all</option>{{ENTRY_OPTIONS}}</select>
    </label>
    <label>Search
      <input id="f-search" type="search" placeholder="id, name, asset, text">
    </label>
    <span class="count" id="count"></span>
  </div>

  <div class="table-wrap">
    <table id="catalog">
      <thead>
        <tr>
          <th data-key="id" aria-sort="ascending">ID</th>
          <th data-key="name">Name</th>
          <th data-key="rank">Status</th>
          <th data-key="entry">Entry points</th>
          <th data-key="assets">Assets</th>
          <th data-key="stride">STRIDE</th>
        </tr>
      </thead>
      <tbody>
{{ROWS}}
      </tbody>
    </table>
  </div>

  <details class="legend">
    <summary>What the fields mean</summary>
{{LEGEND}}
  </details>

  <section id="entries">
{{ENTRIES}}
  </section>

  <footer>
    Generated from <code>threats/</code> at commit <code>{{COMMIT}}</code>.
    Source: <a href="https://github.com/kraatz/elixir-biohackathon-2026-test/tree/main/threats">kraatz/elixir-biohackathon-2026-test</a>
  </footer>
</div>
<script>
(function () {
  var tbody = document.querySelector('#catalog tbody');
  var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
  var fStatus = document.getElementById('f-status');
  var fEntry = document.getElementById('f-entry');
  var fSearch = document.getElementById('f-search');
  var count = document.getElementById('count');
  var sortKey = 'id', sortDir = 1;

  function apply() {
    var s = fStatus.value, e = fEntry.value, q = fSearch.value.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (!s || r.dataset.status === s)
        && (!e || r.dataset.entry.split(' ').indexOf(e) !== -1)
        && (!q || r.dataset.text.indexOf(q) !== -1);
      r.hidden = !ok;
      var art = document.getElementById(r.dataset.id);
      if (art) art.hidden = !ok;
      if (ok) shown++;
    });
    count.textContent = shown + ' of ' + rows.length + ' threats';
  }

  function sortBy(key) {
    if (key === sortKey) { sortDir = -sortDir; } else { sortKey = key; sortDir = 1; }
    rows.sort(function (a, b) {
      var x = a.dataset[key], y = b.dataset[key];
      if (key === 'rank') { x = +x; y = +y; }
      if (x < y) return -sortDir;
      if (x > y) return sortDir;
      return a.dataset.id < b.dataset.id ? -1 : 1;
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
    document.querySelectorAll('#catalog th').forEach(function (th) {
      th.setAttribute('aria-sort', th.dataset.key === sortKey ? (sortDir > 0 ? 'ascending' : 'descending') : 'none');
    });
  }

  document.querySelectorAll('#catalog th').forEach(function (th) {
    th.addEventListener('click', function () { sortBy(th.dataset.key); });
  });
  [fStatus, fEntry].forEach(function (el) { el.addEventListener('change', apply); });
  fSearch.addEventListener('input', apply);
  apply();
})();
</script>
</body>
</html>
"""


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def chips(values: list[str]) -> str:
    return '<span class="chips">' + "".join(
        f'<span class="chip">{esc(v)}</span>' for v in values
    ) + "</span>"


def status_badge(status: str) -> str:
    return f'<span class="status status-{esc(status)}">{esc(status)}</span>'


def render_body(body: str) -> str:
    """Drop the H1 (the page renders its own heading) and shift ##/### down one
    level so they nest under the entry's <h2>."""
    lines = []
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.startswith("# "):
            continue
        if re.match(r"^#{2,3} ", line):
            line = "#" + line
        lines.append(line)
    return markdown.markdown("\n".join(lines).strip())


def options(vocab_section: dict) -> str:
    return "".join(f'<option value="{esc(k)}">{esc(k)}</option>' for k in vocab_section)


def legend(vocab: dict) -> str:
    parts = []
    for section, title in (
        ("status", "Status"),
        ("entry-points", "Entry points"),
        ("assets", "Assets"),
        ("stride", "STRIDE"),
    ):
        parts.append(f"    <h3>{esc(title)}</h3>\n    <dl>")
        for key, desc in vocab[section].items():
            parts.append(f"      <dt>{esc(key)}</dt><dd>{esc(desc)}</dd>")
        parts.append("    </dl>")
    return "\n".join(parts)


def build_catalog(entries, vocab: dict, css: str, commit: str, repo_root: Path) -> str:
    status_rank = {k: i for i, k in enumerate(vocab["status"])}
    rows, articles = [], []
    for entry in entries:
        m = entry.meta
        eid, name = m["id"], m["name"]
        text = " ".join(
            " ".join(
                [eid, name, m["description"], m["status"], *m["entry-points"], *m["assets"], *m["stride"]]
            ).split()
        ).lower()
        rows.append(
            f'        <tr data-id="{esc(eid)}" data-name="{esc(name.lower())}" '
            f'data-status="{esc(m["status"])}" data-rank="{status_rank[m["status"]]}" '
            f'data-entry="{esc(" ".join(m["entry-points"]))}" '
            f'data-assets="{esc(" ".join(m["assets"]))}" '
            f'data-stride="{esc(" ".join(m["stride"]))}" '
            f'data-text="{esc(text)}">\n'
            f'          <td class="id"><a href="#{esc(eid)}">{esc(eid)}</a></td>\n'
            f'          <td><a href="#{esc(eid)}">{esc(name)}</a></td>\n'
            f'          <td>{status_badge(m["status"])}</td>\n'
            f'          <td>{chips(m["entry-points"])}</td>\n'
            f'          <td>{chips(m["assets"])}</td>\n'
            f'          <td>{chips(m["stride"])}</td>\n'
            f"        </tr>"
        )
        rel = entry.path.resolve().relative_to(repo_root.resolve()).as_posix()
        articles.append(
            f'    <article class="threat" id="{esc(eid)}" data-status="{esc(m["status"])}">\n'
            f'      <h2><span class="tm-id">{esc(eid)}</span>{esc(name)}</h2>\n'
            f'      <p class="meta">{status_badge(m["status"])}'
            f'<span class="sep">|</span>{chips(m["entry-points"])}'
            f'<span class="sep">|</span>{chips(m["assets"])}'
            f'<span class="sep">|</span>{chips(m["stride"])}</p>\n'
            f'      <p class="desc">{esc(" ".join(m["description"].split()))}</p>\n'
            f'      <div class="body">\n{render_body(entry.body)}\n      </div>\n'
            f'      <p class="source">Source: <a href="https://github.com/kraatz/elixir-biohackathon-2026-test/blob/main/{esc(rel)}"><code>{esc(rel)}</code></a></p>\n'
            f"    </article>"
        )
    return (
        PAGE.replace("{{CSS}}", css)
        .replace("{{STATUS_OPTIONS}}", options(vocab["status"]))
        .replace("{{ENTRY_OPTIONS}}", options(vocab["entry-points"]))
        .replace("{{ROWS}}", "\n".join(rows))
        .replace("{{LEGEND}}", legend(vocab))
        .replace("{{ENTRIES}}", "\n".join(articles))
        .replace("{{COMMIT}}", esc(commit))
    )


def git_commit(repo_root: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception:  # not a checkout, no git: the page still builds
        return "unknown"


def publish(staging: Path, out: Path) -> None:
    """Swap `staging` into place as `out` with at most a momentary gap."""
    old = out.with_name(out.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out.exists():
        out.rename(old)
    staging.rename(out)
    if old.exists():
        shutil.rmtree(old)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=HERE / "dist")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    sys.path.insert(0, str(repo_root))
    import validate  # the repository's validator

    vocab = validate.load_vocabulary(repo_root / "vocabulary.yaml")
    entries, problems = validate.validate_catalog(repo_root / "threats", vocab)
    if problems:
        for line in problems:
            print(f"FAIL {line}", file=sys.stderr)
        print("site not built: the catalog does not validate", file=sys.stderr)
        return 1

    css = (HERE / "static" / "site.css").read_text(encoding="utf-8")
    landing = (HERE / "landing" / "index.html").read_text(encoding="utf-8")
    if "<!-- site.css -->" not in landing:
        print("landing/index.html lacks the '<!-- site.css -->' marker", file=sys.stderr)
        return 1

    out = args.out.resolve()
    staging = out.with_name(out.name + ".tmp")
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "threats").mkdir(parents=True)
    (staging / "index.html").write_text(landing.replace("<!-- site.css -->", css), encoding="utf-8")
    (staging / "threats" / "index.html").write_text(
        build_catalog(entries, vocab, css, git_commit(repo_root), repo_root), encoding="utf-8"
    )
    publish(staging, out)
    print(f"built {out}: landing page and {len(entries)} threats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
