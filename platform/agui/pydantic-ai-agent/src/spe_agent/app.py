"""FastAPI service: POST /agent (AG-UI, bearer key) and GET /healthz.

Startup never waits for the sandbox. A background task discovers the sandbox's OpenAPI
(with backoff) and builds the agent; until then /healthz and authenticated /agent answer
503. Once ready, the sandbox is probed every `probe_interval` seconds; when it stops
answering the service goes back to 503 and rediscovers, so a sandbox restart needs no
agent restart. Each run uses the agent snapshot it started with.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from ag_ui.core import BaseEvent, EventType, RunAgentInput, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.ui.ag_ui import AGUIAdapter, AGUIEventStream
from pydantic_ai.usage import RunUsage

from .agent import RunDeps, build_agent, build_model, compose_prompt
from .compaction import (
    CompactionRecord, build_sent, estimate_tokens, marker_events, markers_to_activities, nothing_to_compact,
    summarise,
)
from .config import Config, ConfigError, Secrets
from .runlog import RunLog, RunRecorder, redact
from .sandbox import SandboxClient, SandboxUnavailable, build_tools, operations_from_openapi, select_operations

log = logging.getLogger("spe_agent")

MAX_ERROR_CHARS = 500
COMMAND_KEY = "spe_command"
COMPACTION_OFF = "Compaction is turned off on this instance."
NOTHING_TO_COMPACT = "Nothing to compact yet."
UNKNOWN_COMMAND = "Unknown command."


def _command(run_input: RunAgentInput) -> dict | None:
    """The run's command, None for an ordinary run; a value that is not an object is an unknown command ({})."""
    props = run_input.forwarded_props
    if not isinstance(props, dict) or props.get(COMMAND_KEY) is None:
        return None
    command = props[COMMAND_KEY]
    return command if isinstance(command, dict) else {}

# The marker goes out before the next event that opens a response or ends the run, never before a tool
# result: the run is one event ahead of this loop, so the step's last tool result may still be on its way.
_MARKER_BEFORE = {EventType.TEXT_MESSAGE_START, EventType.TOOL_CALL_START, EventType.THINKING_START,
                  EventType.REASONING_START, EventType.RUN_FINISHED, EventType.RUN_ERROR}


class _EventStream(AGUIEventStream):
    """Ends tool calls when the model response ends, not when the next part starts.

    pydantic-ai ends a part as soon as another one starts, but an OpenAI-compatible stream (vLLM
    with qwen) can send a content chunk between a tool call's argument chunks. The arguments that
    follow then come after the call's TOOL_CALL_END, and the AG-UI client rejects them ("No active
    tool call found"). AG-UI lets a text message and tool calls be open at once, so the ends wait.

    The held ends also go out before RUN_ERROR (a stream that breaks mid-response reaches
    `on_error` before `after_response`, and the client accepts nothing after RUN_ERROR) and before
    a call that reuses a held call's ID starts.
    """

    _pending_ends: list[ToolCallPart] | None = None

    async def handle_tool_call_end(self, part: ToolCallPart) -> AsyncIterator[BaseEvent]:
        self._pending_ends = [*(self._pending_ends or []), part]
        return
        yield

    async def _flush_ends(self, tool_call_id: str | None = None) -> AsyncIterator[BaseEvent]:
        """Send the held ends: all of them, or only those for `tool_call_id`."""
        pending = self._pending_ends or []
        flush = [p for p in pending if tool_call_id is None or p.tool_call_id == tool_call_id]
        self._pending_ends = [p for p in pending if p not in flush] or None
        for part in flush:
            async for event in super().handle_tool_call_end(part):
                yield event

    async def handle_tool_call_start(self, part: ToolCallPart) -> AsyncIterator[BaseEvent]:
        async for event in self._flush_ends(part.tool_call_id):
            yield event
        async for event in super().handle_tool_call_start(part):
            yield event

    async def after_response(self) -> AsyncIterator[BaseEvent]:
        async for event in super().after_response():
            yield event
        async for event in self._flush_ends():
            yield event

    async def on_error(self, error: Exception) -> AsyncIterator[BaseEvent]:
        async for event in self._flush_ends():
            yield event
        async for event in super().on_error(error):
            yield event


@dataclass
class _Adapter(AGUIAdapter):
    # A dataclass, so that the generated __init__ calls __post_init__ (AGUIAdapter's own __init__ does not).

    def __post_init__(self) -> None:
        # Before anything reads `messages` (a cached property over run_input): our compaction markers,
        # assistant messages in the chat's history, become the activity pydantic-ai reads as a cut point.
        self.run_input = markers_to_activities(self.run_input)

    def build_event_stream(self) -> _EventStream:
        return _EventStream(self.run_input, accept=self.accept, ag_ui_version=self.ag_ui_version)


@dataclass(frozen=True)
class Ready:
    agent: Agent[RunDeps, str]
    tool_count: int


class Service:
    def __init__(self, config: Config, secrets: Secrets, model: Model, client: SandboxClient, *,
                 owns_client: bool, retry_delay: float, max_retry_delay: float, probe_interval: float):
        self.config = config
        self._secrets = secrets.values()
        self._agent_key = secrets.agent_api_key.encode()
        self._model = model
        self._client = client
        self._owns_client = owns_client
        self._retry_delay = retry_delay
        self._max_retry_delay = max_retry_delay
        self._probe_interval = probe_interval
        try:
            self._base_prompt = config.prompt.file.read_text()
        except OSError as e:
            raise ConfigError(f"prompt.file {config.prompt.file}: {e.strerror or e}") from e
        self.runlog = RunLog(config.run_log, self._secrets)
        self.ready: Ready | None = None
        self.reason = "starting"
        self.discovery_task: asyncio.Task | None = None

    # --- lifecycle --------------------------------------------------------------------------

    async def start(self) -> None:
        self.discovery_task = asyncio.create_task(self._watch(), name="sandbox-discovery")

    async def stop(self) -> None:
        if self.discovery_task:
            self.discovery_task.cancel()
            await asyncio.gather(self.discovery_task, return_exceptions=True)
        if self._owns_client:
            await self._client.aclose()

    async def _discover(self) -> Ready:
        ops = operations_from_openapi(await self._client.openapi())
        ops = select_operations(ops, self.config.tools.sandbox_operations)
        cwd = await self._client.cwd()
        sandbox_prompt = await self._client.system_prompt() if self.config.prompt.include_sandbox_prompt else None
        tools = build_tools(self._client, ops, self.config.tools.max_output_bytes, cwd=cwd)
        prompt = compose_prompt(self._base_prompt, sandbox_prompt)
        agent = build_agent(self._model, prompt, tools, self.config.compaction)
        return Ready(agent, len(tools))

    async def _watch(self) -> None:
        delay = self._retry_delay
        while True:
            if self.ready is None:
                try:
                    self.ready = await self._discover()
                    self.reason = ""
                    delay = self._retry_delay
                    log.info("sandbox ready: %d tools", self.ready.tool_count)
                    continue
                except SandboxUnavailable:
                    self.reason = "sandbox unavailable"
                except ValueError as e:  # e.g. an allowlisted operation the sandbox does not offer
                    self.reason = str(e)
                except Exception:
                    log.exception("sandbox discovery failed")
                    self.reason = "sandbox discovery failed"
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_retry_delay)
            else:
                await asyncio.sleep(self._probe_interval)
                try:
                    await self._client.openapi()
                except SandboxUnavailable:
                    log.warning("sandbox stopped answering; rediscovering")
                    self.ready, self.reason, delay = None, "sandbox unavailable", self._retry_delay

    # --- requests ---------------------------------------------------------------------------

    def authorized(self, request: Request) -> bool:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(token.strip().encode(), self._agent_key)

    def sanitize(self, message: str) -> str:
        message = redact(message, self._secrets)
        return message if len(message) <= MAX_ERROR_CHARS else message[:MAX_ERROR_CHARS] + " […]"

    def run(self, run_input: RunAgentInput, accept: str | None = None) -> AsyncIterator[BaseEvent]:
        ready = self.ready
        if ready is None:
            raise RuntimeError("agent not ready")
        return self._events(_Adapter(agent=ready.agent, run_input=run_input, accept=accept))

    async def _events(self, adapter: _Adapter) -> AsyncIterator[BaseEvent]:
        command = _command(adapter.run_input)
        if command is not None:
            async for event in self._command_events(adapter, command):
                yield event
            return
        run_input = adapter.run_input
        recorder = RunRecorder(run_input)

        async def on_complete(result) -> None:
            recorder.usage(result.usage)

        deps = RunDeps(session_id=run_input.thread_id)
        stream = adapter.run_stream(deps=deps, usage_limits=self.config.limits.usage_limits(), on_complete=on_complete)
        status = "cancelled"  # unless a terminal event arrives: client gone or task cancelled
        try:
            async for event in stream:
                if event.type in _MARKER_BEFORE:
                    for summary in deps.compaction.take_pending():
                        for marker in marker_events(summary):
                            recorder.observe(marker)
                            yield marker
                if isinstance(event, RunErrorEvent):
                    event = event.model_copy(update={"message": self.sanitize(event.message)})
                    status = "failed"
                elif isinstance(event, RunFinishedEvent):
                    status = "completed"
                recorder.observe(event)
                yield event
        finally:
            # Closing the adapter stream ends the agent run (and its model request) if it is
            # still going. Commands the sandbox started in the background keep running there.
            await stream.aclose()
            recorder.compactions(deps.compaction.records)
            try:
                self.runlog.write(recorder.finish(status))
            except OSError:
                log.exception("could not write the run log")

    async def _command_events(self, adapter: _Adapter, command: dict) -> AsyncIterator[BaseEvent]:
        run_input = adapter.run_input
        recorder = RunRecorder(run_input)
        focus = command.get("focus") if isinstance(command.get("focus"), str) else None
        focus = (focus or "").strip() or None
        status, records, usage = "cancelled", [], RunUsage()

        def end(event: BaseEvent) -> BaseEvent:
            recorder.observe(event)
            return event

        try:
            yield end(RunStartedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id))
            if command.get("name") != "compact":
                recorder.command_input(self.sanitize(f"/{command.get('name')}"))
                status = "failed"
                yield end(RunErrorEvent(message=UNKNOWN_COMMAND))
                return
            recorder.command_input("/compact" + (f" {focus}" if focus else ""))
            history = build_sent(adapter.messages)
            # on the raw messages: build_sent replaces our marker with a framed head, which is_ours never matches
            error = (COMPACTION_OFF if not self.config.compaction.enabled
                     else NOTHING_TO_COMPACT if nothing_to_compact(adapter.messages) else None)
            if error is not None:
                status = "failed"
                yield end(RunErrorEvent(message=error))
                return
            try:
                summary = await summarise(self._model, self.config.compaction, history, usage=usage,
                                          usage_limits=self.config.limits.usage_limits(), focus=focus, manual=True)
            except Exception as e:  # sanitized as every error is
                status = "failed"
                yield end(RunErrorEvent(message=self.sanitize(str(e))))
                return
            records.append(CompactionRecord(
                trigger="manual", focus=focus, estimated_tokens=estimate_tokens(history, 0),
                messages_cut=len(adapter.messages), summary=summary.text, usage=summary.usage))
            for marker in marker_events(summary.text, manual=True):
                yield end(marker)
            status = "completed"
            yield end(RunFinishedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id))
        finally:
            recorder.usage(usage)
            recorder.compactions(records)
            try:
                self.runlog.write(recorder.finish(status))
            except OSError:
                log.exception("could not write the run log")


def create_app(config: Config, secrets: Secrets, model_override: Model | None = None,
               sandbox_client: SandboxClient | None = None, *, retry_delay: float = 1.0,
               max_retry_delay: float = 30.0, probe_interval: float = 30.0) -> FastAPI:
    model = model_override or build_model(config.model, secrets.llm_api_key)
    client = sandbox_client or SandboxClient(config.tools.sandbox_url, secrets.sandbox_api_key)
    service = Service(config, secrets, model, client, owns_client=sandbox_client is None,
                      retry_delay=retry_delay, max_retry_delay=max_retry_delay, probe_interval=probe_interval)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(title="spe-agent", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

    @app.get("/healthz")
    async def healthz():
        if service.ready is None:
            return JSONResponse({"status": "starting", "reason": service.reason}, status_code=503)
        return {"status": "ok", "tools": service.ready.tool_count}

    @app.post("/agent")
    async def agent_endpoint(request: Request):
        if not service.authorized(request):
            return JSONResponse({"detail": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        ready = service.ready
        if ready is None:
            return JSONResponse({"detail": f"agent not ready: {service.reason}"}, status_code=503)
        try:
            adapter = await _Adapter.from_request(request, agent=ready.agent)
        except ValidationError as e:
            errors = e.errors(include_url=False, include_input=False, include_context=False)
            return JSONResponse({"detail": errors}, status_code=422)
        return adapter.streaming_response(service._events(adapter))

    return app
