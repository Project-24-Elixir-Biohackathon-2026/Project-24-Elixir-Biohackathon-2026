#!/usr/bin/env bash
# Assemble the spe-experiments template directory before it is pushed or planned:
# Terraform's fileset() sees only files inside it, so the experiments, mitigations,
# injection fixtures and spe's run-ansible.sh are copied in (git-ignored here).
# Stale copies are replaced, so a deleted experiment or mitigation disappears.
# Usage: assemble.sh <repo root> [<template dir>]   (default: this script's directory)
set -euo pipefail
repo=${1:?usage: assemble.sh <repo root> [<template dir>]}
dir=${2:-$(cd "$(dirname "$0")" && pwd)}

rm -rf "$dir/experiments" "$dir/mitigations" "$dir/catalog" "$dir/run-ansible.sh"
mkdir -p "$dir/experiments" "$dir/mitigations" "$dir/catalog/injections"
cp "$repo"/experiments/*.yml "$dir/experiments/"
cp "$repo"/mitigations/*.yml "$dir/mitigations/"
cp "$repo/platform/ansible/catalog/injections/fixtures.json" "$dir/catalog/injections/fixtures.json"
cp -p "$repo/platform/coder/template/run-ansible.sh" "$dir/run-ansible.sh"
