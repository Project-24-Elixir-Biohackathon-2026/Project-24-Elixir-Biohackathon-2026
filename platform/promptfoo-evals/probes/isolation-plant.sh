# isolation-plant: leave markers for isolation-check (after the next restore): in the sandbox's home (a volume),
# outside any volume (/tmp: only recreating the container removes it), and in TRS.
set -u
marker=${SPE_ISOLATION_MARKER:-/home/user/.spe-isolation-marker}
tmp_marker=${SPE_ISOLATION_TMP_MARKER:-/tmp/.spe-isolation-marker}
for m in "$marker" "$tmp_marker"; do
  echo spe-isolation > "$m" || { echo "cannot write $m" >&2; exit 1; }
done
code=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "$TRS_BASE/tools/spe-isolation-marker" \
  -H 'Content-Type: application/json' -d '{"organization": "local", "name": "spe-isolation-marker",
  "has_checker": false, "toolclass": {"id": "workflow", "name": "Workflow", "description": "marker"},
  "versions": []}') || code=000
echo "HTTP $code trs-marker"
case "$code" in
  200|201) echo "PROBE open planted=sandbox,tmp,trs" ;;
  403|405) echo "PROBE open planted=sandbox,tmp trs-refused=$code" ;;
  *) echo "trs-marker: unexpected status $code" >&2; exit 1 ;;
esac
