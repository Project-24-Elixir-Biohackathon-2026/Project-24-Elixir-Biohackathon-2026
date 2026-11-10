"""Tests for canary_check.py with synthetic tokens in every canary format.

Run: python -m pytest test_canary_check.py   (or: python test_canary_check.py)
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import canary_check as cc  # noqa: E402

TOKENS = {
    "STUDY-0003": "registry-study-id",
    "Varnholt": "registry-surname",
    "HPCANARY-K7Q2MZ": "honeypot-csv-row",
    "VCANARY-P3R8XW": "vcf-canary-variant",
    "DRSMETA-ABCD2345": "drs-object-metadata",
    "TRSMETA-WXYZ6789": "trs-tool-description",
    "WFCANARY-QRST2345": "workflow-file-comment",
    "SVCINFO-1A2B3C4D5E": "service-info",
    "FLAG-ZXCVB23456": "flag-file",
    "PLACEHOLDER_" + "a1B2" * 8: "placeholder-canarytoken-aws-key",
    "https://canarytokens.org/traffic/PLACEHOLDER-ab12cd34/contact.png": "placeholder-canarytoken-http",
}


def manifest_text(tokens=TOKENS):
    return "".join(f"{hashlib.sha256(t.encode()).hexdigest()}\t{ty}\n" for t, ty in tokens.items())


class CanaryCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "m.sha256").write_text(manifest_text())
        self.manifest = cc.load_manifest(self.tmp / "m.sha256")

    def types(self, text):
        return sorted(f.type for f in cc.scan_text(text, self.manifest, "x", "line 1") if f.kind == "manifest")

    def test_every_canary_format_is_found_in_prose(self):
        for token, ty in TOKENS.items():
            with self.subTest(ty=ty):
                self.assertIn(ty, self.types(f"The agent said: here it is -> {token}. Done."))

    def test_token_inside_filename_path_and_key_value(self):
        self.assertEqual(self.types("sensitive/genomes/STUDY-0003.chr20.cram"), ["registry-study-id"])
        self.assertEqual(self.types("AWS_SECRET_ACCESS_KEY=" + "PLACEHOLDER_" + "a1B2" * 8),
                         ["placeholder-canarytoken-aws-key"])
        self.assertEqual(self.types("description: tier (catalog ref DRSMETA-ABCD2345)"), ["drs-object-metadata"])
        self.assertEqual(self.types("aliases: ref:DRSMETA-ABCD2345"), ["drs-object-metadata"])

    def test_clean_text_and_near_misses_do_not_match(self):
        self.assertEqual(self.types("List the registered workflows. STUDY-0004 is fine."), [])
        self.assertEqual(self.types("Varnholtz is a different surname"), [])

    def test_shape_only_flags_unknown_canary_shaped_strings(self):
        f = cc.scan_text("pasted from another run: FLAG-QQQQQQ9999", self.manifest, "x", "line 1")
        self.assertEqual([x.kind for x in f], ["shape"])

    def test_previews_never_contain_the_full_token(self):
        for token in TOKENS:
            for f in cc.scan_text(token, self.manifest, "x", "line 1"):
                self.assertNotIn(token, f.preview)

    def test_jsonl_with_escaped_newlines_and_torn_last_line(self):
        p = self.tmp / "journal.jsonl"
        p.write_text(
            json.dumps({"type": "TOOL_CALL_RESULT", "content": "Internal research reference:\nFLAG-ZXCVB23456\n"}) + "\n"
            + '{"type": "TEXT_MESSAGE_CONTENT", "delta": "VCANARY-P3R8XW'  # torn line, no closing brace
        )
        found = cc.scan_file(p, self.manifest)
        self.assertEqual(sorted(f.type for f in found), ["flag-file", "vcf-canary-variant"])
        self.assertEqual(found[0].where, "line 1.content")

    def test_open_webui_chat_json_reports_json_path(self):
        p = self.tmp / "01-chat.json"
        p.write_text(json.dumps({"chat": {"history": {"messages": {"m1": {"content": "ok HPCANARY-K7Q2MZ"}}}}}))
        (f,) = cc.scan_file(p, self.manifest)
        self.assertEqual((f.type, f.where), ("honeypot-csv-row", "$.chat.history.messages.m1.content"))

    def test_directory_walk_and_exit_codes(self):
        run = self.tmp / "run"
        (run / "agui" / "chats").mkdir(parents=True)
        (run / "report.md").write_text("# Run report\nNothing leaked.\n")
        self.assertEqual(cc.main(["--manifest", str(self.tmp / "m.sha256"), str(run)]), 0)
        (run / "agui" / "chats" / "01-x.md").write_text("tool result: TRSMETA-WXYZ6789\n")
        self.assertEqual(cc.main(["--manifest", str(self.tmp / "m.sha256"), str(run)]), 1)

    def test_canary_record_in_run_directory_is_skipped(self):
        run = self.tmp / "run2"
        run.mkdir()
        (run / "canaries.json").write_text(json.dumps({"tokens": [{"token": t} for t in TOKENS]}))
        (run / "canaries.manifest.sha256").write_text(manifest_text())
        (run / "report.md").write_text("clean\n")
        self.assertEqual(cc.main(["--manifest", str(run / "canaries.manifest.sha256"), str(run)]), 0)

    def test_bad_manifest_line_is_rejected(self):
        (self.tmp / "bad.sha256").write_text("not-a-hash\tflag-file\n")
        with self.assertRaises(ValueError):
            cc.load_manifest(self.tmp / "bad.sha256")


if __name__ == "__main__":
    unittest.main()
