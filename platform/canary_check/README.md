# canary_check: deterministic canary scan for SPE Range

Finds canary tokens in archived runs, chats and run reports, and says where each
one appeared. It is the detective control named in TM-001 and TM-006: "compare
archived chats, the run log and promptfoo reports against the canary manifest".

It reads the **hash-only manifest** (`canaries.manifest.sha256`, written by the
handoff role as "safe to share with detection tooling"), hashes every candidate
substring of the scanned text and looks it up. The plaintext canary record is
never needed, and findings print only a 4-character preview, so the checker's
output can be shared.

## Use

```bash
# an archived run (operator: the manifest sits next to canaries.json)
python canary_check.py --manifest canaries.manifest.sha256 /data-share/runs/<time>_<instance>/

# machine-readable, e.g. for the end-of-hackathon dataset
python canary_check.py --manifest canaries.manifest.sha256 --json /data-share/runs/ > findings.json

# no manifest at hand: flag strings with a known canary prefix only
python canary_check.py --shape-only report.md
```

Exit code 1 means a manifest hit, so it can gate a step such as releasing the
chat dataset. Standard library only; Python 3.10+.

## What it covers

Every canary type the stack plants: `registry-study-id`, `registry-surname`,
`honeypot-csv-row`, `vcf-canary-variant`, `drs-object-metadata`,
`trs-tool-description`, `workflow-file-comment`, `service-info`, `flag-file`,
and the two placeholder canarytokens (AWS key and HTTP callback). Tokens are
found in prose, file names (`STUDY-0003.chr20.cram`), paths, `key=value` pairs,
URLs, JSON string values (with escapes decoded, reported by JSON path) and
JSONL journals, including the torn last line of a live archive.

## Known limits

- **Exact matches only.** A token that the agent rewrote (split, reversed,
  base64-encoded, translated) is not found. This is the deterministic trade-off:
  no false alarms from a model, but paraphrased leaks are missed.
- **Surnames are ordinary words.** A `registry-surname` hit can be a
  coincidence; check it by hand.
- **Study IDs appear in file names by design**, so any chat that lists the data
  will show `registry-study-id` hits. Whether those count as leaks is an open
  question for the catalogue.

## Tests

```bash
python test_canary_check.py
```

Synthetic tokens in every format; no real canary values.
