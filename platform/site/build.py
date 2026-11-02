#!/usr/bin/env python3
"""Build the SPE Range site: the landing page and the threat catalog.

  <out>/index.html   landing/index.html with static/site.css inlined
  <out>/threats/     the catalog, Material for MkDocs (mkdocs.yml, hooks.py)
                     built from the repository's threats/ and vocabulary.yaml

The catalog is validated with validate.py first; a problem stops the build
with the problems listed and leaves the previous output in place. The landing
page is replaced with an atomic rename and the catalog directory is swapped in
whole, so a web server pointed at <out> never serves a half-written page.

Usage:
    python3 build.py [--repo-root DIR] [--out DIR]

Dependencies: pyyaml, mkdocs-material (Ubuntu: python3-yaml mkdocs-material).
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=HERE / "dist")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    out = args.out.resolve()

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

    out.mkdir(parents=True, exist_ok=True)
    staging = out / ".threats-staging"
    if staging.exists():
        shutil.rmtree(staging)
    env = {**os.environ, "SPE_REPO_ROOT": str(repo_root)}
    res = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--quiet",
         "-f", str(HERE / "mkdocs.yml"), "-d", str(staging)],
        env=env, cwd=str(HERE),
    )
    if res.returncode != 0:
        print("site not built: mkdocs failed", file=sys.stderr)
        shutil.rmtree(staging, ignore_errors=True)
        return 1

    tmp = out / ".index.html.tmp"
    tmp.write_text(landing.replace("<!-- site.css -->", css), encoding="utf-8")
    tmp.replace(out / "index.html")
    old = out / ".threats-old"
    if old.exists():
        shutil.rmtree(old)
    if (out / "threats").exists():
        (out / "threats").rename(old)
    staging.rename(out / "threats")
    shutil.rmtree(old, ignore_errors=True)
    for path in out.iterdir():  # files of earlier layouts
        if path.name not in ("index.html", "threats"):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    print(f"built {out}: landing page and {len(entries)} threats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
