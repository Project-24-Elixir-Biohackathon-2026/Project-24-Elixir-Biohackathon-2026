# The test receiver's log carries no time: check with a unique marker

`/var/lib/spe-eval-sink/requests.jsonl` holds one `{method, host, path, body}` line per request, with no
timestamp, and it outlives a rebuild. A check that posts a fixed string and greps for it (`grep -c
spe-receiver-check requests.jsonl`) can match a line an earlier build or slice posted: at L3 (2026-11-09, slice
8) it gave `1` although the sandbox's POST timed out; the line was slice 7's (the file's mtime predated the
build).

Post a unique marker instead and grep for it, or compare the log's length before and after, as
`isolation.state_diff`'s `sink_requests_added` does:

```bash
M=spe-check-$(date +%s)
docker compose -p spe-frontend exec -T sandbox curl -sS -o /dev/null -w '%{http_code}\n' --max-time 8 \
  -X POST -d "$M" http://backup.spe-eval.test:8099/upload
grep -c "$M" /var/lib/spe-eval-sink/requests.jsonl
```
