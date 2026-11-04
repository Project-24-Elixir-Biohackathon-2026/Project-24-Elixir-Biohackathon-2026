## 9. Checks (role end and `verify.yml`)

`verify.yml` runs these when `'agui' in spe_frontends` (from the instance
file passed with `-e`, as for every other parameter):

1. `GET 127.0.0.1:{{ spe_agui_agent_port }}/healthz` → 200.
2. `GET 127.0.0.1:{{ spe_agui_ui_port }}/` → 200.
3. `POST /agent` without a key → 401.
4. **Key boundary**: through the sandbox API (`POST /execute`), run
   `env` and assert neither the LLM key nor the agent key appears in the
   output; run `curl -s -o /dev/null -w '%{http_code}' http://agent:8100/agent -X POST`
   and assert `401`. The same check asserts that neither `docker inspect`
   of the sandbox's environment nor `terminal.env` contains the agent key,
   and that no file under `/data/sessions` in `chat-ui` contains the agent,
   LLM or sandbox key (§6, *Security and limits*).
5. **Smoke** (when `spe_agui_smoke`): one AG-UI run, "List the registered
   workflows", with the bearer key; assert the event stream contains a
   `TOOL_CALL_START` and ends with `RUN_FINISHED`. Implemented as a small
   Python helper copied to `/opt/spe/bin/`, like `smoke_test.py`. It calls
   the agent directly, not through `chat-ui`.
6. **Session API answers**: `GET 127.0.0.1:{{ spe_agui_ui_port }}/api/sessions`
   → 200 with a JSON list.
