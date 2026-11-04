# The SPE chat UI: Next.js (standalone output) + CopilotKit, port 3000.
# Needs AGENT_URL and AGENT_API_KEY at run time (server side only).
FROM node:24-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY next.config.mjs tsconfig.json ./
COPY app ./app
COPY lib ./lib
COPY scripts/export-journals.ts ./scripts/
COPY instrumentation.ts ./
RUN npm run build
# The journal exporter (scripts/export-journals.ts) runs outside the server, in a one-off container. The
# standalone output bundles @ag-ui/client and rxjs into the server's chunks and leaves them out of its
# node_modules, so collect what the exporter imports: lib/ and both packages with their dependencies, as
# npm installed them from the lock file.
# Scoped to this step only: pipefail, so a failing npm query or node filter fails the build, not just a
# failing xargs; reverted right after so later RUN steps keep the default shell.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN set -e \
 && mkdir -p /exporter/lib /exporter/scripts \
 && npm query ':root > #@ag-ui/client, :root > #@ag-ui/client *, :root > #rxjs, :root > #rxjs *' \
    | node -e 'let s = ""; process.stdin.on("data", (d) => (s += d)).on("end", () => { for (const p of JSON.parse(s)) console.log(p.location); })' \
    | xargs -r cp -a --parents -t /exporter \
 && cp lib/*.ts /exporter/lib/ \
 && cp scripts/export-journals.ts /exporter/scripts/ \
 && test -d /exporter/node_modules/@ag-ui/client \
 && test -d /exporter/node_modules/rxjs
SHELL ["/bin/sh", "-c"]

FROM node:24-slim
WORKDIR /app
# No telemetry from an SPE: Next.js, CopilotKit runtime (and, via /info, its browser client).
# NEXT_MANUAL_SIG_HANDLE: Next.js's own SIGTERM handler would exit before the sessions are saved;
# instrumentation.ts installs the one that drains them (lib/shutdown.ts).
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 COPILOTKIT_TELEMETRY_DISABLED=true DO_NOT_TRACK=1 \
    PORT=3000 HOSTNAME=0.0.0.0 NEXT_MANUAL_SIG_HANDLE=true
COPY --from=build --chown=root:root /app/.next/standalone ./
COPY --from=build --chown=root:root /app/.next/static ./.next/static
# The exporter's files merge into the standalone tree: same lock file, so a package both hold is the same version.
COPY --from=build --chown=root:root /exporter/ ./
# The image's own files stay root-owned and read-only to the app; only .next/cache is writable,
# and /data, where the chat-sessions volume is mounted: Docker copies /data/sessions, with its
# owner, into the volume when it is first mounted empty, so a fresh volume starts writable.
RUN install -d -o node -g node -m 0700 /app/.next/cache /data /data/sessions
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:' + (process.env.PORT || 3000) + '/').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server.js"]
