# The site

The static pages at the portal's domain: the landing page (`/`) with the two
entrances, Workspaces and Threats, and the threat catalog (`/threats/`) built from
`threats/*.md` with Material for MkDocs. Caddy serves both from the built directory
and proxies everything else to Coder.

```bash
sudo apt install -y python3-yaml mkdocs-material           # the only dependencies
python3 platform/site/build.py                              # writes platform/site/dist/
python3 platform/site/build.py --out /srv/sperange-site     # the portal VM's layout
python3 -m http.server -d platform/site/dist 8000           # look at it locally
(cd platform/site && python3 -m mkdocs serve)               # live preview of the catalog only
```

| Path | What |
|---|---|
| `build.py` | Validates the catalog with `validate.py`, writes the landing page, runs `mkdocs build --strict`; refuses to run on a broken catalog and keeps the previous output |
| `mkdocs.yml`, `hooks.py` | The catalog site; `docs_dir` is `threats/` itself. The hooks add the generated tables and each entry's metadata |
| `pages/` | The hand-written pages: Overview, Interactive table, one page per metadata field. Edit freely |
| `assets/` | Sorting and filtering of the table, images |
| `landing/index.html`, `static/site.css` | The landing page |
| `dist/` | Build output, ignored by git |

The catalog has an Overview, an Interactive table that sorts and filters by text,
status or entry point, one page per entry, and one page per metadata field with
its values and their meaning. `threats/` stays data: `TEMPLATE.md` is excluded, the
other pages come from `pages/`.

On the portal VM the sync timer rebuilds the site every 5 minutes after pulling
`main`, so a merged change to `threats/` is live within minutes.
`platform/dev/tests/test_site_build.py` tests the build.
