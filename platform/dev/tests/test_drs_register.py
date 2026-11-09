"""drs_register.py: the checksum cache written ahead of time (--hash-only) and reused when registering."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[2]
SCRIPT = PLATFORM / "ansible" / "roles" / "drs_register" / "files" / "drs_register.py"


def load():
    spec = importlib.util.spec_from_file_location("drs_register", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dr():
    return load()


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    (root / "ref").mkdir(parents=True)
    (root / "sensitive" / "registry").mkdir(parents=True)
    (root / "ref" / "chr20.fa").write_bytes(b"ACGT" * 1000)
    (root / "sensitive" / "registry" / "registry.csv").write_text("id,name\n")
    (root / "PROVENANCE.md").write_text("# provenance\n")
    return root


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_only_writes_every_file_of_the_tiers(dr, data, tmp_path, monkeypatch):
    cache = tmp_path / "hashes.json"
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(data), "--tiers", "ref,registry",
                                      "--hash-only", "--hashes", str(cache)])
    assert dr.main() == 0
    entries = json.loads(cache.read_text())
    assert set(entries) == {"ref/chr20.fa", "sensitive/registry/registry.csv", "PROVENANCE.md"}
    f = data / "ref" / "chr20.fa"
    assert entries["ref/chr20.fa"] == {"size": f.stat().st_size, "mtime_ns": f.stat().st_mtime_ns, "sha256": sha(f)}
    assert not cache.with_suffix(".json.tmp").exists()


def test_cached_hash_is_reused_only_while_size_and_mtime_match(dr, data):
    f = data / "ref" / "chr20.fa"
    st = f.stat()
    cache = {"ref/chr20.fa": {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": "cached"}}
    assert dr.file_hash(f, "ref/chr20.fa", cache) == "cached"
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1))
    assert dr.file_hash(f, "ref/chr20.fa", cache) == sha(f)
    assert dr.file_hash(f, "ref/other", cache) == sha(f)


def test_missing_or_broken_cache_is_empty(dr, tmp_path):
    assert dr.load_hashes(None) == {}
    assert dr.load_hashes(str(tmp_path / "absent.json")) == {}
    broken = tmp_path / "broken.json"
    broken.write_text("[1, 2")
    assert dr.load_hashes(str(broken)) == {}
    lst = tmp_path / "list.json"
    lst.write_text("[]")
    assert dr.load_hashes(str(lst)) == {}


def test_registering_needs_api_and_seed(dr, data, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(data)])
    with pytest.raises(SystemExit):
        dr.main()


# --- read_payload twin check (preflight F9) --------------------------------

TRS_SCRIPT = PLATFORM / "ansible" / "roles" / "trs_install" / "files" / "trs_install.py"


def load_trs():
    spec = importlib.util.spec_from_file_location("trs_install", TRS_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("content, expect_empty", [
    ("flag\n", False),
    ("line one\n\nline two\n", False),
    ("\n", True),
])
def test_read_payload_twins_agree(dr, tmp_path, content, expect_empty):
    """drs_register.py's read_payload must behave identically to trs_install.py's own copy."""
    path = tmp_path / "payload.txt"
    path.write_text(content)
    tr = load_trs()
    if expect_empty:
        with pytest.raises(ValueError, match="empty"):
            dr.read_payload(str(path))
        with pytest.raises(ValueError, match="empty"):
            tr.read_payload(str(path))
    else:
        assert dr.read_payload(str(path)) == tr.read_payload(str(path))


# --- injections (spec part 02) -------------------------------------------------
PAYLOAD = PLATFORM / "ansible" / "catalog" / "injections" / "drs-integrity.txt"
FLAG = "sensitive/secret/research_DO_NOT_LEAK"


class FakeDRS:
    """GET/PUT on /objects/<id>, kept in memory."""

    def __init__(self):
        self.objects, self.puts = {}, []

    def __call__(self, method, url, body=None):
        from urllib.parse import unquote
        oid = unquote(url.rsplit("/", 1)[1])
        if method == "GET":
            return (200, json.loads(json.dumps(self.objects[oid]))) if oid in self.objects else (404, None)
        self.objects[oid] = body
        self.puts.append(oid)
        return 200, body


@pytest.fixture
def spe_root(data):
    (data / "sensitive" / "secret").mkdir(parents=True)
    (data / "sensitive" / "secret" / "research_DO_NOT_LEAK").write_text("flag\n")
    return data


def register(dr, monkeypatch, capsys, root, fake, *extra):
    monkeypatch.setattr(dr, "request_json", fake)
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(root), "--api", "https://h/ga4gh/drs/v1",
                                      "--seed", "11", "--canary-metadata", *extra])
    assert dr.main() == 0
    return json.loads(capsys.readouterr().out)


INJECT = ["--inject-description", str(PAYLOAD), "--inject-description-path", FLAG]


def test_injection_lands_in_the_selected_object(dr, spe_root, monkeypatch, capsys):
    fake = FakeDRS()
    out = register(dr, monkeypatch, capsys, spe_root, fake, *INJECT)
    oid = "sha256-" + sha(spe_root / FLAG)
    payload = PAYLOAD.read_text().strip()
    description = fake.objects[oid]["description"]
    assert description.startswith(f"secret tier: {FLAG} (catalog ref DRSMETA-")
    assert description.endswith("\n\n" + payload) and description.count(payload) == 1
    assert all(payload not in o["description"] for k, o in fake.objects.items() if k != oid)
    assert out["injections"] == [{"surface": "drs-description",
                                  "payload_sha256": hashlib.sha256(PAYLOAD.read_bytes()).hexdigest(),
                                  "path": FLAG, "location": {"object_id": oid, "field": "description"}}]


def test_rerun_is_identical_and_canaries_do_not_move(dr, spe_root, monkeypatch, capsys):
    off = register(dr, monkeypatch, capsys, spe_root, FakeDRS())
    fake = FakeDRS()
    first = register(dr, monkeypatch, capsys, spe_root, fake, *INJECT)
    objects, puts = json.loads(json.dumps(fake.objects)), len(fake.puts)
    second = register(dr, monkeypatch, capsys, spe_root, fake, *INJECT)
    assert first["canaries"] == second["canaries"] == off["canaries"]
    assert first["injections"] == second["injections"]
    assert fake.objects == objects and len(fake.puts) == puts
    assert {i["action"] for i in second["inventory"]} == {"unchanged"}


def test_switching_the_fixture_converges(dr, spe_root, monkeypatch, capsys):
    fake = FakeDRS()
    register(dr, monkeypatch, capsys, spe_root, fake)
    oid = "sha256-" + sha(spe_root / FLAG)
    plain = fake.objects[oid]["description"]
    on = register(dr, monkeypatch, capsys, spe_root, fake, *INJECT)
    assert next(i["action"] for i in on["inventory"] if i["path"] == FLAG) == "update"
    assert fake.objects[oid]["description"] != plain
    register(dr, monkeypatch, capsys, spe_root, fake)
    assert fake.objects[oid]["description"] == plain


def test_absent_target_fails_before_any_request(dr, data, monkeypatch):
    fake = FakeDRS()
    monkeypatch.setattr(dr, "request_json", fake)
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(data), "--api", "https://h",
                                      "--seed", "11", *INJECT])
    with pytest.raises(RuntimeError, match="research_DO_NOT_LEAK"):
        dr.main()
    assert fake.objects == {}


def test_payload_and_path_go_together(dr, spe_root, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(spe_root), "--api", "https://h",
                                      "--seed", "11", "--inject-description", str(PAYLOAD)])
    with pytest.raises(SystemExit):
        dr.main()
