#!/usr/bin/env bash
# Pull the repo, push the Coder template when it changed, and rebuild the
# static site (landing page and threat catalog). Run by sperange-sync.timer on
# the portal VM, so configs and threats merged to the branch show up within
# minutes, without GitHub needing access to the VM.
#
# Environment (from /etc/sperange/sync.env):
#   SPE_REPO_DIR       repo checkout, e.g. /home/ubuntu/sperange
#   SPE_BRANCH         branch to follow, e.g. main
#   SPE_TEMPLATE_NAME  Coder template name, e.g. spe-testbed
#   SPE_AGENT_URL      Coder URL as seen from the SPE VMs, e.g. http://10.0.2.50:7080
#   CODER_URL, CODER_SESSION_TOKEN   Coder API access (long-lived token)
#   SPE_SITE_DIR       where the site is built, the Caddyfile's root (e.g.
#                      /srv/sperange-site); default $SPE_REPO_DIR/platform/site/dist
set -euo pipefail
cd "$SPE_REPO_DIR"
git fetch --quiet origin "$SPE_BRANCH"
git checkout --quiet "$SPE_BRANCH"
git merge --quiet --ff-only "origin/$SPE_BRANCH"

# The site: cheap, so built on every run; a failure is logged, never fatal
# (needs python3-yaml and python3-markdown).
if ! python3 platform/site/build.py --out "${SPE_SITE_DIR:-$SPE_REPO_DIR/platform/site/dist}"; then
  echo "site build failed; the previous build stays in place" >&2
fi

head=$(git rev-parse HEAD)
state="$SPE_REPO_DIR/.git/sperange-pushed"
if [[ -f $state && $(cat "$state") == "$head" && ${1:-} != --force ]]; then
  exit 0
fi

coder templates push "$SPE_TEMPLATE_NAME" \
  --directory platform/coder/template \
  --variable "spe_ansible_dir=$SPE_REPO_DIR/platform/ansible" \
  --variable "coder_agent_url=$SPE_AGENT_URL" \
  --name "$(git rev-parse --short HEAD)" \
  --message "$(git log -1 --format=%s)" \
  --yes
echo "$head" > "$state"
