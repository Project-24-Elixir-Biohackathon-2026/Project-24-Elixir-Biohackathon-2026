#!/usr/bin/env bash
# Pull the repo, push the Coder templates (spe and spe-experiments) when they changed, rebuild
# the static site (landing page and threat catalog), and keep one template per branch named
# template/<name> or experiment/<name>. Run by sperange-sync.timer on the portal VM, so configs,
# threats and experiments merged to the branch show up within minutes, without GitHub needing
# access to the VM.
#
# A failure pushing spe-experiments, or syncing one template/<name> or experiment/<name>
# branch, is logged to stderr with the template name and does not stop the rest (spe's own
# push, first, is not wrapped this way and fails the script as before). The failed item's
# state file is left untouched, so it is retried on the next run; the script still exits
# non-zero at the end if anything failed, so the timer/journal shows it.
#
# Environment (from /etc/sperange/sync.env):
#   SPE_REPO_DIR       repo checkout, e.g. /home/ubuntu/sperange
#   SPE_BRANCH         branch to follow, e.g. main
#   SPE_TEMPLATE_NAME  Coder template name for spe, e.g. spe-testbed
#   SPE_AGENT_URL      Coder URL as seen from the SPE VMs, e.g. http://10.0.2.50:7080
#   CODER_URL, CODER_SESSION_TOKEN   Coder API access (long-lived token)
#   SPE_SITE_DIR       where the site is built, the Caddyfile's root (e.g.
#                      /srv/sperange-site); default $SPE_REPO_DIR/platform/site/dist
#   SPE_EXPERIMENTS_TEMPLATE_NAME   Coder template name for spe-experiments; default spe-experiments
#   SPE_BRANCH_TEMPLATE_PREFIX   branch template/<name> -> template <prefix>-<name>;
#                      default spe
#   SPE_EXPERIMENT_TEMPLATE_PREFIX   branch experiment/<name> -> template <prefix>-<name>;
#                      default spe-x
#   SPE_BRANCH_DIR     worktrees of those branches; default $SPE_REPO_DIR/../sperange-branches
set -euo pipefail
force=${1:-}
failed=0
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
if [[ ! -f $state || $(cat "$state") != "$head" || $force == --force ]]; then
  coder templates push "$SPE_TEMPLATE_NAME" \
    --directory platform/coder/template \
    --variable "spe_ansible_dir=$SPE_REPO_DIR/platform/ansible" \
    --variable "coder_agent_url=$SPE_AGENT_URL" \
    --name "$(git rev-parse --short HEAD)" \
    --message "$(git log -1 --format=%s)" \
    --yes
  echo "$head" > "$state"
fi

# spe-experiments: fileset() sees only files inside its directory, so assemble.sh copies the
# experiments, mitigations, injection fixtures and spe's run-ansible.sh in (git-ignored there)
# before every push. Same head-changed rule as spe, its own state file. A failing assemble.sh
# or push here is contained below (sync_spe_experiments's status is checked, not left to
# set -e), so a persistent failure here does not block the template/ and experiment/ branches.
#
# Bash gotcha: calling a function in a tested position (`if ! f; then`) suppresses errexit
# for the function's *entire* body, not just its own exit status, so a failing command inside
# it would otherwise be silently ignored and execution would fall through to the next line.
# Every risky command below is therefore checked explicitly with `|| return 1`.
exp_template_name=${SPE_EXPERIMENTS_TEMPLATE_NAME:-spe-experiments}
exp_state="$SPE_REPO_DIR/.git/sperange-pushed-experiments"
sync_spe_experiments() {
  platform/coder/experiments-template/assemble.sh "$SPE_REPO_DIR" || return 1
  if [[ -f $exp_state && $(cat "$exp_state") == "$head" && $force != --force ]]; then
    return 0
  fi
  coder templates push "$exp_template_name" \
    --directory platform/coder/experiments-template \
    --variable "spe_ansible_dir=$SPE_REPO_DIR/platform/ansible" \
    --variable "coder_agent_url=$SPE_AGENT_URL" \
    --name "$(git rev-parse --short HEAD)" \
    --message "$(git log -1 --format=%s)" \
    --yes || return 1
  echo "$head" > "$exp_state"
}
if ! sync_spe_experiments; then
  echo "$exp_template_name: assemble.sh or push failed; left for the next run" >&2
  failed=1
fi

# --- one template per branch, two kinds -------------------------------------
# A pushed branch template/<name> becomes the template <prefix>-<name>, built from spe's
# template in a worktree of that branch (its Ansible code, its repository commit on the VMs).
# A pushed branch experiment/<name> becomes <exp-prefix>-<name>, built the same way from
# spe-experiments' template, with assemble.sh run in that worktree so the branch template's
# form always matches the code it builds with. Either way, a later push updates it, and when
# the branch is deleted the template is deleted too, unless workspaces still use it; then it
# stays until they are gone. Workspaces made from spe or spe-experiments directly are not
# affected by any of this.
#
# template/<name> keeps the worktree and state-file paths this script used before the
# experiment kind existed ($branch_dir/<name>, $branch_dir/.pushed-<name>), so deploying this
# changes nothing for branches already synced in production. experiment/<name> uses the "x."
# marker, a separator the template/<name> regex below can never contain (no dot allowed), so
# its paths ($branch_dir/x.<name>, $branch_dir/.pushed-x.<name>) cannot collide with any
# template/<name> path, and each kind's cleanup pass below only ever touches its own files.
branch_dir=${SPE_BRANCH_DIR:-$SPE_REPO_DIR/../sperange-branches}
mkdir -p "$branch_dir"

# Build/update one branch's worktree, assemble if needed, and push + edit its template if the
# commit changed. The caller (sync_branch_kind) calls this in a tested position (`if !
# sync_one_branch ...; then`), which in bash suppresses errexit for this whole function body
# (not just its own exit status, see the comment above sync_spe_experiments) — so every risky
# command here is checked explicitly with `|| return 1`, to return immediately on the first
# failure rather than silently falling through to the push. The caller logs that and moves on
# to the next branch instead of aborting the whole run, and leaves the state file alone so
# this branch is retried next time.
# $1 kind, $2 name_prefix (the worktree/state marker: "" for template, "x." for experiment),
# $3 the Coder template name prefix, $4 the template subdir inside the worktree, $5 "yes" to
# run that subdir's assemble.sh in the worktree first, $6 the branch name, $7 its commit.
sync_one_branch() {
  local kind=$1 name_prefix=$2 tmpl_prefix=$3 subdir=$4 need_assemble=$5 name=$6 sha=$7
  local wt="$branch_dir/$name_prefix$name"
  if [[ -d $wt ]]; then
    git -C "$wt" checkout --quiet --detach "$sha" || return 1
  else
    git worktree add --quiet --detach "$wt" "$sha" || return 1
  fi
  # Not in git: the installed collections, and the run archives (one place for all).
  local d
  for d in collections output; do
    ln -sfn "$SPE_REPO_DIR/platform/ansible/$d" "$wt/platform/ansible/$d" || return 1
  done
  if [[ $need_assemble == yes ]]; then
    # A branch cut before the experiments template existed would fail here on every run,
    # turning the service red and hiding real failures: skip it, as an invalid name is.
    if [[ ! -x $wt/$subdir/assemble.sh ]]; then
      echo "branch $kind/$name: its commit has no $subdir/assemble.sh; skipped" >&2
      return 0
    fi
    "$wt/$subdir/assemble.sh" "$wt" "$wt/$subdir" || return 1
  fi
  local bstate="$branch_dir/.pushed-$name_prefix$name"
  if [[ -f $bstate && $(cat "$bstate") == "$sha" && $force != --force ]]; then
    return 0
  fi
  local subject
  subject=$(git log -1 --format=%s "$sha") || return 1
  coder templates push "$tmpl_prefix-$name" \
    --directory "$wt/$subdir" \
    --variable "spe_ansible_dir=$wt/platform/ansible" \
    --variable "coder_agent_url=$SPE_AGENT_URL" \
    --name "$(git rev-parse --short "$sha")" \
    --message "$subject" \
    --yes || return 1
  coder templates edit "$tmpl_prefix-$name" \
    --display-name "$kind/$name" \
    --description "From branch $kind/$name: $subject" \
    --yes >/dev/null || return 1
  echo "$sha" > "$bstate"
}

# $1 kind: the ref namespace under refs/heads/<kind>/<name> ("template" or "experiment").
# $2 the Coder template name prefix: <prefix>-<name>.
# $3 the longest name allowed (the first character plus this many more: $3 total).
# $4 the template directory inside the worktree, relative to it.
# $5 "yes" to run that directory's assemble.sh in the worktree before pushing, else "no".
# $6 name_prefix, the worktree/state marker for this kind (see the comment above).
sync_branch_kind() {
  local kind=$1 tmpl_prefix=$2 maxlen=$3 subdir=$4 need_assemble=$5 name_prefix=$6
  local -A wanted=()
  git fetch --quiet --prune origin "+refs/heads/$kind/*:refs/remotes/origin/$kind/*"
  while read -r sha ref; do
    [[ -n $sha ]] || continue
    name=${ref#refs/remotes/origin/"$kind"/}
    if [[ ! $name =~ ^[a-z0-9][a-z0-9-]{0,$((maxlen - 1))}$ ]]; then
      echo "branch $kind/$name: the name must be lowercase letters, digits and hyphens, $maxlen characters at most; skipped" >&2
      continue
    fi
    wanted[$name]=1
    if ! sync_one_branch "$kind" "$name_prefix" "$tmpl_prefix" "$subdir" "$need_assemble" "$name" "$sha"; then
      echo "$tmpl_prefix-$name: branch $kind/$name failed to sync; left for the next run" >&2
      failed=1
    fi
  done < <(git for-each-ref --format='%(objectname) %(refname)' "refs/remotes/origin/$kind/")

  for bstate in "$branch_dir"/.pushed-*; do
    [[ -f $bstate ]] || continue
    raw=${bstate#"$branch_dir"/.pushed-}
    if [[ -n $name_prefix ]]; then
      [[ $raw == "$name_prefix"* ]] || continue
      name=${raw#"$name_prefix"}
    else
      # template's own files never contain a dot (the name regex above forbids it), so any
      # name that does belongs to another kind's marker (e.g. experiment's "x."); skip it.
      [[ $raw != *.* ]] || continue
      name=$raw
    fi
    [[ -n ${wanted[$name]:-} ]] && continue
    # Deleted here, or already deleted by hand: either way the branch's leftovers go.
    if coder templates delete "$tmpl_prefix-$name" --yes >/dev/null 2>&1 \
       || ! coder templates versions list "$tmpl_prefix-$name" >/dev/null 2>&1; then
      rm -f "$bstate"
      git worktree remove --force "$branch_dir/$name_prefix$name" 2>/dev/null || true
      echo "template $tmpl_prefix-$name removed (branch $kind/$name is gone)"
    else
      echo "template $tmpl_prefix-$name: branch $kind/$name is gone but the template still has workspaces; kept" >&2
    fi
  done
}

sync_branch_kind template "${SPE_BRANCH_TEMPLATE_PREFIX:-spe}" 28 platform/coder/template no ""
sync_branch_kind experiment "${SPE_EXPERIMENT_TEMPLATE_PREFIX:-spe-x}" 26 platform/coder/experiments-template yes "x."

if [[ $failed -eq 1 ]]; then
  exit 1
fi
