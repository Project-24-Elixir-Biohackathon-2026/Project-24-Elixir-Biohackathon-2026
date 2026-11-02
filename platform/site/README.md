# sperange site

The static pages served at the portal's domain next to Coder: the landing page
(`/`) with the two entrances, Workspaces and Threats, and the threat catalog
(`/threats/`) rendered from `threats/*.md`. Coder keeps its own paths
(`/workspaces`, `/login`, `/api`, …); Caddy serves these two paths from the
built directory and proxies everything else to Coder
(`platform/coder/deploy/Caddyfile.example`).

| Path | What |
|---|---|
| `build.py` | Validates the catalog with the repository's `validate.py`, then writes `dist/` |
| `landing/index.html` | The landing page; `<!-- site.css -->` is replaced by the stylesheet at build time |
| `static/site.css` | One stylesheet for both pages, inlined so the pages are single files |
| `dist/` | Build output, ignored by git: `index.html` and `threats/index.html` |

```bash
sudo apt install -y python3-yaml python3-markdown     # the only dependencies
python3 platform/site/build.py                        # writes platform/site/dist/
python3 platform/site/build.py --out /srv/sperange-site
python3 -m http.server -d platform/site/dist 8000     # look at it locally
```

The build refuses to run when the catalog does not validate, and it replaces
`dist/` as a whole, so the web server never serves a half-written tree. The
catalog page is self-contained: sorting, the status and entry-point filters
and the search are a few lines of inline JavaScript, no framework.

On the portal VM, `platform/coder/deploy/sync-template.sh` rebuilds the site on
every run of the sync timer (every 5 minutes), after pulling `main`. A merged
change to `threats/` is live within minutes, like a merged testbed preset.

Tests: `platform/dev/tests/test_site_build.py` builds into a temporary
directory and checks that a broken catalog stops the build.
