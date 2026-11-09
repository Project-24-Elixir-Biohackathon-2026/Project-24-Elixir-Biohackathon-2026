# canary-guard: stdlib-only reverse proxy in front of WES, DRS and TRS.
# canary_check.py is copied next to guard.py by the workflow_stack role from
# platform/canary_check/, so the proxy and the archive checker share one matcher.
FROM python:3.12-slim
RUN useradd --system --uid 10001 guard
WORKDIR /app
COPY guard.py canary_check.py ./
USER guard
EXPOSE 8080
CMD ["python", "-u", "/app/guard.py"]
