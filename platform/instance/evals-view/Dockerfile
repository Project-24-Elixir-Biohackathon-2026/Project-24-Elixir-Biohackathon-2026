# evals-view's promptfoo side: `promptfoo view`, the same version (and lock file) the eval
# runs themselves use (platform/promptfoo-evals/package.json pins 0.125.1), so the viewer and a
# run agree on the database schema. Built with context platform/promptfoo-evals (like spe-apply's
# sandbox build uses -f: docker build -f platform/instance/evals-view/Dockerfile platform/promptfoo-evals).
# Read-only is nginx's job, not this image's: evals-view, its other service
# (platform/instance/evals-view/nginx.conf), sits in front of it; this container's own port
# (15500) is reachable only through that proxy, which shares its network namespace
# (compose.yml: evals-promptfoo's network_mode: "service:evals-view") -- not a boundary against
# the VM host itself, which can always reach any container's own interfaces.
#
# Pinned to spe_eval_node_version (platform/ansible/inventory/group_vars/all.yml): the same
# Node version the VM installs to run `spe-eval run`/promptfoo there.
FROM node:24.21.0-slim
WORKDIR /app
# No sharing, telemetry or self-update from an SPE instance; the config dir is the bind-mounted
# evaluations volume (compose.yml: evals-promptfoo's /data), not promptfoo's own default.
ENV PROMPTFOO_CONFIG_DIR=/data \
    PROMPTFOO_DISABLE_SHARING=1 \
    PROMPTFOO_DISABLE_TELEMETRY=1 \
    PROMPTFOO_DISABLE_UPDATE=1 \
    PATH=/app/node_modules/.bin:$PATH
COPY package.json package-lock.json ./
# No --ignore-scripts: better-sqlite3 (promptfoo's eval database) needs its install script to
# build its native binding.
RUN npm ci --no-audit --no-fund
# node:24-slim's own "node" user (uid/gid 1000); nothing here is written to /app at run time.
USER node
EXPOSE 15500
# -n/--no: skip the "open in browser?" confirmation and don't open one (there is none here).
CMD ["promptfoo", "view", "--port", "15500", "--no"]
