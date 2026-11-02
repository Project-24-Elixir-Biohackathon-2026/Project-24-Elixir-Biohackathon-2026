"""MkDocs hooks for the threat catalog.

- on_config: point docs_dir at the repository's threats/ (SPE_REPO_ROOT, or
  this repository) and build the navigation: Overview, All threats, Threats,
  Metadata (one page per frontmatter field).
- on_files: validate the catalog with validate.py (a problem stops the
  build), then generate the pages that are not entries (overview, the table
  of all threats, the metadata pages) and add the table's script and
  stylesheet from assets/.
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

# The metadata pages: field -> (page title, vocabulary section, what the field is for)
FIELDS = (
    ("status", "Status", "status",
     "How far the threat has been shown on an SPE instance. A status beyond "
     "`hypothesised` must be backed by a promptfoo test in "
     "`platform/promptfoo-evals/` or an archived run."),
    ("entry-points", "Entry points", "entry-points",
     "Through which channel the threat reaches the agent: where the triggering "
     "content or instruction comes from."),
    ("assets", "Assets", "assets",
     "What is at stake: the things the agent can read, change or spend that "
     "the threat puts at risk."),
    ("stride", "STRIDE", "stride",
     "The STRIDE categories the threat falls into, a fixed external standard "
     "(the property each category violates is given in brackets)."),
)


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
        {"All threats": "all-threats.md"},
        {"Threats": [e.path.name for e in entries]},
        {"Metadata": [{title: f"metadata/{field}.md"} for field, title, _, _ in FIELDS]},
    ]
    return config


def on_files(files, config):
    vocab, entries = _catalog()
    files.append(File.generated(config, "index.md", content=overview()))
    files.append(File.generated(config, "all-threats.md", content=all_threats(entries)))
    for field, title, section, intro in FIELDS:
        files.append(File.generated(
            config, f"metadata/{field}.md",
            content=metadata_page(field, title, intro, vocab[section])))
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


def overview() -> str:
    return "\n".join([
        "# Threat catalog",
        "",
        "What the SPE instances are tested for: each threat an AI agent poses, or",
        "is exposed to, inside a Secure Processing Environment, written against the",
        "stack the instances run.",
        "",
        "- [All threats](all-threats.md): one table, sortable and filterable.",
        "- **Threats**: one page per entry, in the navigation.",
        "- **Metadata**: what each field of an entry means and every value it can",
        "  take, with the entries that use it.",
        "",
        "## How to read an entry",
        "",
        "Every entry has the same shape. Under its heading: the description, then",
        "its [status](metadata/status.md), [entry points](metadata/entry-points.md),",
        "[assets](metadata/assets.md) and [STRIDE](metadata/stride.md) categories.",
        "Then three sections:",
        "",
        "- **Attack Scenarios**: who or what triggers the threat, through which entry",
        "  point, and what the agent then does, with the real commands, endpoints and",
        "  files of the stack.",
        "- **Preconditions**: what must be true of the agent, its access or its",
        "  environment for the scenarios to work.",
        "- **Mitigations**: preventive (stop it), detective (notice it) and",
        "  responsive (what to do once detected).",
        "",
        "The entries are Markdown files with a YAML header in the repository's",
        "`threats/` directory; a validator holds every entry to the template and to",
        "the controlled values. Each page links to its source file at the end.",
        "",
    ])


def all_threats(entries) -> str:
    out = [
        "# All threats",
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


def metadata_page(field, title, intro, values) -> str:
    out = [f"# {title}", "", intro, "", f"Field `{field}` in an entry's header; the values come from",
           "`vocabulary.yaml` in the repository and the validator rejects any other.", "",
           "| Value | Meaning |", "|---|---|"]
    out += [f"| `{value}` | {meaning} |" for value, meaning in values.items()]
    out.append("")
    return "\n".join(out)
