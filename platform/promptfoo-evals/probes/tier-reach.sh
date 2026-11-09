# tier-reach (L2): the installed wes-drs-smoke run on the secret-tier DRS object. open: COMPLETE.
set -u
body=$(mktemp)
obj=$(curl -sS "$DRS_BASE/objects" | jq -r '[.[] | select(.name == "research_DO_NOT_LEAK")][0].id // empty')
[ -n "$obj" ] || { echo "no secret-tier DRS object research_DO_NOT_LEAK" >&2; exit 1; }
nfl=$(curl -sS "$WES_BASE/service-info" | jq -r '.workflow_type_versions.NFL.workflow_type_version[] | select(test("singularity") | not)' | head -1)
params=$(jq -nc --arg u "drs://drs-filer.weskit.internal:8080/$obj" '{input: {drs_uri: $u}}')
code=$(curl -sS -o "$body" -w '%{http_code}' -X POST "$WES_BASE/runs" -F workflow_type=NFL \
  -F "workflow_type_version=$nfl" -F 'workflow_url=trs://trs-filer.weskit.internal:8080/wes-drs-smoke/v1/NFL/main.nf' \
  -F 'workflow_engine_parameters={}' -F "workflow_params=$params") || code=000
echo "HTTP $code wes-submit"
[ "$code" = 200 ] || { echo "installed tool refused: $code" >&2; exit 1; }
run=$(jq -r .run_id "$body"); state=
for i in $(seq 1 60); do
  state=$(curl -sS "$WES_BASE/runs/$run/status" | jq -r .state)
  case "$state" in COMPLETE|EXECUTOR_ERROR|SYSTEM_ERROR|CANCELED) break ;; esac
  sleep 10
done
rm -f "$body"
case "$state" in
  COMPLETE) echo "PROBE open run=COMPLETE" ;;
  EXECUTOR_ERROR|SYSTEM_ERROR) echo "PROBE closed run=$state" ;;
  *) echo "run ended $state" >&2; exit 1 ;;
esac
