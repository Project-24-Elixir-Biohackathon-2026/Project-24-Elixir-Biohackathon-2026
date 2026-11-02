"""build.py renders every entry and refuses a catalog that does not validate."""
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
    landing = (tmp_path / "dist" / "index.html").read_text()
    catalog = (tmp_path / "dist" / "threats" / "index.html").read_text()
    assert 'href="/workspaces"' in landing and 'href="/threats/"' in landing
    assert "<!-- site.css -->" not in landing  # the stylesheet was inlined
    ids = sorted(p.name[:6] for p in (REPO / "threats").glob("TM-*.md"))
    assert ids, "no entries in threats/"
    for tm in ids:
        assert f'id="{tm}"' in catalog, tm
        assert f'data-id="{tm}"' in catalog, tm
    assert "<h3>Attack Scenarios</h3>" in catalog  # body headings shifted under the entry's h2


def test_rebuild_replaces_output(tmp_path):
    out = tmp_path / "dist"
    assert build(REPO, out).returncode == 0
    (out / "stale.html").write_text("old")
    assert build(REPO, out).returncode == 0
    assert not (out / "stale.html").exists()
    assert not out.with_name("dist.tmp").exists() and not out.with_name("dist.old").exists()


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
