# egress (L3): a request to a host other than the API host. open: any HTTP answer; closed: no connection.
set -u
url=${PROBE_EGRESS_URL:-https://example.org/}
code=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null); rc=$?
echo "HTTP $code egress"
if [ "$code" != 000 ]; then echo "PROBE open egress=$code"; else echo "PROBE closed egress=000 curl=$rc"; fi
