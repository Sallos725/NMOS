# NMOS Status

## Current phase

**Release `v0.2.0` (2026-09-28), the first milestone (`docs/ROADMAP-1.0.md`), at the owner's request.** Stage 4
(knowledge and secrets, Phase 10) complete, with Stage 5 (Phases 11–12) and Stage 6 so far (Phase 13, Phase 14 steps
1–5) from `main`: secrets and memory modes, open business and causes, relationship pairs, summaries in `<Story>` and
`<Cast>`, owner repairs and the lock, canon sources, names and facts. Extractor `extract-v13`, normalizer `clean-v3`,
packet policy `packet-v8`, migrations 0021–0026. Phase 14 step 6 (canon facts measured, real-host smoke) followed on
`main`, then Phase 15 (complete 2026-09-29): `packet-v9` and a 4,000-token default budget (ADR 0049), M0 +6 cases
needing memory; 70 % of production recalls went without vectors (K34), now shown in the Status tab.

**Phase 17 — Model-call cost and fallback outcomes: approved 2026-09-29, complete 2026-09-30, not released.** Spec
`docs/phases/PHASE-17.md` (C4 and C5 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`): the tokens each model call of
the worker used (extraction, summaries, canon reads; embeddings as input tokens), as the provider reports them and
never estimated, stored with the row they produced; totals per chat and generation in the Inspector and one line in
the Status tab, no money; the HUD tells "injected, lexical only" (K34) and "injected (reused)" apart and says what
background work produced. One migration. The owner accepted every proposed answer (Q1–Q7), and moved the embeddings'
usage from the job (pruned after 7 days) to each embedded chunk; no release. Step 2 (ADR 0051, D61, migration
0027): `ChatModel.complete_metered` and `Embedder.embed_metered` read the response's `usage`; each extraction, canon
read, summary and embedded chunk keeps its call's usage (NULL before the migration, `{"calls": 0}` without a call);
the archive carries it. Nothing is shown yet (step 3). The hosted check (Q7, `gemma4:31b-cloud` through Ollama, the owner's choice): three
calls recorded the input and output tokens of each response's `usage` exactly, and Ollama's own count of the same
prompts agreed (46/51, 50/86, 55/150); the provider names the model `gemma4:31b`. The local embedding check waits
for a model that is not production's request-path embedder. Step 3: `GET /v1/conversations/{id}/coverage?usage=true`
totals the chat's usage per generation (calls, calls reported, input / output / cached / reasoning tokens, results
from before recording), discarded results included; the HUD's polls leave it out. A "Model usage" section on the
Inspector's conversation page, and one line in the panel's "This chat" card. A new plugin build. Step 4: the HUD
says "· lexical only" when the recall's vectors fell back (K34) and "· reused" for a cached packet, in the injected
style; background work that added facts or summaries ends with "✓ facts +N · summaries +M" (the coverage view's new
`produced` counts, compared from when the work was first seen), else "✓ Processing done". On the isolated PocketRisu
v1.13.0 (stub models; the query embedding held past a 150 ms timeout): "✓ 기억 주입 (639자) · 어휘 검색만", on the
second reroll "… · 재사용 · 어휘 검색만", "✓ 사실 1개 추가" after a turn's extraction, and the Status-tab and Inspector
usage. A new plugin build. Step 5 (`docs/perf/model-usage.md`): recorded usage equals the provider's on a local
model too (an isolated CPU Ollama: `qwen2.5:0.5b`, cached input included, and `all-minilm` embeddings); request-path
latency at 10,000 messages unchanged (p50 301.6 → 301.1 ms); an evaluation copy at schema 0025 restores through
migration 0027 with usage "not recorded" and round-trips byte for byte. Phase 17 complete.

**Phase 18 — Recall by the words that matter: approved and complete 2026-09-30, not released.** Spec
`docs/phases/PHASE-18.md`: a keyword lexical route beside the whole-message one (ADR 0052, D15 amended, D62) and
`packet-v10` excerpts that grow from their best sentence (ADR 0053, D63; before, two sentences, a median of 69
characters at every budget). Step 2 done: lexical recall found a candidate for 30 % of evaluation queries. Step 3: the
keyword route (up to four words, each looked up alone, a word in more than 200 messages or half the chat dropped,
25 ms a word within the lexical budget; keyword-only excerpts that repeat a secret left out). Step 4: `packet-v10`,
the default, grows an excerpt by up to four sentences within its length; at 4,000 on M0 v2, +6 cases needing
memory without vectors and a median excerpt of 98 characters. Step 5: on 34 of the owner's recorded
requests (read-only, counts only) it placed 24 excerpts without vectors where `packet-v9` placed none, and no secret
or thread `packet-v9` would not; the isolated PocketRisu v1.13.0 injected a grown excerpt the keyword route found;
latency +11.9 ms p50 at 10,000 messages (+29 ms for a question of four common keywords alone, accepted); K39 (grown
excerpts carry replaced values) and K40 (a short keyword with a particle attached is not found) recorded
(`docs/perf/lexical-recall.md`).

**Phase 16 — Export and restore (Stage 6, part 3): approved and complete 2026-09-29 but for the owner's phone check (K38), not released.** Spec
`docs/phases/PHASE-16.md`: an "NMOS Archive" (`.nmos.zip`: a manifest and one JSON Lines file per table) of the
whole install or chosen chats, with the ledger, canon, the owner's input, recorded requests and settings without
secrets, by default the model's work too (embeddings optional); restore into an install without those chats, same or
newer NMOS, never merged; export from the panel as well as a command, restore a command. Host evidence first (can the
plugin's frame save a file). The owner accepted every proposed answer; no release. Step 2 done (`docs/HOST-FACTS.md`
"Saving a file from the plugin frame", H21): on v1.13.0 the frame saves a Blob (Chromium and Firefox; mobile not yet
observed) and `nativeFetch` carries a 30 MB binary body whole on both routes; a link to the file breaks the panel, so
Export saves a Blob. Step 3 (ADR 0050, D60): the NMOS Archive and its export: `GET /v1/archive`, `python -m
nmos_sidecar.archive export`, and the panel's **Export this chat** (Inspector) and **Export everything** (Settings);
one read-only snapshot, the ledger, canon, the owner's input, recorded requests and generations always, settings
for the whole install, the model's work by default, embeddings when asked; any credential refuses the export. A new
plugin build; no migration. Step 4 (ADR 0050 amendment 1): `python -m nmos_sidecar.archive restore [--check]`: every
file checked first; refused for a newer archive or a conversation already here (never merged); the archive's schema
built in a scratch schema, rows loaded, later migrations applied, copied in with ids and timestamps kept (shared
sequenced ids moved past the install's own when taken, with the recorded requests' refs); a whole install restored
into a fresh one re-exports to the same bytes and replays the same; a Phase 13 archive restores as the upgrade would.
Step 5 (`docs/perf/archive.md`): on copies of the two measured chats (schema 0025, migrated on restore) every table
equal, every recorded request compiled the same, M0 and the secret gate identical, rebuilds equal; the production-sized
copy exports in 2.6 s (15.3 MB with embeddings, 2.1 MB without) and restores in 2.9 s; a real-host smoke of both
Export buttons on v1.13.0. Not tried on a phone (K38).

**Phase 14 — Verification and Repair, part 2: canon sources (Stage 6): approved 2026-09-28, complete 2026-09-29.** Spec
`docs/phases/PHASE-14.md`: the character card, the lorebooks, the persona and the author's note as
immutable sources of each chat; names from canon; canon facts read by the extraction model as their own projection
(the message extractor unchanged), superseded by the story from the turn it says something new; contradictions in
"Needs attention"; a canon lock. Host evidence first, on the owner's PocketRisu v1.13.0. Export/restore is Phase 16 (Q0; renumbered 2026-09-29).
The owner accepted every proposed answer; no release. Step 2 done (`docs/HOST-FACTS.md` "Canon sources", H19,
`docs/perf/canon.md`): every canon source is readable on v1.13.0, the card only off the request path (reading it
clones the chat, 82–93 ms at 10,000 messages); sample 2's lorebook keys cover six given names (K31). Step 3 (ADR 0045,
D55, migration 0025): canon kept per chat as immutable revisions and manifests, a request recording its manifest
and the keys its prompt held (it replays with its own canon), uploads in the background, a "Canon" section in the
Inspector; a new plugin build. Step 4 (ADR 0046, D56): a lorebook entry's keys become aliases of the one
character they name (K31); on sample 2 with its canon the given-name probes find their fact 2 of 3 (0 before), M0
unchanged. Step 5 (ADR 0047, D57, migration 0026): a `canon` generation reads the card, the persona, the note and each
lorebook entry once a prompt held it; its facts are before turn 0 and the story supersedes them; a story that changes
who someone is or how two stand is listed in "Needs attention" with the owner's choices; `fact_lock` keeps a canon fact
or a correction current; a canon fact whose text the prompt held is not sent again; a new plugin build (the switch,
the lock button, macro-aware "held"). Step 6 (`docs/perf/canon.md`, "Evaluation"; ADR 0047 amendment 1): on both
measured chats with their canon, M0 and the secret gate unchanged case by case; canon took 12 and 66 model calls (26 on
production); only relationships are listed as conflicts with canon now (the owner's choice: the identities listed were
the same one in two languages, K37); latency with a 200-entry lorebook read whole +33.7 ms, accepted (K36); an upgrade
fixture from Phase 13 `main`; a real-host smoke on v1.13.0 passed and found an Inspector display bug (fixed).

**Owner request (2026-09-28), outside the Phase 14 steps: NMOS off for one chat** (ADR 0048, D58). The plugin arg
`disabled_chats` lists chats whose requests pass through untouched (nothing synced, uploaded or retrieved; what NMOS
keeps stays). Switched from the chat input's ☰ menu and a "This chat" card at the top of the panel's Status tab; the
panel also opens from the sidebar's ☰ menu. A new plugin build; no migration. Plugin tests pass; the real-host smoke
(the two menus, the arg surviving a reload and an update) is not yet run.

**Owner request (2026-09-28): a new icon.** NMOS's own SVG line icon (an N with a memory node, `src/icon.ts`) replaces
🧠 in the three menus and before "Recalling memory…" in the progress display. A new plugin build. Source reading and
a local DOMPurify check say the host keeps it (`docs/HOST-FACTS.md` "Plugin icons"); the real-host look is not yet
checked.

**Phase 13 — Verification and Repair, part 1 (Stage 6): complete (2026-09-28), not released.** Spec
`docs/phases/PHASE-13.md`: the owner repairs memory in the panel (close or reopen a thread, retract or correct a
fact, mark a secret found out, split two names), stored as owner input that survives rebuilds and new extractor
generations and finds its target by what it says; a "Needs attention" queue per chat. Canon sources are Phase 14
and export/restore Phase 15. The owner answered every question with the recommended answer; no release. Step 2 done
(`docs/perf/repair.md`): the owner confirmed NMOS's lists (50 of 59 open threads ended, 6 of 14 kept secrets found out,
2 never kept); on `main` all 40 M0 packets carry a thread the owner closed. Step 3 (ADR 0044, D54, migration 0024):
owner repairs as owner input, found by what their target says; threads closed or reopened and secrets found out or
kept, through the API, listed in the Inspector. Step 4: facts retracted or corrected, two names split (K8). Step 5:
the panel's repair buttons (bulk close, undo, splits on an entity page) and each chat's "Needs attention" list; the
plugin build changed. Step 6 (`docs/perf/repair.md`): with the owner's decisions made as repairs, no thread the
owner closed reaches a packet on either measured chat (113 lines in 40 packets and 45 in 17 before); M0 27 of 28
(one more) and 5 of 12, the second chat's 17 cases unchanged; the secret gate 6 of 6 with `<Story>` back in all six
scenes, judged by the owner's list (the owner's decision: words of a secret the character found out are told, not
forbidden); an upgrade from every fixture and a real-host smoke pass (a thread closed in the panel leaves the next
packet, undo brings it back). K8 and K23 are rewritten to what remains. One criterion is missed and the owner
accepted it: retrieve at 10,000 messages is +7.0 ms p50 over Phase 12 `main` with 100 fact repairs (the spec allows
+5; +1.7 with none, about +2 with the owner's own mix). A first run was +66 ms; the fact repairs' reads were fixed.

**Phase 12 — Narrative Engine, part 2 (Stage 5): complete (2026-09-28), not released.** Spec
`docs/phases/PHASE-12.md`: scene summaries of 8-turn windows and a story so far, as a rebuildable `summarize`
projection written by the extraction model; secrets left out and checked, no `<Story>` in narrator mode; a `<Cast>`
block of each scene character's state from facts; `packet-v8` with `<Story>` in at most 30% of the budget; new M0
cases whose answers lie outside the prompt window. The owner answered every question with the recommended answer;
no release is decided. Done: step 1 (spec); step 2, 12 owner-confirmed M0 cases whose answers lie outside the
prompt window, 2 of 12 on `main` (`docs/perf/m0-baseline.md`); step 3, the summary projection (ADR 0042, migration
0023), off by default and not yet in packets; step 4, secrets in the summary prompt and a read-time check
(`docs/perf/summaries.md`: `gemma4` 18/24, `deepseek` 24/24; `gemma4` wrote a secret twice, both held by the
read-time check); step 5, `packet-v8` with `<Story>` and `<Cast>` (ADR 0043), summaries on by default and the default
memory budget 2,000 (owner: the story did not fit 30 % of 800). M0 with `gemma4` extraction: 2 → 5 of the 12 new cases,
26 of 28 as before, nothing forbidden placed. Two faults found on the owner's chat and fixed: a finished goal in an
unrelated packet, and a secret stated after its summary (ADR 0042 amendment 2). The secret gate passes 6 of 6 with a
stricter check in front of the character a secret is kept from (amendment 3). Step 6: the Inspector shows each
summary's state and why one is not used, and a character's `<Cast>` state and open goals. Step 7: the deterministic
cases, an upgrade from Phase 11 `main` and a real-host smoke pass (`docs/perf/summaries.md`, "Acceptance"); two faults
found and fixed (ADR 0042 amendment 4: a long append left the story unwritten; a request's `<Story>` read cost about
180 ms at 10,000 messages, now about 10). One criterion is not met, and the owner accepted it: retrieve at 10,000
messages is +13.1 ms p50 over Phase 11 `main` with a summary for each of 624 windows (the spec allows +10). With
Phases 11 and 12, Stage 5 of the roadmap is done on `main`. The owner decided no release for now and chose Stage 6
next: Phase 13 is current (below).

**Phase 11 — Narrative Engine, part 1 (Stage 5): complete (2026-09-28), not released.** Spec
`docs/phases/PHASE-11.md`: the M0 evaluation on real chats (a restored backup, read-only), relationship history
per pair (K24), goal, question, threat and debt threads with a lifecycle, and explicit links, in one extractor
generation (`extract-v13`). The owner answered every question with the recommended answer; no release is decided.
Part 2 (summaries, character state) is Phase 12. Done: steps 1–3 (spec; M0 on a restored backup,
`docs/perf/m0-baseline.md`; relationship pairs, the persona's full name and `packet-v5`, ADR 0038, K24's direction
case closed). M0: 5 → 7 of 12; on the 28 cases the owner confirmed later, 13 → 15. Steps 4–5 (`extract-v13`,
ADR 0039, migration 0022; one pull request, since the prompt's OPEN THREADS need the read side): synthetic tier
`gemma4` 41/42, `deepseek` 42/42; M0 on the copy re-extracted with it 17 of 28, no category worse than the baseline
(`docs/perf/extract-v13.md`). The first 12 cases had stopped it on one wording; the owner then confirmed 28.
Step 6 (ADR 0040, `packet-v6`): stated causes in the packet and linked in the Inspector. M0's scoring now counts
answers the prompt's own last messages hold (`docs/perf/m0-baseline.md`): 23 → 26 of 28, and of the 9 cases that
need memory 5 → 7. Step 7: the Inspector's Relationships section per pair and threads by kind. Step 8: every
thread kind opened, ended, deleted and edited back in the memory evaluation (53 of 53), a real-host smoke on
PocketRisu v1.13.0, an upgrade from Phase 10 `main`, retrieve +1.2 to +4.7 ms p50 at 10k. One criterion is partly
met, and the owner accepted it: goals end (9 of 48 on the owner's chat) but 37 stay open (K23; closing a thread by
hand is Stage 6, `docs/perf/extract-v13.md`).

Outside the phase (found in the Phase 11 real-host smoke; owner decision 2026-09-28): `packet-v7`, the default, numbers
an excerpt's `turn` and a state item's `as_of_turn` by the turn of their message, as facts and threads are numbered
(ADR 0041, D51); earlier policies and their traces are unchanged. The compose files pass the packet policy empty, so a
compose install gets the sidecar's default (they had pinned `packet-v4`).

**Phase 10 — Knowledge and Secrets (Stage 4): complete (2026-09-27), not released (owner).** Spec
`docs/phases/PHASE-10.md` (every acceptance criterion met), ADRs 0033–0037, D43–D47, migration 0021. A secret is
what the story keeps from someone and ends when they find it out (`extract-v12`); what someone in the scene does
not know goes in a `<Private>` section with a rule; a chat can choose strict or a first-person narrator; the
Inspector shows a chat's secrets. Along the way, by the owner's requests: the default reserve 800, a Status-tab
notice with the budget that holds what was left out and `packet-v4` (ADR 0036), and the plugin build check (ADR
0037, K19). Evidence: `docs/perf/secrets-eval.md` — on the owner's real scenes, 48 replies of Opus 5.5 and Gemini
3.1 Pro with no leak, the holder remembering the secret as often as the pilot's best condition once a thread
ranking fault was fixed (ADR 0019 amendment 1). Released in `v0.2.0` (2026-09-28).

**Phase 9 — Accountable Packets: complete (2026-09-26), released in `v0.1.0-beta.19`.** The owner asked for
the work on a new branch and approved the merge after review. Spec `docs/phases/PHASE-9.md` (Track B, B6
narrowed to recording and budgeting what the packet holds), ADR 0027, D39, migration 0020. Every request
records a ledger of what its packet offered and held, with provenance. `packet-v1` keeps room for the
best excerpt. A recorded request replays as of its time (story position and knowledge time), and
`tools/replay_packets.py` compares policies offline. Echo reports what the next reply reused. Evidence:
`docs/perf/phase9-packets.md`, including a real-host smoke and an answer probe with two response models.
Every acceptance criterion is met. No phase is current.

**Phase 8 — Event Participants: complete (2026-09-24), released in `v0.1.0-beta.15`.** Spec
`docs/phases/PHASE-8.md` (Track B, B3 narrowed to typed participants of `event`, `goal`, `knows`,
`destroyed`), approved with the recommended answer to every question (Q1–Q5). Typed participants
(ADR 0021, D33), `extract-v8`, migration 0017, `resolve-v2`, Inspector "With" and "Takes part in".
Evidence: `docs/perf/phase8-extraction.md`. Every acceptance criterion met; the Phase 7 minor-event
scene "chores" (1/3 with `extract-v8`, no event extracted; ten more runs: v7 3/10, v8 4/10) was accepted
by the owner as not a regression. No phase is current. Next: the rest of Track B, B3, not authorized.

**Phase 7 — Promise Threads and Event Salience: complete (2026-09-24), released in
`v0.1.0-beta.14`.** Spec `docs/phases/PHASE-7.md` (Track B, B3 narrowed to promise threads and event salience),
approved with the recommended answer to every question (Q1–Q5). Promise threads (ADR 0019), event cap
and salience (ADR 0020), `extract-v7` with `fulfilled` and OPEN PROMISES, migration 0016, D32, Inspector
promises. Evidence: `docs/perf/phase7-extraction.md` (real-model tier, fact-read latency, real-host
smoke, upgrade from a `v0.1.0-beta.13` database).

**Phase 6 — Item Transitions and Conflicts: complete (2026-09-24), released in `v0.1.0-beta.13`.**
Spec `docs/phases/PHASE-6.md` (Track B, B2), approved 2026-09-24 with the recommended answer to every
question (Q1–Q5). One whereabouts per item (ADR 0016), `destroyed` with `extract-v6` and
`disputed="true"` (ADR 0017), D30, Inspector item timelines and conflicts. Every acceptance criterion
met: `docs/perf/phase6-extraction.md` (real-model tier, fact-read latency, real-host smoke, upgrade from
a `v0.1.0-beta.12` database).

**Phase 5 — Entity Identity and Semantic Assertions: complete (2026-09-24), released in
`v0.1.0-beta.12`.** Spec `docs/phases/PHASE-5.md`, ADRs 0012–0014 (0012/0013 amended by the owner after
the real-model tier), D26/D27, D7/D20 amended. Every acceptance criterion met: deterministic cases in
CI, the real-model tier on the release candidate and a real-host smoke (`docs/perf/phase5-extraction.md`),
latency (`docs/perf/scale.md`), a real upgrade from a `v0.1.0-beta.10` database. Next: Track B, B2
(transition verifier), not authorized yet.
Outside the phase (owner decision 2026-09-24, D28): an optional progress display on the chat screen,
released in `v0.1.0-beta.12`.
Outside the phase (owner-reported bug 2026-09-24, ADR 0023, D34, released in `v0.1.0-beta.16`): the persona's name as
the host reports it is the persona, so `{{user}}` and a named persona are one entity; the plugin
reads it with the host's "db" permission, asked at load (real-host check: `docs/HOST-FACTS.md`, "Persona
name"). Migration 0018, `resolve-v3`.
Outside the phase (owner report 2026-09-25, ADRs 0024 and 0025, D35 and D36, released in `v0.1.0-beta.17`): `extract-v9` labels an
event major by what it changes, in action or in words (admissions, speech-level and address changes, a relationship
allowed, an incident others must deal with), names a character shown without a name by a `?` description and links
it when a later turn reveals the name; the owner can join two names of a chat by hand in the panel (migration 0019,
`resolve-v4`). Evidence: `docs/perf/extract-v9.md`.
Outside the phase (owner request 2026-09-24, ADR 0022): Google Vertex AI service-account keys for the
extraction LLM, released in `v0.1.0-beta.15`. Mocked token exchange in CI; verified against real Vertex on
2026-09-26 with the owner's key (`google/gemini-3.8-flash`: connection test, extraction, recall; ADR 0022).
Outside the phase (owner report 2026-09-26, ADR 0026, D37, released in `v0.1.0-beta.19`): characters forgot settled things (a 반말 agreement
went back to 존댓말). Reproduced read-only on the owner's database: in a crowded scene the fact ranking was decided by
`known_by` lists, so trivia took the four facts a 600-token packet holds. Now how the cast stand with each other
(`relationship`, `feels_toward`) and major events come first among equal mentions, standing facts take the budget before
threads, and the trace and Inspector show how many facts fit. Read side only.
Outside the phase (owner decision 2026-09-26 on `docs/proposals/SPEECH-AND-ADDRESS.md`, recommended answers; ADR 0028,
D38, released in `v0.1.0-beta.19`): `extract-v10` adds `addresses`, how one character speaks to and calls another, per direction, only when
the story settles it (a slip is not recorded); it ranks with relationships. Evidence: `docs/perf/extract-v10.md`
(owner's model on the owner's chat: 18/18 settled turns, 0/3 on the slip, 0/12 routine; synthetic 21/21 on two models;
isolated real host).
Outside the phase (owner request 2026-09-25, released in `v0.1.0-beta.18`): the Status tab shows the exact text the last request
injected ("Show the injected memory"), held in the plugin's memory only. Real-host check on
`ghcr.io/pocketrisu/pocketrisu:latest` at 1280 px and 390 px; the text matched what the stub model received.

Outside the phase (owner decision 2026-09-27, unreleased): `extract-v11`, made before its milestone at the owner's
request. It carries the two queued audit items: the prompt says notes outside the story are not evidence (A-12;
an OOC note in a reply 0/3 → 3/3 ignored, the control kept 3/3) and the registry drops `Predicate.epistemic`
(A-14). Evidence: `docs/perf/extract-v11.md`. Memory-shaped markup still became a fact, because the normalizer
stripped the tag and kept the text; the owner then chose a normalizer generation (2026-09-27, unreleased):
`clean-v3` drops NMOS's own memory markup with its content (K27; `docs/perf/memory-poisoning.md`).

Outside the phase (owner decision on K26, 2026-09-26, ADR 0032, D42, unreleased): the default packet policy
is `packet-v2`, which estimates Korean at 1.2 tokens a character instead of 1.5, so more of the reserve is
used. Evidence: `docs/perf/token-estimate.md` (three tokenizers, a replay of the owner's recorded requests,
an answer probe with two response models).

**Phase 0 — complete (2026-09-22).** Phase 0A exit criteria and all Phase 0B acceptance criteria are met.

**Public beta `v0.1.0-beta.21` (2026-09-26), public repository and image.** The rest of the 2026-09-26
audit: deadline warnings in the plugin, a host check without a token (ADR 0030), the per-message extraction
window retired (ADR 0031), startup backfills committed step by step, one environment for sidecar and worker,
upgrade tests from beta.7/beta.16 databases, Vertex AI verified; no schema or generation change.
`v0.1.0-beta.20` (2026-09-26): Three fixes from the
2026-09-26 audit: a broken emoji no longer stops a chat's sync (A-01, ADR 0029), a reply quoting the
memory tag no longer turns memory off (A-02), and one bad job no longer stops the worker (A-04).
`v0.1.0-beta.19` (2026-09-26): Phase 9 (accountable
packets: packet ledger, `packet-v1`, echo, as-of replay), standing facts first (ADR 0026) and speech
level and forms of address (`extract-v10`, ADR 0028); migration 0020.
`v0.1.0-beta.18` (2026-09-25): The Status tab shows the
memory the last request injected (plugin only).
`v0.1.0-beta.17` (2026-09-25): `extract-v9` (salience by
what an event changes, unnamed characters and revealed names, ADR 0024) and owner entity links (ADR
0025); migration 0019.
`v0.1.0-beta.16` (2026-09-24): Bug fix: a named persona is
the persona (ADR 0023, above); migration 0018.
`v0.1.0-beta.15` (2026-09-24): Phase 8 (above), Google
Vertex AI keys for extraction (ADR 0022), an Inspector status-window example; migration 0017.
`v0.1.0-beta.14` (2026-09-24): Phase 7 (above); migration
0016. `v0.1.0-beta.13` (2026-09-24): Phase 6 (above) and O5
resolved: superseded vectors pruned (ADR 0015), full-manifest host observations compacted losslessly
(ADR 0018); migration 0015. `v0.1.0-beta.12` (2026-09-24): Phase 5 (above), `clean-v2`
normalizer (inline images no longer read as story), optional progress display (D28); migration 0014.
`v0.1.0-beta.11` (2026-09-24): Phase 5 step 1: a new LLM
model re-extracts only each chat's recent window and older turns keep the previous model's facts (ADR
0014, D20 amended); fact and state reads no longer stall for seconds after an edit, reroll or swipe in a
long chat. No schema change. `v0.1.0-beta.10` (2026-09-23): Track A stabilization:
verified append fast path and incremental plugin manifest (ADR 0010, migration 0013), default request
deadline 3 s after a real-host check at 5k/10k/15k messages (D24), one current holder per item (ADR
0011, D25), broad lexical queries stopped at 200 matches, and a deterministic memory evaluation
(`docs/perf/eval-baseline.md`). Evidence: `docs/perf/scale.md`. `v0.1.0-beta.9` (2026-09-23): the owner can delete a
conversation from the panel's Inspector, raw messages included (ADR 0009, D23, invariant 1 amended;
migration 0012). Evidence: `docs/perf/scale.md` (delete timings, sync A/B), real-UI host check in
ADR 0009. `v0.1.0-beta.8` (2026-09-23): facts are extracted per turn
(user message + reply) with turn-counted backfill, and each chat has "extract all history" and
"rebuild memory" in the Inspector (ADR 0008, D7/D17 revised, D22; migration 0011). Evidence:
`docs/perf/turn-extraction.md` (model comparison, real-UI host check), `docs/perf/scale.md` re-check.
`v0.1.0-beta.7` (2026-09-23): main-generation gating no
longer assumes a preset layout (ADR 0001 amendment 2): presets that add instructions after the user's
turn got no memory in beta.6 and earlier. `v0.1.0-beta.6` (2026-09-23): the Inspector opens inside
the NMOS panel (Status | Inspector | Settings tabs): PocketRisu sandboxes plugins without
`allow-popups`, so the beta.5 link could not open a tab (ARCHITECTURE H15). One PocketRisu settings
entry. `v0.1.0-beta.5` (2026-09-23) was a packaging release: multi-arch image (`linux/amd64`,
`linux/arm64`), `:latest` tag on every release, Inspector "—" for never-enabled features, README
screenshots. `v0.1.0-beta.4` (2026-09-23) was the
stabilization release (issues #6–#19) and UI review on top of `v0.1.0-beta.3` (2026-09-22). Phases 1–3 complete. Phase 4 soft
subset complete (knowledge scope `public` / `limited` / `unknown`, D19, `docs/phases/PHASE-4.md`).
Plugin settings panel configures providers, embeddings, tuning and parser rules. Validated with a
real RisuRealm sim bot and a fresh install from release assets. Still outside the beta: hard
character-POV isolation, threads/causal links, verifier, MCP (Phase 5+; not authorized).

**beta.4 contents.** Projection generations and coverage (D20, ADR 0006), normalized text (D21),
knowledge scope (ADR 0007), CORS PUT, large-chat envelope (`docs/perf/scale.md`), release gate, no
search of unverifiable beta.3 vectors (#17), immediate provider disable (#18), strict config types
(#19), one NMOS panel (status/settings tabs, chat-menu entry, Korean/English), Inspector labels.
Known issues (current list): `docs/KNOWN-ISSUES.md`.

## What exists

| Part | Where | State |
|---|---|---|
| Host evidence | `docs/HOST-FACTS.md`, `fixtures/host/a14c911-2026-09-22/` | S1–S14 (S13 N/A), Q1–Q8, 0B runtime findings |
| Architecture | `ARCHITECTURE.md` | H1–H21, D1–D63, O2/O3/O4/O5 resolved |
| Sidecar + worker | `apps/sidecar` (Python 3.12, FastAPI, psycopg 3, httpx) | sync, hybrid recall, state, facts, inspector; `nmos-worker` jobs |
| Schema | `migrations/0001`–`0027` | source layer, state, extraction/jobs, embeddings, config, knowledge, normalized text, projection generations, knowledge scope, conversation labels, turn extraction, conversation delete, append rows, assertion semantics, observation compaction, event salience, assertion participants, conversation persona, owner entity links, packet ledger, conversation memory mode, thread outcome and cause, summaries, owner repairs, canon, canon facts and lock, model-call usage |
| Plugin | `adapters/pocketrisu-plugin` → `dist/nmos-pocketrisu.js` | gating (D13), manifest, sync, recall injection, fail-open |
| Deployment | `docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example` | postgres 16 + sidecar |
| Tests | `apps/sidecar/tests` (722), `adapters/pocketrisu-plugin/test` (162; DOM code under `happy-dom`) | all passing; the M0 real-chat evaluation is `docs/perf/m0-baseline.md` (28 owner-confirmed cases; 9 need memory: 5 before Phase 11, 7 now) and, on a second chat, `docs/perf/m0-sample2.md` (17 cases; 8 of the 13 that need memory); deterministic memory evaluation `docs/perf/eval-baseline.md` (with budget pressure since Phase 9) |
| Performance | `docs/perf/phase0.md`, `docs/perf/scale.md` | Phase 0 targets met. Since beta.10: sidecar append 715 → 156 ms and plugin manifest 175 → 17 ms at 10k (ADR 0010). Real host (PocketRisu v1.12.0): ≈1.5 s at 5k, ≈2.7 s at 10k, ≈4.1 s at 15k per warm generation (host stall after `getChatFromIndex`); default deadline 3 s covers up to ≈10k without extraction and embeddings (D24); with both on (15k facts, 15k vectors) 10k takes ≈3.2 s (A-09); K3 on the real host (2026-09-27): rerolls and last-reply swipes stay on the fast path, an edit of an older message at 10k takes 3.6–3.8 s |
| Known issues | `docs/KNOWN-ISSUES.md` | K1–K40 (K10 resolved; K33–K38 recorded 2026-09-29, K39–K40 in Phase 18) current as of `v0.2.0` and Phase 18, each with workaround and tracking (host, Track B stage); resolved limitations listed |
| Next work | `docs/ROADMAP-1.0.md`, `docs/proposals/` | Road to 1.0: stages 4–8 of the original roadmap, one release each (draft, R1–R6 open). Track A (stabilization) A1–A5 done; Track B B1 = Phase 5, B2 = Phase 6 (complete); B3 narrowed = Phase 7 (complete); the rest of B3 and B4–B7 not authorized |
| Decisions | `docs/adr/0001`–`0053` | gating, branches, token (optional), recall scoring, hybrid tuning, projection generations, knowledge scope, turn extraction, conversation delete, append fast path, item holder; Phase 5: entity identity, assertion semantics, generation fallback; superseded projection retention; Phase 6: item whereabouts, item end; observation compaction; Phase 7: promise threads, event salience; Phase 8: typed participants; Vertex AI service-account keys; persona name; salience by change and revealed names; owner entity links; standing facts first; speech level and address; text PostgreSQL cannot store; host check without a token; per-message window retired; Korean token estimate; Phase 10: secrets, private section, memory mode, budget pressure; plugin build check; Phase 11: relationship pairs, open business, stated causes; Phase 12: scene summaries, story and cast; Phase 13: owner repair; Phase 14: canon sources, names from canon, canon facts and lock; NMOS off for one chat; Phase 15: a packet that fills its budget; Phase 16: NMOS Archive; Phase 17: model-call usage; Phase 18: keyword lexical recall, excerpts that fill their length |
| Phase specs | `docs/phases/PHASE-0.md`–`PHASE-18.md` | 0–3 met; 4 soft subset met; 5–10 met; 11 met but one criterion partly (owner accepted); 12 met but the latency criterion missed by 3 ms (owner accepted); 13 met but the latency criterion missed by 2 ms (owner accepted); 14 met but the latency criterion missed by 29 ms with a 200-entry lorebook read whole (owner accepted); 15 met (packet fill); 16 met but for the owner's phone check (K38, open); 17 met; 18 met (latency measured over the benchmark's questions, owner accepted) |
| Retro | `docs/phases/PHASE-0-RETRO.md` | |
| Audits | `docs/audits/NMOS-AUDIT-2026-09-26.md` + `-REVIEW.md` | A-01 (ADR 0029, D40), A-02, A-04 fixed in `v0.1.0-beta.20`; A-03, A-05 (ADR 0030), A-06, A-07, A-08, A-10 (verified), A-15 (ADR 0031), A-16 fixed, A-09 measured with deadline warnings, A-12 measured (K27), in `v0.1.0-beta.21`; after it, A-11 fixed (access log), A-13 documented (K28), A-18 documented (K21), A-19 fixed (plugin tests); A-17 is a caution (K15), not a defect; A-12's prompt line and A-14 in `extract-v11`, and A-12's markup half in `clean-v3` (both unreleased) |

## Evidence status (Phase 0A)

| Scenario | Status | Fixture/evidence |
|---|---|---|
| S1–S12 | run | `fixtures/host/a14c911-2026-09-22/` (S4b, S8b variants) |
| S13 | not executable on `a14c911` (no group chat); N/A accepted by owner | HOST-FACTS S13 |
| S14 | run (100 / 1,000 messages) | `…/*S14*` |

## Audit follow-up (2026-09-27)

A read-only audit of `69800f0` is recorded in [Original vision → stable](proposals/ORIGINAL-VISION-TO-STABLE-2026-09-27.md) (Korean, at the owner's request; proposal only). Its isolated API/worker probes reproduced a reveal being applied to a different secret after an old source edit (G1), the K29 history-extraction workaround queuing no work for already compiled turns (G2), and malformed assertion output being recorded as complete (G3). The 421 sidecar and 104 plugin tests that existed then passed and did not cover these cases.

- **Fixed on `main` (unreleased):**
  - G1: a reveal links to its listed turn only while that turn reads as it did (ADR 0033 amendment 2).
  - G2: "Extract all history" also extracts again the turns extracted before an earlier turn's secret, so K29's workaround works (amendment 2).
  - G3: an answer without an `assertions` list fails the job (retried, then counted failed) instead of counting as compiled.
  - Each is covered in `test_secrets.py` / `test_extraction.py`; they were strict xfails before the fix.
- Exposure before the fix: G1 and G2 came with Phase 10, which production runs from `:edge`; no tag has them. G3 dates from `e21e9cd` (Phase 2) and is in every release up to `v0.1.0-beta.21`.
- No extractor generation change: the prompt, registry and normalizer are unchanged; the listed turn's hash is stored with the hints only. Reveals extracted before the fix carry no hash and keep the old linking.

The audit's other findings (G4–G17) stay proposals. No phase authorization or release decision was made.

A second analysis the same day (an external document the owner shared, not in the repository) was reviewed against
the code. Its confirmed defects are fixed on `main` as bug fixes (CHANGELOG, Unreleased): a saved API key is sent
only to the host it was saved for, the plugin's host reads count against the request deadline and its budget and
deadline arguments are capped, the worker waits for the sidecar's migrations, a recall reads the chat as its
request had it, and the plugin's DOM code has tests (`happy-dom`, owner-approved dev dependency). Not adopted: its
advice to tag `0.2.0` now (it missed G1–G3), a Dockerfile `HEALTHCHECK` (the worker runs the same image),
removing the assertion's `epistemic` field (it is live: `certainty="implied"`; A-14 removed only
`Predicate.epistemic`), and a plugin update channel (on hold by the owner; the host offers an update only for a
higher `//@version`). Its Stage 5–8 items remain phase work; next, once G1–G3 were fixed: M0 and Stage 5 (owner,
2026-09-28).

## Open owner decisions

- O1 — relationship to MIRRA / VEIL.
- O5 — resolved 2026-09-24: superseded vectors and text pruned (ADR 0015, D29), full-manifest host
  observations compacted losslessly (ADR 0018, D31), everything else on abandoned worldlines kept.
- Phase 9 (accountable packets): complete, released in `v0.1.0-beta.19`.
- Phase 11 (Stage 5, part 1): approved 2026-09-28 with the recommended answers (Q0–Q8); complete 2026-09-28, the
  goal pile-up criterion partly met and accepted (owner); release on hold.
- Phase 12 (Stage 5, part 2: summaries, character state): approved 2026-09-28 with the recommended answers
  (Q1–Q9, `docs/phases/PHASE-12.md`); complete 2026-09-28, the latency criterion missed by 3 ms and accepted
  (owner). No release for now (owner, 2026-09-28).
- Phase 13 (Stage 6, part 1: owner repair and a needs-attention queue): approved 2026-09-28 with the recommended
  answers (Q0–Q9, `docs/phases/PHASE-13.md`); complete 2026-09-28, the latency criterion missed by 2 ms and accepted
  (owner); no release.
- Phase 14 (Stage 6, part 2: canon sources): approved 2026-09-28 with every proposed answer (Q0–Q10,
  `docs/phases/PHASE-14.md`); export/restore is Phase 16 (Q0; renumbered 2026-09-29); complete 2026-09-29, the latency
  criterion missed (+33.7 ms with a 200-entry lorebook read whole) and accepted (owner); no release.
- Phase 15 (a packet that fills its budget; P1 of `docs/proposals/PUBLIC-RELEASE-AND-BENCHMARK.md`): approved
  2026-09-29 with the proposed answers (Q0–Q8, `docs/phases/PHASE-15.md`); before export/restore, after Phase 14
  step 6; default budget 4,000, fixed; no release.
- Phase 16 (Stage 6, part 3: export and restore): approved 2026-09-29 with every proposed answer (Q0–Q9,
  `docs/phases/PHASE-16.md`); an Export button in the panel too (owner); complete 2026-09-29; no release.
- Phase 17 (model-call cost and fallback outcomes; C4 and C5 of `docs/proposals/IDEA-SURVEY-2026-09-29.md`): the
  owner chose 2026-09-29 to run it after Phase 16; approved 2026-09-29 with every proposed answer (Q1–Q7,
  `docs/phases/PHASE-17.md`); complete 2026-09-30 (`docs/perf/model-usage.md`); no release.
- Phase 18 (recall by the words that matter): approved 2026-09-30, complete 2026-09-30
  (`docs/perf/lexical-recall.md`); no release. The owner accepted the latency criterion as measured over the
  benchmark's questions and chose to measure a lower keyword threshold (K40) separately: measured 2026-09-30, it found less; 0.8 kept. Phase 19+ (Stages 7–8): not
  authorized.
- K26 — decided 2026-09-26: change the estimate (1.5 → 1.2 tokens per non-ASCII character, `packet-v2`,
  ADR 0032, D42); the default reserve stays 600. Raised to 800 on 2026-09-27 (owner; ADR 0035).
- Release cadence — decided 2026-09-26, revised 2026-09-27: one release per roadmap stage, urgent patches
  only in between, `:edge` built from every `main` merge (`AGENTS.md` §13).
- Roadmap to 1.0 — decided 2026-09-27: not stable until stages 4–8 of the original roadmap are done
  (`docs/ROADMAP-1.0.md`). Open: R1 order, R2 public benchmark, R3–R6 stage scope.
- Stage 4 — decided 2026-09-27: first milestone (R1); recommended answers to Q1–Q5; no release yet. Spec
  `docs/phases/PHASE-10.md`, approved 2026-09-27. Tentative: a holder's own slip is direction, not a leak.

## Queued for the next extractor generation

A change to the extraction prompt or registry makes a new generation and re-extracts each chat's recent
window at the provider's cost (ADR 0006, 0014). Owner-approved changes wait for the next one, so the cost is
paid once (owner decision 2026-09-26). A-12 and A-14 shipped in `extract-v11` (owner decision 2026-09-27,
`docs/perf/extract-v11.md`). Queued:

- **Synthetic prompt examples** (owner decision 2026-09-28, PR #149). The extraction prompt's `because`
  example and `addresses` examples (`extraction.py`) and the example value in the `addresses` description
  (`predicates.py`) come from the owner's chat. Replace them with synthetic examples (the persona 타쿠미 /
  Takumi, as in the tests); the repository is public.
- **Evidence found in the turn for every assertion** (owner decision 2026-09-29, C2 of
  `docs/proposals/IDEA-SURVEY-2026-09-29.md`). Reveals already need their quoted evidence in the target turn
  (trigram containment 0.7, PHASE-10); apply the same check to every assertion, parking one whose evidence is not
  found as `pending` ("evidence not in the turn"). Measure with M0 and the rate of newly parked rows before it ships.

## Public release checklist (done 2026-09-23)

| Item | State |
|---|---|
| Security notice (plain-text API keys in `app_config`, no internet exposure, token for LAN/Tailscale) | done — README "Security", guide.ko "보안 주의" |
| README/guide claims scoped to the tested PocketRisu build | done |
| Private IP in experiment notes generalized (`192.168.x.x`) | done |
| Outdated agent docs (`CODEX-PROMPT.md`, `STARTER-CONTENTS.md`) archived to `docs/reference/`; `AGENTS.md` current; `PHASE-4.md` added | done |
| Commit author email in git history | done — `main` and tags `v0.1.0-beta.1`–`3` rewritten to the GitHub noreply address; later commits use it |
| Repository description/topics | done |
| Repository visibility → Public | done 2026-09-23 (after `v0.1.0-beta.4`) |
| GHCR `nmos-sidecar` package visibility → Public | done 2026-09-23 (owner) |
| Anonymous `docker pull` + fresh install from release assets | done 2026-09-23 — `0.1.0-beta.4` and `beta` pulled without login (same image); release compose file up with migrations 0001–0010; release plugin file installed in PocketRisu `a14c911`, synced a 37-message chat, Inspector showed it as *bot · chat* in Korean |
| README screenshot (settings panel or Inspector) | done 2026-09-23 — `docs/images/` (panel Status tab, Inspector), taken on the `v0.1.0-beta.4` release stack |
