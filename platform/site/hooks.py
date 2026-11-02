"""MkDocs hooks for the threat catalog.

- on_config: point docs_dir at the repository's threats/ (SPE_REPO_ROOT, or
  this repository) and build the navigation: Overview, Threats, Vocabulary.
- on_files: validate the catalog with validate.py (a problem stops the
  build), then generate the overview page and the vocabulary page, and add
  the catalog table's script and stylesheet from assets/.
- on_page_markdown: show an entry's frontmatter on its page: the description
  under the heading, then status, entry points, assets and STRIDE; and a link
  to the entry's source file at the end.
"""

import os
import sys
from pathlib import Path

from mkdocs.exceptions import PluginError
from mkdocs.structure.files import File

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("SPE_REPO_ROOT") or HERE.parents[1])
sys.path.insert(0, str(ROOT))
import validate  # noqa: E402  (the repository's validator)

_vocab = None
_entries = None


def _catalog():
    global _vocab, _entries
    if _entries is None:
        _vocab = validate.load_vocabulary(ROOT / "vocabulary.yaml")
        _entries, problems = validate.validate_catalog(ROOT / "threats", _vocab)
        if problems:
            raise PluginError("the catalog does not validate:\n" + "\n".join(problems))
    return _vocab, _entries


def on_config(config):
    config["docs_dir"] = str(ROOT / "threats")
    _, entries = _catalog()
    config["nav"] = [
        {"Overview": "index.md"},
        {"Threats": [e.path.name for e in entries]},
        {"Vocabulary": "vocabulary.md"},
    ]
    return config


def on_files(files, config):
    vocab, entries = _catalog()
    files.append(File.generated(config, "index.md", content=overview(vocab, entries)))
    files.append(File.generated(config, "vocabulary.md", content=vocabulary_page(vocab)))
    for name in ("catalog.js", "catalog.css"):
        files.append(File.generated(
            config, f"assets/catalog/{name}", content=(HERE / "assets" / name).read_text(encoding="utf-8")))
    return files


def on_page_markdown(markdown, page, config, files):
    meta = page.meta
    if "id" not in meta:
        return markdown
    lines = markdown.split("\n")
    h1 = next(i for i, line in enumerate(lines) if line.strip())
    block = [
        "",
        " ".join(meta["description"].split()),
        "",
        "| Status | Entry points | Assets | STRIDE |",
        "|---|---|---|---|",
        f"| {codes([meta['status']])} | {codes(meta['entry-points'])} "
        f"| {codes(meta['assets'])} | {codes(meta['stride'])} |",
        "",
    ]
    source = (
        f"{config['repo_url']}/blob/main/threats/{page.file.src_uri}"
    )
    tail = ["", "---", "", f"Source: [`threats/{page.file.src_uri}`]({source})", ""]
    return "\n".join(lines[: h1 + 1] + block + lines[h1 + 1 :] + tail)


def codes(values) -> str:
    return " ".join(f"`{v}`" for v in values)


def link(entry) -> str:
    return f"[{entry.meta['id']}: {entry.meta['name']}]({entry.path.name})"


def overview(vocab, entries) -> str:
    out = [
        "# Threat catalog",
        "",
        "What the SPE instances are tested for: each threat with its entry points,",
        "the assets at stake and the status of what has been shown on an instance.",
        "The [vocabulary](vocabulary.md) defines the terms.",
        "",
        "## By status",
        "",
    ]
    for status, meaning in vocab["status"].items():
        group = [e for e in entries if e.meta["status"] == status]
        out += [f"### {status} ({len(group)})", "", f"*{meaning}.*", ""]
        out += [f"- {link(e)}" for e in group] or ["- none yet"]
        out.append("")
    out += [
        "## All threats",
        "",
        "Click a column to sort; the controls filter the rows.",
        "",
        '<div class="catalog-table" markdown="block">',
        "",
        "| ID | Name | Status | Entry points | Assets | STRIDE |",
        "|---|---|---|---|---|---|",
    ]
    for e in entries:
        m = e.meta
        out.append(
            f"| [{m['id']}]({e.path.name}) | [{m['name']}]({e.path.name}) | `{m['status']}` "
            f"| {codes(m['entry-points'])} | {codes(m['assets'])} | {codes(m['stride'])} |"
        )
    out += ["", "</div>", ""]
    return "\n".join(out)


def vocabulary_page(vocab) -> str:
    out = [
        "# Vocabulary",
        "",
        "The controlled values an entry's frontmatter may use, from",
        "`vocabulary.yaml` in the repository. `validate.py` rejects anything else.",
        "",
    ]
    for section, title in (
        ("status", "Status"),
        ("entry-points", "Entry points"),
        ("assets", "Assets"),
        ("stride", "STRIDE"),
    ):
        out += [f"## {title}", "", "| Value | Meaning |", "|---|---|"]
        out += [f"| `{k}` | {v} |" for k, v in vocab[section].items()]
        out.append("")
    return "\n".join(out)
