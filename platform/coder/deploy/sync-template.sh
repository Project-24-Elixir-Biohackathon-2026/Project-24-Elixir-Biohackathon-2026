#!/usr/bin/env bash
# Pull the repo, push the Coder template when it changed, rebuild the static
# site (landing page and threat catalog), and keep one template per branch
# named template/<name>. Run by sperange-sync.timer on the portal VM, so
# configs and threats merged to the branch show up within minutes, without
# GitHub needing access to the VM.
#
# Environment (from /etc/sperange/sync.env):
#   SPE_REPO_DIR       repo checkout, e.g. /home/ubuntu/sperange
#   SPE_BRANCH         branch to follow, e.g. main
#   SPE_TEMPLATE_NAME  Coder template name, e.g. spe-testbed
#   SPE_AGENT_URL      Coder URL as seen from the SPE VMs, e.g. http://10.0.2.50:7080
#   CODER_URL, CODER_SESSION_TOKEN   Coder API access (long-lived token)
#   SPE_SITE_DIR       where the site is built, the Caddyfile's root (e.g.
#                      /srv/sperange-site); default $SPE_REPO_DIR/platform/site/dist
#   SPE_BRANCH_TEMPLATE_PREFIX   branch template/<name> -> template <prefix>-<name>;
#                      default spe
#   SPE_BRANCH_DIR     worktrees of those branches; default $SPE_REPO_DIR/../sperange-branches
set -euo pipefail
cd "$SPE_REPO_DIR"
git fetch --quiet origin "$SPE_BRANCH"
git checkout --quiet "$SPE_BRANCH"
git merge --quiet --ff-only "origin/$SPE_BRANCH"

# The site: cheap, so built on every run; a failure is logged, never fatal
# (needs python3-yaml and mkdocs-material).
if ! python3 platform/site/build.py --out "${SPE_SITE_DIR:-$SPE_REPO_DIR/platform/site/dist}"; then
  echo "site build failed; the previous build stays in place" >&2
fi

head=$(git rev-parse HEAD)
state="$SPE_REPO_DIR/.git/sperange-pushed"
if [[ ! -f $state || $(cat "$state") != "$head" || ${1:-} == --force ]]; then
  coder templates push "$SPE_TEMPLATE_NAME" \
    --directory platform/coder/template \
    --variable "spe_ansible_dir=$SPE_REPO_DIR/platform/ansible" \
    --variable "coder_agent_url=$SPE_AGENT_URL" \
    --name "$(git rev-parse --short HEAD)" \
    --message "$(git log -1 --format=%s)" \
    --yes
  echo "$head" > "$state"
fi

# --- one template per branch template/<name> ---------------------------------
# A pushed branch template/<name> becomes the template <prefix>-<name>, built from
# a worktree of that branch (its Ansible code, its repository commit on the VMs);
# a later push updates it. When the branch is deleted, the template is deleted
# too, unless workspaces still use it; then it stays until they are gone.
# Workspaces made from the main template are not affected by any of this.
prefix=${SPE_BRANCH_TEMPLATE_PREFIX:-spe}
branch_dir=${SPE_BRANCH_DIR:-$SPE_REPO_DIR/../sperange-branches}
mkdir -p "$branch_dir"
git fetch --quiet --prune origin '+refs/heads/template/*:refs/remotes/origin/template/*'
declare -A wanted=()
while read -r sha ref; do
  [[ -n $sha ]] || continue
  name=${ref#refs/remotes/origin/template/}
  if [[ ! $name =~ ^[a-z0-9][a-z0-9-]{0,27}$ ]]; then
    echo "branch template/$name: the name must be lowercase letters, digits and hyphens, 28 characters at most; skipped" >&2
    continue
  fi
  wanted[$name]=1
  wt="$branch_dir/$name"
  if [[ -d $wt ]]; then
    git -C "$wt" checkout --quiet --detach "$sha"
  else
    git worktree add --quiet --detach "$wt" "$sha"
  fi
  # Not in git: the installed collections, and the run archives (one place for all).
  for d in collections output; do
    ln -sfn "$SPE_REPO_DIR/platform/ansible/$d" "$wt/platform/ansible/$d"
  done
  bstate="$branch_dir/.pushed-$name"
  if [[ -f $bstate && $(cat "$bstate") == "$sha" && ${1:-} != --force ]]; then
    continue
  fi
  subject=$(git log -1 --format=%s "$sha")
  coder templates push "$prefix-$name" \
    --directory "$wt/platform/coder/template" \
    --variable "spe_ansible_dir=$wt/platform/ansible" \
    --variable "coder_agent_url=$SPE_AGENT_URL" \
    --name "$(git rev-parse --short "$sha")" \
    --message "$subject" \
    --yes
  coder templates edit "$prefix-$name" \
    --display-name "template/$name" \
    --description "From branch template/$name: $subject" \
    --yes >/dev/null
  echo "$sha" > "$bstate"
done < <(git for-each-ref --format='%(objectname) %(refname)' 'refs/remotes/origin/template/')

for bstate in "$branch_dir"/.pushed-*; do
  [[ -f $bstate ]] || continue
  name=${bstate##*/.pushed-}
  [[ -n ${wanted[$name]:-} ]] && continue
  # Deleted here, or already deleted by hand: either way the branch's leftovers go.
  if coder templates delete "$prefix-$name" --yes >/dev/null 2>&1 \
     || ! coder templates versions list "$prefix-$name" >/dev/null 2>&1; then
    rm -f "$bstate"
    git worktree remove --force "$branch_dir/$name" 2>/dev/null || true
    echo "template $prefix-$name removed (branch template/$name is gone)"
  else
    echo "template $prefix-$name: branch template/$name is gone but the template still has workspaces; kept" >&2
  fi
done
