#!/usr/bin/env bash
# One ladder run for one level, condition and model (spec part 06): the controls suite, then, only if every
# probe agrees with hardening.json's level, the whole agent suite (model calls), repeated and
# uncached. The build sets the condition: injected (hardening.json injections: true) or clean (false); a
# mixed build, or a hand-off that disagrees with its condition, is refused before any call.
# Usage: run.sh <hand-off dir> <repeat>. Reports: reports/L<level>/ (injected) or reports/L<level>-clean/,
# each with hardening.json, controls.json, agent.json, run.json (start time, canary digest) and, when
# injected, injections.json: what matrix.py counts reads.
set -euo pipefail
if [ $# -ne 2 ] || ! [[ $2 =~ ^[1-9][0-9]*$ ]]; then
  echo "usage: run.sh <hand-off dir> <repeat>" >&2; exit 2
fi
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
handoff=$(cd "$1" && pwd) || exit 2
repeat=$2
cd "$(dirname "$0")"
export SPE_HANDOFF_DIR="$handoff"
if ! instance=$(python3 controls_asserts.py check-handoff "$handoff"); then
  echo "run.sh: stale or malformed hand-off in $handoff; refusing" >&2; exit 2
fi
if ! condition=$(python3 -c 'import sys, handoff
try:
    print(handoff.condition(sys.argv[1]))
except handoff.ConfigError as e:
    sys.exit(f"run.sh: {e}")' "$handoff"); then
  exit 2
fi
level=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["level"])' "$handoff/hardening.json")
run="L$level"
if [ "$condition" = clean ]; then run="L$level-clean"; fi
mkdir -p reports
rm -f reports/controls.json reports/agent.json
npm run eval:controls || true   # promptfoo exits non-zero on failed tests; the gate decides
if ! python3 controls_asserts.py gate reports/controls.json; then
  echo "run.sh: the controls suite disagrees with level in hardening.json; no agent run" >&2; exit 3
fi
status=0
npm run eval:agent -- --repeat "$repeat" --no-cache || status=$?
if [ ! -s reports/agent.json ]; then
  echo "run.sh: eval:agent wrote no report (exit $status)" >&2; exit 4
fi
rm -rf "reports/$run"
mkdir -p "reports/$run"
cp "$handoff/hardening.json" reports/controls.json reports/agent.json "reports/$run/"
if [ "$condition" = injected ]; then cp "$handoff/injections.json" "reports/$run/"; fi
python3 -c 'import json, sys, handoff
print(json.dumps({"started": sys.argv[2], "canaries_sha256": handoff.canaries_digest(sys.argv[1])}))' \
  "$handoff" "$started" > "reports/$run/run.json"
echo "run.sh: $instance, $condition, reports in reports/$run/ (agent suite exit $status)"
