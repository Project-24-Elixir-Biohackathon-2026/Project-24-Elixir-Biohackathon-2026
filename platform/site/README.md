# SPE Range site

The static pages served at the portal's domain next to Coder: the landing page
(`/`) with the two entrances, Workspaces and Threats, and the threat catalog
(`/threats/`) built from `threats/*.md` with
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/). Coder
keeps its own paths (`/workspaces`, `/login`, `/api`, …); Caddy serves these
two paths from the built directory and proxies everything else to Coder
(`platform/coder/deploy/Caddyfile.example`).

| Path | What |
|---|---|
| `build.py` | Validates the catalog with the repository's `validate.py`, writes the landing page, runs `mkdocs build` |
| `mkdocs.yml` | The catalog site: theme, navigation features, `docs_dir` is `threats/` itself |
| `hooks.py` | MkDocs hooks: validation, the generated Overview, All threats and Metadata pages, each entry's frontmatter shown on its page |
| `assets/catalog.js`, `assets/catalog.css` | Sorting and filtering of the All threats table, added to the site by `hooks.py` |
| `landing/index.html` | The landing page; `<!-- site.css -->` is replaced by the stylesheet at build time |
| `static/site.css` | The landing page's stylesheet |
| `dist/` | Build output, ignored by git: `index.html` and `threats/` |

```bash
sudo apt install -y python3-yaml mkdocs-material           # the only dependencies
python3 platform/site/build.py                              # writes platform/site/dist/
python3 platform/site/build.py --out /srv/sperange-site     # the portal VM's layout
python3 -m http.server -d platform/site/dist 8000           # look at it locally
(cd platform/site && python3 -m mkdocs serve)               # live preview of the catalog only
```

The catalog: an Overview that explains how to read an entry; All threats, one
table that sorts by any column and filters by text, status or entry point;
one page per entry with the navigation on the left and the entry's sections
on the right; and Metadata, one page per frontmatter field (status, entry
points, assets, STRIDE) with a table of its values and their meaning. The
entry's description and its field values appear under its heading,
taken from the frontmatter, each value linked to its explanation. `threats/`
stays data only: the pages that are not entries are generated at build time,
and `TEMPLATE.md` is excluded.

The build refuses to run when the catalog does not validate, or when MkDocs
reports a problem (`--strict`), and leaves the previous output in place. The
landing page is replaced with an atomic rename and the catalog directory is
swapped in whole.

On the portal VM, `platform/coder/deploy/sync-template.sh` rebuilds the site on
every run of the sync timer (every 5 minutes), after pulling `main`, into
`SPE_SITE_DIR` (`/srv/sperange-site`, owned by `ubuntu`: Caddy's user cannot
read under `/home/ubuntu`). A merged change to `threats/` is live within
minutes, like a merged testbed preset.

Tests: `platform/dev/tests/test_site_build.py` builds into a temporary
directory and checks that a broken catalog stops the build.
