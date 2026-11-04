# A leftover chat UI preview server hides from `pgrep -f server.js`

**Symptom.** The e2e (`platform/dev/e2e/sessions.py`) or a preview of the standalone chat UI fails to bind its
port (`EADDRINUSE`), yet `pgrep -af server.js` and `pgrep -af standalone` list nothing.

**Why.** Next's standalone server renames its process: it shows as `next-server (v1…)`, not
`node .next/standalone/server.js`.

**Fix.** Find it by the port: `ss -ltnp | grep <port>` gives the PID; kill that PID. If you match by pattern, keep
it from matching your own shell (`pkill-self-match.md`): `pgrep -af 'next-serve[r]'`.
