# isolation-check: the restore before this test removed every marker. closed: gone; open: what was left.
set -u
marker=${SPE_ISOLATION_MARKER:-/home/user/.spe-isolation-marker}
tmp_marker=${SPE_ISOLATION_TMP_MARKER:-/tmp/.spe-isolation-marker}
left=
[ -e "$marker" ] && left=sandbox
[ -e "$tmp_marker" ] && left="${left:+$left,}tmp"
code=$(curl -sS -o /dev/null -w '%{http_code}' "$TRS_BASE/tools/spe-isolation-marker") || code=000
echo "HTTP $code trs-marker"
case "$code" in
  200) left="${left:+$left,}trs" ;;
  404) ;;
  *) echo "trs-marker: unexpected status $code" >&2; exit 1 ;;
esac
if [ -n "$left" ]; then echo "PROBE open marker-left=$left"; else echo "PROBE closed markers-gone"; fi
