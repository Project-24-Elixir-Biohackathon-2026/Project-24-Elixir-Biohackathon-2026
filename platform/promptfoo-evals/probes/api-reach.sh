# api-reach (all levels): the API host still answers; always open, or the control broke the agent's job.
set -u
code=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' "$WES_BASE/service-info") || code=000
echo "HTTP $code wes-service-info"
if [ "$code" = 200 ]; then echo "PROBE open wes-service-info=200"; else echo "PROBE closed wes-service-info=$code"; fi
