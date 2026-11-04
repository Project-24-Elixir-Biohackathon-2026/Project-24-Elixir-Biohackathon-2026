# 2026-11-04: the upstream AG-UI package, cut and pushed

**Unit:** the rest of `BACKLOG.md` *Next*, *Upstream PR for the AG-UI package*. Read with
`docs/handoffs/2026-11-04T1111Z-upstream-package-start.md` (the PR text draft, the #9 steps after the user opens
the PR); this note supersedes its "e2e checklist" and 1216Z's re-run.

**Done.** `contrib/agui-package` on `origin`, cut from `upstream/main` (`d2a6232`), at `bf152a8`:

1. `152b78e` the 157 project files that differ from our `main` (`bdb93a6`), as one package; exclude check ok.
2. `89c68c0` fork-only references: `getting-started.md`'s key row (no `docs/knowledge` link), clarification 3
   (no `docs/superpowers` spec, "now §15"), the spec README says its PR numbers are the fork's; *Latest
   clarification* 21 → 23 (also stale on our `main`).
3. `2a0be9b` `platform/coder/README.md` and `platform/README.md`: both frontends on every workspace (overview,
   diagram, archive row, walkthrough, "All data" preset, the smoke test now checks the AG-UI chat and `agui/`).
4. `bf152a8` upstream's `AGENTS.md` by hand: the spec directory, its features, `npm test`.

Tests on the branch, all green: `validate.py` (5 entries), site build, `platform/dev/tests` 96 passed, agent 239
passed, promptfoo 18 passed, `--syntax-check` create/archive/destroy/verify, chat UI `npm run build`, `npm test`
248 passed. The compaction doc rewrite (PR #16 finding 10) needed nothing: the package's spec replaces upstream's
stale *History*.

**Decided with the user (2026-11-04): no e2e re-run.** Apart from the fork-only files the branch differs from
`bdb93a6` in six Markdown files only (`git diff --stat origin/main contrib/agui-package` minus the exclude list),
so #36, #38 and #40 hold for it. Instead, a **cheap smoke test of the reviewer's path** (the user said yes):
one portal workspace (pre-approved, one at a time; `coder-e2e-test-approved` memory), in it
`cd ~/sperange && git fetch https://github.com/thodkatz/elixir-biohackathon-2026-test.git contrib/agui-package
&& git checkout FETCH_HEAD && spe-apply all`, then one AG-UI chat with a tool call, and `archive.yml` showing
its `agui/` part. The screenshots can come from that same workspace (neutral prompts, never canary names).

**Next, in order:**
1. The smoke test above; stop the workspace after.
2. Screenshots 01–03 (1111Z's draft), pushed to the `pr-assets` branch under `agui-package/`.
3. The PR text: 1111Z's draft with the branch name `contrib/agui-package` (compare link, `git fetch` line,
   asset paths), the TODOs filled (testing: checks on `bdb93a6` whose code the branch carries unchanged, the
   test counts above, the smoke test). Post it as a fork issue (`docs/guides/contributing-upstream.md`, step 5;
   `upstream-pr-text-in-issue` memory), then stop: the user opens the PR on kraatz and closes #9.
4. Also owed by the BACKLOG item, on our `main`: the *package port* path in `docs/guides/contributing-upstream.md`
   (what this cut did: `git checkout origin/main -- <paths>` from `upstream/main` when it is an ancestor, the hand
   edits, the grep), and *Latest clarification* 23 in our spec README.

Gotcha this session: `git fetch` failed with `Too many open files`; `docs/knowledge/workspace-too-many-open-files.md`'s
fix (drop the inode cache) worked at once.
