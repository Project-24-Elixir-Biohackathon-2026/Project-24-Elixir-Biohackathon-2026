"""Run in the agent container (python -): ask the sandbox, through its own API, for what a
model-chosen command sees: its environment, and the HTTP status of an unauthenticated
request from the sandbox to the agent. Prints the command's output. Uses only the sandbox
key the agent already holds; no other key is sent anywhere."""
import json
import os
import urllib.request

COMMAND = ("env; printf 'AGENT_STATUS=%s\\n' \"$(curl -s -o /dev/null -w '%{http_code}' -X POST "
           "-H 'content-type: application/json' -d '{}' http://agent:8100/agent)\"")
req = urllib.request.Request(
    "http://sandbox:8000/execute?wait=30", data=json.dumps({"command": COMMAND}).encode(), method="POST",
    headers={"Authorization": "Bearer " + os.environ["SANDBOX_API_KEY"], "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.load(resp)
output = result.get("output", "")
# open-terminal (0.12.4 and 0.16.1) returns the output as a list of {"type": ..., "data": ...} chunks.
if isinstance(output, list):
    output = "".join(str(chunk.get("data", "")) if isinstance(chunk, dict) else str(chunk) for chunk in output)
print(output)
print(f"STATUS={result.get('status')}")
