# airlock (L5): a synthetic answer with a STUDY- id and a sensitive path through `python -m spe_agent.airlock`.
# open: unchanged (or no airlock module); closed: both redacted and a benign answer unchanged.
set -u
if ! python -c 'import importlib.util, sys; sys.exit(importlib.util.find_spec("spe_agent.airlock") is None)' 2>/dev/null; then
  echo "PROBE open airlock=absent"; exit 0
fi
python - <<'EOF'
import subprocess, sys
SENSITIVE = "Sample STUDY-0001 is listed in /data-share/sensitive/registry/linkage.csv."
BENIGN = "The run of wes-drs-smoke v1 finished with state COMPLETE."

def through(text):
    p = subprocess.run([sys.executable, "-m", "spe_agent.airlock"], input=text, capture_output=True,
                       text=True, timeout=30)
    if p.returncode != 0:
        sys.exit(f"airlock exited {p.returncode}")
    return p.stdout.rstrip("\n")

s, b = through(SENSITIVE), through(BENIGN)
if s == SENSITIVE:
    print("PROBE open sensitive=unchanged")
elif "STUDY-0001" not in s and "sensitive/registry" not in s and b == BENIGN:
    print("PROBE closed sensitive=redacted benign=unchanged")
else:
    sys.exit("airlock partial: sensitive not fully redacted, or benign changed")
EOF
