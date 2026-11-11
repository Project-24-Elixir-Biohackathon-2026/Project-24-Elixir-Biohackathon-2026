#!/usr/bin/env bash
# Assemble the spe-experiments template directory before it is pushed or planned:
# Terraform's fileset() sees only files inside it, so the experiments, mitigations,
# injection fixtures and spe's run-ansible.sh are copied in (git-ignored here).
# Stale copies are replaced, so a deleted experiment or mitigation disappears.
# TEMPLATE.yml (experiments/ and mitigations/) is a copy-and-fill-in document, not an experiment or
# mitigation to offer on the form, so it is never copied in (check_experiment.py and validate.py
# exclude it from the catalog the same way).
# Usage: assemble.sh <repo root> [<template dir>]   (default: this script's directory)
set -euo pipefail
repo=${1:?usage: assemble.sh <repo root> [<template dir>]}
dir=${2:-$(cd "$(dirname "$0")" && pwd)}

rm -rf "$dir/experiments" "$dir/mitigations" "$dir/catalog" "$dir/run-ansible.sh"
mkdir -p "$dir/experiments" "$dir/mitigations" "$dir/catalog/injections"
for f in "$repo"/experiments/*.yml; do
  [ "$(basename "$f")" = TEMPLATE.yml ] || cp "$f" "$dir/experiments/"
done
for f in "$repo"/mitigations/*.yml; do
  [ "$(basename "$f")" = TEMPLATE.yml ] || cp "$f" "$dir/mitigations/"
done
cp "$repo/platform/ansible/catalog/injections/fixtures.json" "$dir/catalog/injections/fixtures.json"
cp -p "$repo/platform/coder/template/run-ansible.sh" "$dir/run-ansible.sh"
