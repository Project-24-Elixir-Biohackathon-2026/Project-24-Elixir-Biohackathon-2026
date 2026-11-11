# trs-write-sensitive (trs-guard): register a TRS tool version whose workflow content names a path
# under the sensitive data tier. open (the guard is off): the filer accepts it like any other
# version, whatever it names. closed: refused (403) before the filer sees it. Nothing is run
# either way -- this probe only exercises the write step paths/P2.md starts from.
set -u
tool=spe-probe-trs-guard; ver="v$(date +%s)"; body=$(mktemp)
jq -n --arg t "$tool" "{organization: \"local\", name: \$t, description: \"controls probe\", has_checker: false, toolclass: {id: \"workflow\", name: \"Workflow\", description: \"Runnable workflow\"}, versions: []}" > "$body"
code=$(curl -sS -o /dev/null -w "%{http_code}" -X PUT "$TRS_BASE/tools/$tool" -H "Content-Type: application/json" --data-binary @"$body") || code=000
echo "HTTP $code trs-tool"
jq -n --arg c "workflow { println file(\"/data-share/sensitive/registry/linkage.csv\").text }" --arg v "$ver" "{name: \$v, is_production: false, descriptor_type: [\"NFL\"], files: [{tool_file: {path: \"main.nf\", file_type: \"PRIMARY_DESCRIPTOR\"}, file_wrapper: {content: \$c}, type: \"NFL\"}]}" > "$body"
code=$(curl -sS -o /dev/null -w "%{http_code}" -X PUT "$TRS_BASE/tools/$tool/versions/$ver" -H "Content-Type: application/json" --data-binary @"$body") || code=000
echo "HTTP $code trs-version"
rm -f "$body"
case "$code" in
  200|201) echo "PROBE open trs-version=$code" ;;
  403|405) echo "PROBE closed trs-version=$code" ;;
  *) echo "trs-version: unexpected status $code" >&2; exit 1 ;;
esac
