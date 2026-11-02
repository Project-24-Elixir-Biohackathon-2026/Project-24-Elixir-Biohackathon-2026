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
COPY instrumentation.ts ./
RUN npm run build

FROM node:24-slim
WORKDIR /app
# No telemetry from an SPE: Next.js, CopilotKit runtime (and, via /info, its browser client).
# NEXT_MANUAL_SIG_HANDLE: Next.js's own SIGTERM handler would exit before the sessions are saved;
# instrumentation.ts installs the one that drains them (lib/shutdown.ts).
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 COPILOTKIT_TELEMETRY_DISABLED=true DO_NOT_TRACK=1 \
    PORT=3000 HOSTNAME=0.0.0.0 NEXT_MANUAL_SIG_HANDLE=true
COPY --from=build --chown=root:root /app/.next/standalone ./
COPY --from=build --chown=root:root /app/.next/static ./.next/static
# The image's own files stay root-owned and read-only to the app; only .next/cache is writable,
# and /data, where the chat-sessions volume is mounted: Docker copies /data/sessions, with its
# owner, into the volume when it is first mounted empty, so a fresh volume starts writable.
RUN install -d -o node -g node -m 0700 /app/.next/cache /data /data/sessions
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:' + (process.env.PORT || 3000) + '/').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server.js"]
