# Canary hit viewer — progress and rulings

Rulings slices made where they departed from or filled in the plan: *decision, why, cost if wrong*. Status per
slice is the README's slices table; the handoffs say what each session did.

## Slice 1

1. **Archive hits keep their underlying source; Open WebUI export hits are `archive`.** A run's journal and run
   log hits keep `agui-journal` and `agent-runs`, so a hit found live and found again in the archive has one dedup
   key; `openwebui-export.json` has no live twin in slice 1, so its hits are `archive`. *Cost if wrong:* a
   `source` filter on the admin page groups archive hits under the live source; relabel in slice 4.
2. **The early output on the portal is root-only** (`/data-share/canary-hits/early-output/`, root:root, dir 0750,
   files 0640) instead of plan ruling 4's group read: the portal has no `sperange-report` group (`getent` empty,
   2026-11-10). The user reads it with `sudo`. Slice 2's hits root setup re-owns `/data-share/canary-hits`.
   *Cost if wrong:* none.
3. **Receiver hits share one dedup key per canary per generation** (the spec's key, *Sources*): one `delivered`
   hit per canary, not one per request. *Cost if wrong:* repeat deliveries are not listed; slice 3 revisits it if
   the page should show each request (carried into slice 2's Task 7).
4. **`_required` lives once, in `canary_record.py`**, and `handoff.py` imports it (the plan's import list
   duplicated it). *Cost if wrong:* none.
5. **`hits.css` duplicates `report.css`'s tokens** so the static page is self-contained (no external stylesheet).
   *Cost if wrong:* the two drift; slice 3's served page links `report.css` and can drop the copy.
6. **Accepted limits** (review of #77): `test_watcher_agrees_with_metrics` reaches `canary_hits` through
   `metrics`' own `sys.path` insert (correct, and one line to make explicit when next touched); the agent run log's
   `answer` joins a run's messages with no separator, so a token right after another message's last word fails
   the whole-word match there, while the journal, one answer per message, still finds it. *Cost if wrong:* a
   run with a run log and no journal misses that one hit.
