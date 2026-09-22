# Phase 0A evidence — PocketRisu `a14c911`, 2026-09-22

Real observations recorded by `adapters/pocketrisu-spike/nmos-host-spike.js` v0.2.0 through
`tools/spike_collector.py`. `REPORT.md` is generated from these files by `tools/spike_report.py`.

## How this run was made

| Item | Value |
|---|---|
| Host build | PocketRisu `a14c911fd927a2bf63c8665bae202f29643920b4` (v1.12.0), built from a clean `git archive` of that commit |
| Deployment | isolated container `nmos-spike-pocketrisu`, `--network host`, `PORT=6101`, empty `save/` (owner data untouched) |
| Client | headless Chromium 1223 driven over CDP by Playwright scripts; origin `http://localhost:6101` (secure context) |
| Model | `tools/spike_stub_llm.py` via PocketRisu "Custom API" (OpenAI-compatible), main and auxiliary model |
| Chat | one blank character, chat "New Chat 2" (`26b153b7-…`); S14 used imported synthetic chats |
| Raw bodies | not captured (`include_raw_snapshot = 0`); manifests carry hashes, lengths and `{{specialcomment::…}}` markers only. All message text is stub/synthetic |

Every scenario action was a real UI action in the running host (send, reroll button + confirm,
swipe arrow, "Continue Response", pencil edit, trash → "Remove this message only", message menu →
"Disable Message" / "Cut Messages for AI" / "Branch", page reload, chat export + import, "Auto
Suggest"). Test setup (model URL, plugin install, plugin args) also went through the UI, except
that the scenario label was set with the host's own `__pluginApis__.setArg` and dumps were
triggered through the spike's parent-window `postMessage` hook instead of the settings menu.

Setup and debug captures made before the clean run (a first chat whose generation hung while the
plugin was being reinstalled, dumps taken before an action had actually happened) were discarded
and are not in this directory.

## Scenario index

| Scenario | Action | Files (prefix `20260922T…`) |
|---|---|---|
| warm-up | 3 normal turns to create "old" messages | `warmup__*` |
| S1 | normal send + reply | `S1-before`, `S1__beforeRequest`, `S1__output`, `S1-after` |
| S2 | reroll last reply (confirm "Generate a new message…") | `S2-before`, `S2__beforeRequest`, `S2__output`, `S2-after` |
| S3 | swipe ← on the last reply | `S3-before`, `S3-after` |
| S4 | "Continue Response" with default `useSayNothing = true` | `S4-before`, `S4__beforeRequest`, `S4__output`, `S4-after` |
| S4b | "Continue Response" with `useSayNothing = false` | `S4b-before`, `S4b__beforeRequest`, `S4b__output`, `S4b-after` |
| S5 | edit old user message (index 2) | `S5-before`, `S5-after` |
| S6 | edit old AI message (index 3) | `S6-before`, `S6-after` |
| S7 | delete middle AI message (index 5), "Remove this message only" | `S7-before`, `S7-after` |
| S8 | "Disable Message" on index 4 | `S8-before`, `S8-after` |
| S8b | "Cut Messages for AI" on index 2 (`disabled: 'allBefore'`) | `S8b-before`, `S8b-after` |
| S9 | "Branch" from index 3 | `S9-before` (origin), `S9-after` (branch chat) |
| S10 | page reload; then export chat JSON and import it | `S10-before`, `S10-after` (reload), `S10-import-current-index`, `S10-imported` |
| S11 | "Auto Suggest" (auxiliary `submodel` request) | `S11-before`, `S11__beforeRequest`, `S11-after` |
| S12 | stub forced 2× HTTP 500, then success | `S12-before`, 3× `S12__beforeRequest` (retries), `S12__output`, 1× `S12__beforeRequest` (auto-suggest `submodel`), `S12-after` |
| S13 | group chat | **not executable on this build** — see `docs/HOST-FACTS.md` |
| S14 | imported synthetic 100 / 1,000-message chats; 3 dumps each; hash benchmark; one send on the 1,000 chat | `S14-100-*`, `S14-1000-*` |

Order note: S8/S8b were run before S7, so the S7 manifests already contain the S8 `disabled` flags.

Scenarios S5–S10 produce no `beforeRequest`/`output` observations: those actions do not call the
model and do not fire output listeners. That absence is itself evidence (see HOST-FACTS Q8).
