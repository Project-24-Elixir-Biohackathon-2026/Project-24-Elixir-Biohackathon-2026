# The SPE agent: FastAPI + Pydantic AI over AG-UI on port 8100.
# Built from the frozen uv.lock; the offline test suite runs in the `test` stage and the
# final image depends on it, so a failing test fails the build.
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.14-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.14
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# The project itself is not installed into the venv: it runs from /app/src (PYTHONPATH), so a
# bind mount of the source over /app/src is what runs, with or without SPE_AGENT_RELOAD=1.
COPY src ./src

FROM build AS test
COPY tests ./tests
RUN uv sync --frozen --no-install-project \
 && PYTHONPATH=/app/src PYDANTIC_AI_NO_BANNER=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
 && touch /tests-passed

FROM python:3.14-slim
COPY --from=test /tests-passed /tmp/tests-passed
RUN useradd --uid 10001 --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin spe \
 && install -d -o spe -g spe -m 0700 /var/lib/spe-agent \
 && rm /tmp/tests-passed
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1 SPE_AGENT_CONFIG=/etc/spe-agent/agent.yaml
USER spe
EXPOSE 8100
VOLUME ["/var/lib/spe-agent"]
# No LLM call: /healthz only reports whether the sandbox's tools were discovered.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=4).status != 200)"]
CMD ["python", "-m", "spe_agent"]
