"""build.py renders the landing page and every entry, and refuses a catalog
that does not validate."""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BUILD = REPO / "platform" / "site" / "build.py"


def build(repo_root: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD), "--repo-root", str(repo_root), "--out", str(out)],
        capture_output=True, text=True,
    )


def test_builds_landing_and_catalog(tmp_path):
    res = build(REPO, tmp_path / "dist")
    assert res.returncode == 0, res.stderr
    out = tmp_path / "dist"
    landing = (out / "index.html").read_text()
    assert 'href="/workspaces"' in landing and 'href="/threats/"' in landing
    assert "<!-- site.css -->" not in landing  # the stylesheet was inlined
    overview = (out / "threats" / "interactive-table" / "index.html").read_text()
    entries = sorted(p for p in (REPO / "threats").glob("TM-*.md"))
    assert entries, "no entries in threats/"
    for path in entries:
        tm = path.name[:6]
        page = out / "threats" / path.stem / "index.html"
        assert page.is_file(), page
        text = page.read_text()
        assert f"{tm}:" in text and "Attack Scenarios" in text
        assert "hypothesised" in text or "reproduced" in text or "mitigated" in text
        assert f'href="{path.stem}/"' in overview or f'href="../{path.stem}/"' in overview or path.stem in overview
    for field in ("status", "entry-points", "assets", "stride"):
        page = out / "threats" / "metadata" / field / "index.html"
        assert page.is_file(), page
    assert 'href="../metadata/status/"' in (out / "threats" / entries[0].stem / "index.html").read_text()
    status_page = (out / "threats" / "metadata" / "status" / "index.html").read_text()
    article = status_page[status_page.index("<article"):status_page.index("</article>")]
    assert "<table>" in article and "TM-001" not in article  # a value table, no entry links
    assert (out / "threats" / "assets" / "catalog" / "catalog.js").is_file()
    assert 'class="catalog-table"' in overview and "catalog/catalog.js" in overview
    assert not (out / "threats" / "TEMPLATE").exists()
    assert sorted(p.name for p in out.iterdir()) == ["index.html", "threats"]


def test_rebuild_replaces_output(tmp_path):
    out = tmp_path / "dist"
    assert build(REPO, out).returncode == 0
    (out / "stale.html").write_text("old")
    (out / "threats" / "stale.html").write_text("old")
    assert build(REPO, out).returncode == 0
    assert not (out / "stale.html").exists()
    assert not (out / "threats" / "stale.html").exists()
    assert sorted(p.name for p in out.iterdir()) == ["index.html", "threats"]


def test_invalid_catalog_stops_the_build(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(REPO / "threats", root / "threats")
    shutil.copy(REPO / "vocabulary.yaml", root / "vocabulary.yaml")
    shutil.copy(REPO / "validate.py", root / "validate.py")
    first = sorted((root / "threats").glob("TM-*.md"))[0]
    first.write_text(first.read_text().replace("status: hypothesised", "status: done", 1))
    res = build(root, tmp_path / "dist")
    assert res.returncode == 1
    assert "unknown status value 'done'" in res.stderr
    assert not (tmp_path / "dist").exists()
