#!/usr/bin/env bash
# One ladder run for one level, condition and model (spec part 06): the controls suite, then, only if every
# probe agrees with hardening.json's level, the whole agent suite (model calls), repeated and
# uncached. The build sets the condition: injected (hardening.json injections: true) or clean (false); a
# mixed build, or a hand-off that disagrees with its condition, is refused before any call -- except on
# the --suite/--reports-dir/--description path (an experiment naming only some of the catalogue's
# injections, spe-eval run), where "mixed" is accepted and treated as injected (fix round 1).
# Usage: run.sh <hand-off dir> <repeat> [--suite <config>] [--reports-dir <dir>] [--description <text>].
# With none of the three, today's exact behaviour: reports/L<level>/ (injected) or reports/L<level>-clean/,
# each with hardening.json, controls.json, agent.json, run.json (start time, canary digest) and, when
# injected, injections.json (what matrix.py counts reads), via `npm run eval:controls`/`eval:agent`.
#
# With --reports-dir <dir> (experiments spec part 03, *run.sh gains three arguments*): controls.json and
# agent.json are written there directly (never under reports/), the directory is not cleared first (the
# caller, spe-eval, refuses one that already exists), and hardening.json, injections.json (if injected) and
# run.json land there too; the gate's notes go to <dir>/gate-notes.json. --suite <config> replaces agent.yaml
# for the agent eval; --description <text> gives both evals' promptfoo --description ("<text> controls" and
# "<text> agent"). Any of the three switches to calling `npx promptfoo eval` directly, since passing
# --description through an `npm run` script is awkward; the default path above stays untouched.
set -euo pipefail
usage() {
  echo "usage: run.sh <hand-off dir> <repeat> [--suite <config>] [--reports-dir <dir>] [--description <text>]" >&2
  exit 2
}
[ $# -ge 2 ] || usage
handoff_arg=$1
repeat=$2
shift 2
suite=""
reports_dir=""
description=""
while [ $# -gt 0 ]; do
  case "$1" in
    --suite) [ $# -ge 2 ] || usage; suite=$2; shift 2 ;;
    --reports-dir) [ $# -ge 2 ] || usage; reports_dir=$2; shift 2 ;;
    --description) [ $# -ge 2 ] || usage; description=$2; shift 2 ;;
    *) usage ;;
  esac
done
[[ $repeat =~ ^[1-9][0-9]*$ ]] || usage

started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
handoff=$(cd "$handoff_arg" && pwd) || exit 2
cd "$(dirname "$0")"
export SPE_HANDOFF_DIR="$handoff"
if ! instance=$(python3 controls_asserts.py check-handoff "$handoff"); then
  echo "run.sh: stale or malformed hand-off in $handoff; refusing" >&2; exit 2
fi
# "mixed" is accepted only on the non-default path (an experiment naming only some of the
# catalogue's injections never reaches the ladder's own reports/L<level>/ route below).
allow_mixed=false
if [ -n "$reports_dir" ] || [ -n "$suite" ] || [ -n "$description" ]; then allow_mixed=true; fi
if ! condition=$(python3 -c 'import sys, handoff
try:
    print(handoff.condition(sys.argv[1], allow_mixed=(sys.argv[2] == "true")))
except handoff.ConfigError as e:
    sys.exit(f"run.sh: {e}")' "$handoff" "$allow_mixed"); then
  exit 2
fi
level=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["level"])' "$handoff/hardening.json")

write_run_json() {
  python3 -c 'import json, sys, handoff
print(json.dumps({"started": sys.argv[2], "canaries_sha256": handoff.canaries_digest(sys.argv[1])}))' \
    "$handoff" "$started" > "$1"
}

if [ -z "$reports_dir" ] && [ -z "$suite" ] && [ -z "$description" ]; then
  # Today's exact behaviour: byte-identical commands, so the ladder's tests and goldens stay green.
  run="L$level"
  if [ "$condition" = clean ]; then run="L$level-clean"; fi
  mkdir -p reports
  rm -f reports/controls.json reports/agent.json
  # SPE_EVAL_PROGRESS (if set) is for the agent suite only (task 5 review, Important 2): both
  # controls.yaml and agent.yaml load isolation.py's hook, and a shared progress.jsonl would have
  # the agent total overwrite the controls total mid-run and double-count `done` lines on top of
  # it. Unset it just for the controls call; the agent call below still inherits it.
  (unset SPE_EVAL_PROGRESS; npm run eval:controls) || true   # promptfoo exits non-zero on failed tests; the gate decides
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
  write_run_json "reports/$run/run.json"
  echo "run.sh: $instance, $condition, reports in reports/$run/ (agent suite exit $status)"
  exit 0
fi

# A suite, reports directory or description was given: call promptfoo directly (npm run's "--" forwarding
# makes a repeated --description awkward), into the caller's own directory when it gave one, or today's
# reports/ (still cleared first there, so a stale controls.json/agent.json from an earlier run never scores).
agent_suite="${suite:-agent.yaml}"
if [ -n "$reports_dir" ]; then
  out="$reports_dir"
  mkdir -p "$out"
else
  out="reports"
  mkdir -p "$out"
  rm -f "$out/controls.json" "$out/agent.json"
fi
controls_desc=()
agent_desc=()
if [ -n "$description" ]; then
  controls_desc=(--description "$description controls")
  agent_desc=(--description "$description agent")
fi
(unset SPE_EVAL_PROGRESS; npx promptfoo eval -c controls.yaml --no-cache --no-share -o "$out/controls.json" \
  "${controls_desc[@]}") || true   # SPE_EVAL_PROGRESS is for the agent eval only, see above
notes_args=()
if [ -n "$reports_dir" ]; then notes_args=(--notes "$out/gate-notes.json"); fi
if ! python3 controls_asserts.py gate "$out/controls.json" "${notes_args[@]}"; then
  echo "run.sh: the controls suite disagrees with level in hardening.json; no agent run" >&2; exit 3
fi
status=0
npx promptfoo eval -c "$agent_suite" --no-cache --no-share -o "$out/agent.json" --repeat "$repeat" \
  "${agent_desc[@]}" || status=$?
if [ ! -s "$out/agent.json" ]; then
  echo "run.sh: eval:agent wrote no report (exit $status)" >&2; exit 4
fi
if [ -n "$reports_dir" ]; then
  cp "$handoff/hardening.json" "$out/"
  if [ "$condition" = injected ]; then cp "$handoff/injections.json" "$out/"; fi
  write_run_json "$out/run.json"
  echo "run.sh: $instance, $condition, reports in $out/ (agent suite exit $status)"
else
  run="L$level"
  if [ "$condition" = clean ]; then run="L$level-clean"; fi
  rm -rf "reports/$run"
  mkdir -p "reports/$run"
  cp "$handoff/hardening.json" "$out/controls.json" "$out/agent.json" "reports/$run/"
  if [ "$condition" = injected ]; then cp "$handoff/injections.json" "reports/$run/"; fi
  write_run_json "reports/$run/run.json"
  echo "run.sh: $instance, $condition, reports in reports/$run/ (agent suite exit $status)"
fi
