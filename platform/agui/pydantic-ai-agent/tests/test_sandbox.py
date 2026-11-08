"""Tools generated from open-terminal's OpenAPI, called against a fake sandbox."""
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from spe_agent.sandbox import (
    SandboxClient,
    SandboxUnavailable,
    build_tools,
    operations_from_openapi,
    select_operations,
    truncate,
)

FIXTURE = Path(__file__).parent / "fixtures" / "open-terminal-0.16.1-openapi.json"
SPEC = json.loads(FIXTURE.read_text())
OPS = {op.name: op for op in operations_from_openapi(SPEC)}
BASE = "http://sandbox:8000"
KEY = "sandbox-key"

EXPECTED = {
    "list_files", "read_file", "display_file", "write_file", "replace_file_content", "grep_search",
    "match_files", "search_files", "glob_search", "list_processes", "run_command", "get_process_status",
    "send_process_input", "kill_process", "read_user_terminal", "send_user_terminal_input",
}


class Recorder:
    """A fake sandbox: records requests, answers with `respond(request)`."""

    def __init__(self, respond=None):
        self.requests: list[httpx.Request] = []
        self.respond = respond or (lambda req: httpx.Response(200, json={"ok": True}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)


def client_for(recorder, **kw) -> SandboxClient:
    return SandboxClient(BASE, KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(recorder)), **kw)


# --- schema generation -------------------------------------------------------

def test_sixteen_operations_from_fixture():
    assert set(OPS) == EXPECTED


def test_query_params_follow_open_webui():
    params = OPS["read_file"].parameters
    assert params["required"] == ["path"]
    assert params["properties"]["path"]["type"] == "string"
    # anyOf parameter schemas have no top-level type: Open WebUI makes them strings
    assert params["properties"]["start_line"]["type"] == "string"
    assert OPS["read_file"].query_params == {"path", "start_line", "end_line"}
    assert OPS["read_file"].required_query == {"path"}


def test_body_is_resolved_and_merged():
    op = OPS["run_command"]
    props = op.parameters["properties"]
    assert {"command", "cwd", "wait", "tail"} <= set(props)
    assert "command" in op.parameters["required"]
    assert op.has_body
    assert "$ref" not in json.dumps(op.parameters)
    # clean_properties: single non-null anyOf collapsed, default null dropped
    assert props["cwd"]["type"] == "string" and "anyOf" not in props["cwd"]
    assert "default" not in props["cwd"]


def test_path_params_recorded():
    op = OPS["get_process_status"]
    assert op.path_params == {"process_id"}
    assert "process_id" in op.parameters["required"]
    assert op.method == "GET" and op.path == "/execute/{process_id}/status"


def test_enum_values_in_description():
    spec = {"paths": {"/x": {"get": {"operationId": "x", "parameters": [
        {"name": "mode", "in": "query", "schema": {"type": "string", "enum": ["a", "b"], "description": "Mode"}}]}}}}
    (op,) = operations_from_openapi(spec)
    assert op.parameters["properties"]["mode"]["description"] == "Mode. Possible values: a, b"


def test_local_refs_only():
    spec = {"paths": {"/x": {"post": {"operationId": "x", "requestBody": {"content": {"application/json": {
        "schema": {"$ref": "https://evil.example/schema.json"}}}}}}}}
    (op,) = operations_from_openapi(spec)
    assert op.parameters["properties"] == {}


def test_allowlist_filters():
    ops = select_operations(list(OPS.values()), ["run_command", "get_process_status"])
    assert [o.name for o in ops] == ["run_command", "get_process_status"]
    assert len(select_operations(list(OPS.values()), "all")) == 16


def test_allowlist_rejects_unknown():
    with pytest.raises(ValueError, match="nope"):
        select_operations(list(OPS.values()), ["run_command", "nope"])


# --- truncation --------------------------------------------------------------

def test_truncate_keeps_short_text():
    assert truncate("hello", 100) == "hello"


def test_truncate_total_within_cap():
    out = truncate("é" * 100, 60)  # 200 bytes
    assert len(out.encode()) <= 60
    assert out.endswith("[truncated: " + out.split("[truncated: ")[1])
    shown = int(out.split("[truncated: ")[1].split(" ")[0])
    assert out.split("[truncated: ")[1] == f"{shown} of 200 bytes shown]"
    assert shown % 2 == 0  # never cuts a character in half


# --- calls ---------------------------------------------------------------------

async def test_request_shape_and_bearer():
    rec = Recorder()
    c = client_for(rec)
    out = await c.call(OPS["run_command"], {"command": "ls", "wait": 5})
    req = rec.requests[0]
    assert req.method == "POST"
    assert req.url.path == "/execute" and req.url.params["wait"] == "5"
    # Open WebUI sends every argument as the JSON body when the operation has one
    assert json.loads(req.content) == {"command": "ls", "wait": 5}
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(out) == {"ok": True}


async def test_session_header():
    rec = Recorder()
    await client_for(rec).call(OPS["list_processes"], {}, session_id="thread-1")
    assert rec.requests[0].headers["x-session-id"] == "thread-1"


async def test_empty_optional_query_is_dropped():
    rec = Recorder()
    await client_for(rec).call(OPS["list_files"], {"directory": ""})
    assert "directory" not in rec.requests[0].url.params


async def test_required_query_is_kept_even_if_empty():
    rec = Recorder()
    await client_for(rec).call(OPS["grep_search"], {"query": ""})
    assert rec.requests[0].url.params["query"] == ""


async def test_missing_required_parameter_is_an_error():
    rec = Recorder()
    out = await client_for(rec).call(OPS["read_file"], {})
    assert "path" in json.loads(out)["error"]
    assert rec.requests == []


async def test_path_param_is_encoded():
    rec = Recorder()
    await client_for(rec).call(OPS["get_process_status"], {"process_id": "a/../b?x=1"})
    raw = rec.requests[0].url.raw_path.decode()
    assert raw.startswith("/execute/a%2F..%2Fb%3Fx%3D1/status")
    assert rec.requests[0].url.host == "sandbox"


@pytest.mark.parametrize("bad", [".", "..", ""])
async def test_path_param_dot_segments_rejected(bad):
    rec = Recorder()
    out = await client_for(rec).call(OPS["kill_process"], {"process_id": bad})
    assert "error" in json.loads(out)
    assert rec.requests == []


async def test_delete_sends_empty_json_body():
    rec = Recorder()
    await client_for(rec).call(OPS["kill_process"], {"process_id": "p1", "force": True})
    req = rec.requests[0]
    assert req.method == "DELETE" and req.url.params["force"] == "true"
    assert json.loads(req.content) == {}


async def test_http_error_is_a_result():
    rec = Recorder(lambda r: httpx.Response(404, text="no such process"))
    out = await client_for(rec).call(OPS["get_process_status"], {"process_id": "p9"})
    assert json.loads(out) == {"error": "HTTP error 404: no such process"}


async def test_redirect_not_followed():
    rec = Recorder(lambda r: httpx.Response(302, headers={"location": "http://elsewhere/"}))
    out = await client_for(rec).call(OPS["list_processes"], {})
    assert "302" in json.loads(out)["error"]
    assert len(rec.requests) == 1


async def test_timeout_is_a_result():
    def boom(request):
        raise httpx.ReadTimeout("timed out", request=request)
    out = await client_for(Recorder(boom)).call(OPS["list_processes"], {})
    assert "timed out" in json.loads(out)["error"].lower()


async def test_non_json_text_is_returned_as_text():
    rec = Recorder(lambda r: httpx.Response(200, text="plain words", headers={"content-type": "text/plain"}))
    assert await client_for(rec).call(OPS["list_processes"], {}) == "plain words"


async def test_malformed_json_is_returned_as_text():
    rec = Recorder(lambda r: httpx.Response(200, content=b'{"broken', headers={"content-type": "application/json"}))
    assert await client_for(rec).call(OPS["list_processes"], {}) == '{"broken'


async def test_binary_output_is_truncated_safely():
    blob = bytes(range(256)) * 40_000  # ~10 MB, invalid UTF-8
    rec = Recorder(lambda r: httpx.Response(200, content=blob, headers={"content-type": "application/octet-stream"}))
    c = client_for(rec)
    (tool,) = build_tools(c, [OPS["read_file"]], max_output_bytes=16384)
    out = await tool.function(SimpleNamespace(deps=None), path="/data/x.cram")
    assert isinstance(out, str)
    assert len(out.encode()) <= 16384
    assert out.endswith(f"of {len(blob)} bytes shown]")


# --- discovery -------------------------------------------------------------------

def discovery(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p == "/openapi.json":
        return httpx.Response(200, json=SPEC)
    if p == "/files/cwd":
        return httpx.Response(200, json={"cwd": "/home/user"})
    if p == "/api/config":
        return httpx.Response(200, json={"features": {"system": True}})
    if p == "/system":
        return httpx.Response(200, json={"prompt": "You have access to a computer."})
    return httpx.Response(404)


async def test_discovery():
    c = client_for(Recorder(discovery))
    assert (await c.openapi())["info"]["version"] == "0.16.1"
    assert await c.cwd() == "/home/user"
    assert await c.system_prompt() == "You have access to a computer."


async def test_system_prompt_needs_feature_flag():
    def no_flag(request):
        if request.url.path == "/api/config":
            return httpx.Response(200, json={"features": {}})
        return discovery(request)
    rec = Recorder(no_flag)
    assert await client_for(rec).system_prompt() is None
    assert "/system" not in [r.url.path for r in rec.requests]


async def test_openapi_failure_is_unavailable():
    with pytest.raises(SandboxUnavailable):
        await client_for(Recorder(lambda r: httpx.Response(503))).openapi()

    def refused(request):
        raise httpx.ConnectError("refused", request=request)
    with pytest.raises(SandboxUnavailable):
        await client_for(Recorder(refused)).openapi()


# --- tools ---------------------------------------------------------------------

async def test_each_tool_is_bound_to_its_own_operation():
    rec = Recorder()
    c = client_for(rec)
    tools = {t.name: t for t in build_tools(c, list(OPS.values()), max_output_bytes=16384)}
    assert set(tools) == EXPECTED
    await tools["list_processes"].function(SimpleNamespace(deps=None))
    await tools["read_user_terminal"].function(SimpleNamespace(deps=None))
    assert [r.url.path for r in rec.requests] == ["/execute", "/api/terminals/user/output"]


async def test_tool_passes_thread_as_session():
    rec = Recorder()
    (tool,) = build_tools(client_for(rec), [OPS["list_processes"]], max_output_bytes=100)
    await tool.function(SimpleNamespace(deps=SimpleNamespace(session_id="t-7")))
    assert rec.requests[0].headers["x-session-id"] == "t-7"


def test_run_command_description_gets_cwd():
    c = client_for(Recorder())
    tools = {t.name: t for t in build_tools(c, list(OPS.values()), max_output_bytes=100, cwd="/home/user")}
    assert tools["run_command"].description.endswith("\n\nThe current working directory is: /home/user")
    assert "working directory is" not in (tools["list_files"].description or "")
    assert tools["run_command"].function_schema.json_schema == OPS["run_command"].parameters


async def test_owned_client_is_closed_injected_is_not():
    injected = httpx.AsyncClient(transport=httpx.MockTransport(Recorder()))
    await SandboxClient(BASE, KEY, http=injected).aclose()
    assert not injected.is_closed
    owned = SandboxClient(BASE, KEY)
    await owned.aclose()
    assert owned._http.is_closed


@pytest.mark.parametrize("value, encoded", [
    ("%2e%2e", "%252e%252e"),
    ("%2Fadmin", "%252Fadmin"),
    ("//elsewhere/a", "%2F%2Felsewhere%2Fa"),
    ("a\\..\\b", "a%5C..%5Cb"),
])
async def test_encoded_paths_stay_on_sandbox_route(value, encoded):
    rec = Recorder()
    await client_for(rec).call(OPS["get_process_status"], {"process_id": value})
    req = rec.requests[0]
    assert req.url.raw_path == f"/execute/{encoded}/status".encode()
    assert req.url.host == "sandbox"


async def test_injected_client_cannot_override_bearer_or_follow_redirects():
    rec = Recorder(lambda r: httpx.Response(307, headers={"location": "https://elsewhere/"}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec),
                                auth=("other", "password"), follow_redirects=True) as http:
        await SandboxClient(BASE, KEY, http=http).call(OPS["list_processes"], {})
    assert len(rec.requests) == 1
    assert rec.requests[0].headers["authorization"] == f"Bearer {KEY}"


async def test_model_arguments_cannot_set_origin_or_headers():
    rec = Recorder()
    await client_for(rec).call(OPS["list_processes"], {
        "base_url": "https://elsewhere", "headers": {"Authorization": "evil"},
    })
    assert rec.requests[0].url.host == "sandbox"
    assert rec.requests[0].headers["authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("payload", [[], {"paths": []}, {"info": {}}, "broken"])
async def test_malformed_discovery_is_unavailable(payload):
    with pytest.raises(SandboxUnavailable):
        await client_for(Recorder(lambda r: httpx.Response(200, json=payload))).openapi()


async def test_errors_do_not_echo_credentials_or_exception_details():
    rec = Recorder(lambda r: httpx.Response(500, text=f"failed with {KEY}"))
    assert KEY not in await client_for(rec).call(OPS["list_processes"], {})

    def fail(request):
        raise httpx.ConnectError(f"private details {KEY}", request=request)
    result = await client_for(Recorder(fail)).call(OPS["list_processes"], {})
    assert "private details" not in result and KEY not in result


@pytest.mark.parametrize("cap", [0, 1, 20, 50, 100])
def test_truncation_small_caps(cap):
    assert len(truncate("é" * 1000, cap).encode()) <= cap


async def test_discovery_response_limit():
    rec = Recorder(lambda r: httpx.Response(200, content=b" " * (1024 * 1024 + 1)))
    with pytest.raises(SandboxUnavailable):
        await client_for(rec).openapi()
