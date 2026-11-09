# wes-inline (L1): WES accepts a run whose workflow is not an installed TRS tool. open: 200 with a run_id.
set -u
wf=$(mktemp); body=$(mktemp)
printf 'nextflow.enable.dsl=2\nworkflow { println "spe-probe" }\n' > "$wf"
nfl=$(curl -sS "$WES_BASE/service-info" | jq -r '.workflow_type_versions.NFL.workflow_type_version[] | select(test("singularity") | not)' | head -1)
[ -n "$nfl" ] || { echo "no NFL engine in service-info" >&2; exit 1; }
code=$(curl -sS -o "$body" -w '%{http_code}' -X POST "$WES_BASE/runs" -F workflow_type=NFL \
  -F "workflow_type_version=$nfl" -F workflow_url=main.nf -F 'workflow_engine_parameters={}' \
  -F 'workflow_params={}' -F "workflow_attachment=@$wf;filename=main.nf") || code=000
echo "HTTP $code wes-submit"
case "$code" in
  200) jq -e '.run_id' "$body" >/dev/null || { echo "200 without run_id" >&2; exit 1; }
       echo "PROBE open wes-submit=200" ;;
  400|403|422) echo "PROBE closed wes-submit=$code" ;;
  *) echo "wes-submit: unexpected status $code" >&2; exit 1 ;;
esac
rm -f "$wf" "$body"
