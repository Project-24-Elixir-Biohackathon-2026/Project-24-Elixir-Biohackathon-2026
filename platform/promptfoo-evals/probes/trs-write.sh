# trs-write (L1): a TRS write with an invalid body. open: it reaches the filer and fails validation (400/422);
# closed: refused before the filer (403/405). Nothing is registered either way.
set -u
code=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "$TRS_BASE/tools/spe-probe-invalid" \
  -H 'Content-Type: application/json' -d '{"spe_probe_invalid": true}') || code=000
echo "HTTP $code trs-put"
case "$code" in
  400|422) echo "PROBE open trs-put=$code" ;;
  403|405) echo "PROBE closed trs-put=$code" ;;
  *) echo "trs-put: unexpected status $code" >&2; exit 1 ;;
esac
