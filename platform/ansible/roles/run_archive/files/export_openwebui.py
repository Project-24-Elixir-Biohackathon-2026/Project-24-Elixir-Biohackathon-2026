#!/usr/bin/env python3
"""Export what a participant produced in OpenWebUI to one JSON file.

Runs on the SPE VM against the local OpenWebUI (stdlib only):
    export_openwebui.py <base url> <out.json>
Credentials come from WEBUI_EMAIL / WEBUI_PASSWORD; both may be empty when
OpenWebUI runs without a login (sign-in then returns the single admin).
"""
import json
import os
import sys
import time
import urllib.request

base, out = sys.argv[1:3]


def call(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


token = call("/api/v1/auths/signin", {
    "email": os.environ.get("WEBUI_EMAIL", ""),
    "password": os.environ.get("WEBUI_PASSWORD", ""),
})["token"]

bundle = {
    "exported_at": int(time.time()),
    "chats": call("/api/v1/chats/all/db", token=token),
    "tags": call("/api/v1/chats/all/tags", token=token),
    "notes": [call(f"/api/v1/notes/{n['id']}", token=token)
              for n in call("/api/v1/notes/", token=token)],
}
with open(out, "w") as f:
    json.dump(bundle, f, indent=1)
print(f"{len(bundle['chats'])} chats, {len(bundle['notes'])} notes")
