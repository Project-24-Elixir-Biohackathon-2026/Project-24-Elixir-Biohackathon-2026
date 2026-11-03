## 8. Error handling and known gaps

- **Sandbox down at startup**: the agent retries fetching the OpenAPI
  spec; `/healthz` stays 503 until it succeeds; compose's healthcheck and
  the role's wait reflect that.
- **Sandbox error during a run**: the tool returns the HTTP status and body
  to the model as the tool result (as Open WebUI does), not an exception
  that kills the run.
- **LLM endpoint error**: the run ends with `RUN_ERROR` with the provider's
  status and message; the chat shows it.
- **Usage limit hit**: `RUN_ERROR`, see §5.
- **Long commands**: `run_command` returns while the command keeps running
  in the sandbox; the model polls with `get_process_status` as the runbook
  says. No HTTP request blocks for the duration of a workflow.
- **Known gap, kept from today**: the sandbox has unrestricted outbound
  network access. Restricting egress is a scenario concern (0005) and
  belongs to sub-project 2.
- **Known gap**: the sandbox's own key is readable by its commands
  (verified); it grants only the same shell. Documented so it is not
  mistaken for a scenario flag.
