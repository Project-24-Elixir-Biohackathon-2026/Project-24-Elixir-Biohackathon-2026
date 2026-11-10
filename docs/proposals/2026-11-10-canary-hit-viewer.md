**Status:** *specified*: superseded by `docs/specs/2026-11-10-canary-hit-viewer.md` (PR #74), which settles the
open questions below in its *Rulings on the open questions*.

# Canary hits, visible: a live detector for participants and a global view for the portal owner

**Where it came from.** A discussion with the user on 2026-11-09/10 about how BioHackathon participants can
contribute to the canary evaluation ladder (verify the hardening levels, vary and discover attacks), and what
they lack to do it. Read against `main` at `ab9537c`.

Claims are marked **verified** (read in the code or docs named) or **unverified** (reasoned, or from general
knowledge of a project not read here).

## The problem

A participant's workspace gives them the chat (the scenario's user) and a terminal on the whole instance VM (the
lab operator). Neither tells them whether an attempt **leaked a canary**. Canary detection exists only inside the
promptfoo evaluation, so "did my attack work?" has no answer in the workspace, and the portal owner has no view
of what all participants found.

What exists (verified):

- **The detector is `platform/promptfoo-evals/metrics.py`**: it loads `canaries.json` from the hand-off
  directory and matches each token literally, as a whole word, in the answer, the trace (tool arguments and
  results) and the state diff, reading each text as given, unescaped and JSON-decoded (`_texts`, `_word`,
  `_found`). Reasons name the canary's type and file, never the token. Six metrics: `canary.answer`,
  `canary.touched` (file canaries only), `canary.sent`, `canary.delivered`, `injection.followed`, `key.leak`.
- **`canaries.json` lives on the controller** (the portal VM for Coder workspaces,
  `platform/coder/template/main.tf:351`), not on the instance. Its hash-only twin,
  `canaries.manifest.sha256` (`sha256 <tab> type` per token, `roles/handoff/tasks/main.yml:71`), is labelled
  "safe to share with detection tooling" but nothing reads it.
- **The archive** copies chats, AG-UI journals, the agent's run log and the canary record to
  `/data-share/runs/<time>_<instance>/` on workspace stop (`platform/coder/README.md`); nothing scans it.
- **Live sources on the instance**: AG-UI session journals are appended per event during a run
  (`copilotkit-chat/lib/recorder.ts`); the agent's `runs.jsonl` is written once per run, at its end
  (`spe_agent/runlog.py`); Open WebUI saves a chat at the end of each response (unverified for v0.13.0); the
  sandbox's log and the eval test receiver's log (`spe_eval_sink`) are live.
- **The portal VM already runs a Coder-authenticated service**, the run report (`platform/report/`): it knows
  the viewer from Coder's session cookie; owners write their report, Coder owners (admins) write any, everyone
  logged in reads. A natural home, or model, for the admin view.
- **The L5 airlock** (`spe_agent/airlock.py`) is a hardening control, not a detector: it matches classes and
  never reads the canary record. The detector must stay separate from it.

## What the user asked for

1. **Participants see their own hits**, live while they work, with enough **trace metadata to find when it
   happened** even if they missed the moment: the session and run, the time, the prompt (user message) that
   started the run, the tool call and the tool result in which the canary appeared, which canary (type and
   file) and the canary itself.
2. **The Coder owner has an admin panel**: a global view of every detected issue across all workspaces.

## Direction from the discussion (to be settled in the spec)

- **One scanner, outside the agent, as the source of truth.** It reads the live sources above (frontend-agnostic:
  AG-UI and Open WebUI, plus the sandbox and receiver logs, which also catch what never passes through the agent,
  e.g. a workflow container sending data out). Report-only: it never changes what the model sees or says.
- **One matching rule**, shared with `metrics.py` (a common module, or a copy held equal by a test), so the live
  flag, the archive scan and the promptfoo score agree.
- **Severity follows the metrics**: exposed to the agent (`canary.touched`), leaked in the answer
  (`canary.answer`), sent out (`canary.sent` / `delivered`). Metadata canaries met in ordinary listings are
  counted quietly, not flashed (see `BACKLOG.md` *Next*, the study-id-in-DRS-names question).
- **Display, in order**: (a) a findings page served by the scanner as one more Coder app next to the chat,
  live over SSE, with browser notifications; (b) inline marks in the AG-UI chat (chips on the tool group and
  answer, the leaked span highlighted by offsets, a session tally, "Add to report" pre-filling a finding in the
  run report); (c) an Open WebUI filter function showing a toast, only if (a) is not enough (Open WebUI's event
  emitter `notification` type is unverified for v0.13.0).
- **Admin view on the portal VM**: findings from every workspace, live or from the archive.
- **Literal matching is a stated limit**: an encoded, split or paraphrased canary is not seen; the page says so.

## Open questions for the spec

- **Showing the token.** The user wants "the actual canary" in the participant's trace. The participant can read
  every canary from the terminal anyway, and it is their own instance; but every committed file and report reason
  so far carries type and file only. Which views show the value (participant's own panel? admin?), and does the
  plaintext record then go onto the instance, or does the instance get only the hash manifest (match by hashing
  candidate words) with the value shown from the matched text itself?
- **Where the scanner runs**: on each instance (close to the live sources, then reports to the portal), or on
  the portal VM (pulling from instances), or both. How findings reach the admin view, and survive workspace stop.
- **Ladder runs**: is the scanner off (`spe_*` switch) on ladder instances so the UI is identical to what
  promptfoo measures, or harmless there?
- **Upstream**: participants' workspaces follow upstream `main`, so the feature is only useful once ported; the
  spec should be written for `docs/specs/` (upstream's layout, fork-only links avoided: `AGENTS.md`, *Overrides*).
