"""MkDocs hooks for the threat catalog.

- on_config: point docs_dir at the repository's threats/ (SPE_REPO_ROOT, or
  this repository) and build the navigation: Overview, Interactive table, Threats,
  Metadata (one page per frontmatter field).
- on_files: validate the catalog with validate.py (a problem stops the
  build), then add the pages that are not entries from pages/ (the overview
  as written; the table of all threats and the value table of each metadata
  page appended to the text written there), the table's script and
  stylesheet from assets/, and the images from assets/images/.
- on_page_markdown: show an entry's frontmatter on its page: the description
  under the heading, then status, entry points, assets and STRIDE, each value
  linked to its explanation; and a link to the entry's source file at the end.
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

PAGES = HERE / "pages"  # the hand-written pages that are not entries

# The metadata pages: one per frontmatter field, each a vocabulary.yaml section.
FIELDS = ("status", "entry-points", "assets", "stride")


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
        {"Interactive table": "interactive-table.md"},
        {"Threats": [e.path.name for e in entries]},
        {"Metadata": [f"metadata/{field}.md" for field in FIELDS]},
    ]
    return config


def on_files(files, config):
    vocab, entries = _catalog()
    files.append(File.generated(config, "index.md", content=page("index.md")))
    files.append(File.generated(
        config, "interactive-table.md", content=page("interactive-table.md") + all_threats(entries)))
    for field in FIELDS:
        files.append(File.generated(
            config, f"metadata/{field}.md",
            content=page(f"metadata/{field}.md") + value_table(vocab[field])))
    for name in ("catalog.js", "catalog.css"):
        files.append(File.generated(
            config, f"assets/catalog/{name}", content=(HERE / "assets" / name).read_text(encoding="utf-8")))
    for image in sorted((HERE / "assets" / "images").glob("*")):
        files.append(File.generated(config, f"assets/images/{image.name}", content=image.read_bytes()))
    return files


def on_page_markdown(markdown, page, config, files):
    meta = page.meta
    if "id" not in meta:
        return markdown
    # Material shows a status icon in the navigation for any page whose meta
    # has a `status` key (its own page-status feature). Ours means something
    # else, so take it out of the page meta once read.
    meta = dict(meta)
    page.meta.pop("status", None)
    lines = markdown.split("\n")
    h1 = next(i for i, line in enumerate(lines) if line.strip())
    block = [
        "",
        " ".join(meta["description"].split()),
        "",
        "| Status | Entry points | Assets | STRIDE |",
        "|---|---|---|---|",
        f"| {linked('status', [meta['status']])} | {linked('entry-points', meta['entry-points'])} "
        f"| {linked('assets', meta['assets'])} | {linked('stride', meta['stride'])} |",
        "",
    ]
    source = (
        f"{config['repo_url']}/blob/main/threats/{page.file.src_uri}"
    )
    tail = ["", "---", "", f"Source: [`threats/{page.file.src_uri}`]({source})", ""]
    return "\n".join(lines[: h1 + 1] + block + lines[h1 + 1 :] + tail)


def codes(values) -> str:
    return " ".join(f"`{v}`" for v in values)


def linked(field: str, values) -> str:
    """Values as links to their explanation on the field's metadata page."""
    return " ".join(f"[`{v}`](metadata/{field}.md)" for v in values)


def link(entry) -> str:
    return f"[{entry.meta['id']}: {entry.meta['name']}]({entry.path.name})"


def page(name: str) -> str:
    """A hand-written page from pages/, ending in a blank line."""
    return (PAGES / name).read_text(encoding="utf-8").rstrip() + "\n\n"


def all_threats(entries) -> str:
    out = [
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


def value_table(values: dict) -> str:
    out = ["| Value | Meaning |", "|---|---|"]
    out += [f"| `{value}` | {meaning} |" for value, meaning in values.items()]
    out.append("")
    return "\n".join(out)
