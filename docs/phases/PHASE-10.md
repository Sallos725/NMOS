# Phase 10 — Knowledge and Secrets (Stage 4)

> **Status: draft, awaiting the owner's approval of this document (2026-09-27).** Stage 4 of
> `docs/ROADMAP-1.0.md` (original §27–30; Track B, B5 narrowed). The owner chose the recommended answer to every
> question (R1, Q1–Q5) on 2026-09-27 and asked for no release yet. Design: `docs/proposals/STAGE-4-KNOWLEDGE.md`.
> Evidence behind it: `docs/perf/stage4-leak-pilot.md`. Implementation starts only after the owner approves
> this document.

## Questions and answers

| # | Question | Answer (recommended) | Alternatives not taken |
|---|---|---|---|
| R1 | Which roadmap stage comes first? | **Stage 4.** Its inputs exist (knowledge marks, typed participants) and its design is backed by a pilot. The order after it is decided when it is done. | The roadmap's 5 → 6 → 4 → 7 → 8. |
| Q1 | When does a secret end? | **When the story shows the hidden character learning it**: the extraction reports it against the chat's open secrets, and the secret stops applying to that character from that turn. History is kept. | Also by hand in the Inspector (Stage 6, repair). |
| Q2 | Strict mode (only what everyone present knows)? | **Per chat, off by default.** | A global switch; no strict mode. |
| Q3 | How is a first-person chat known? | **A per-chat setting in the panel** (who narrates). | Reading the preset's POV toggle (names and values differ per preset). |
| Q4 | A holder's own slip (a child blurting a secret)? | **Reported separately as a slip, not counted as a leak** (tentative owner decision). | Counted as a leak. |
| Q5 | Which response models measure it? | **Opus 5.5 and Gemini 3.1 Pro**, each paid run's budget agreed with the owner first. | One model. |

Release: none at the end of this phase unless the owner asks (owner, 2026-09-27).

## Goal

A secret stays with its holders. The memory tells the model who knows a fact and, for a secret, whom it is kept
from; a secret the story reveals stops being one. Holders keep the content; the model is told not to voice it
in front of those it is kept from. A chat can choose a strict packet or a first-person narrator.

## Evidence behind the scope

- **The packet works when the data is right.** In the pilot, adding `hidden_from` to one promise (A′) kept it in
  the holder's mind 3 of 3 times with no announcement to the character it was kept from; the same packet
  without it leaked once in 3 (`docs/perf/stage4-leak-pilot.md`).
- **The data is usually not right.** In the owner's longest chat, 90 of 347 facts were `limited`, mostly
  recording who was present; about 15 had `hidden_from`, several on trivia; a secret revealed at turn 21 was
  still hidden at turn 59, next to the fact that the character knew.
- **Withholding costs memory.** Replacing a secret's content (B′) removed every leak and every recollection
  (0 of 4, both models).
- **Models differ.** Opus voices secrets in dialogue, Gemini in narration. Both are measured.
- **The host's own text is out of reach.** With a 150k-token context the transcript carries the secret anyway;
  the packet only decides for secrets older than the host's window.

## In scope

1. **Extraction (`extract-v12`, one generation).**
   - `hidden_from` names a character only when the story shows the fact is **kept from** them (a secret, a lie,
     a surprise, a plan against them). Absence alone is never `hidden_from`; `known_by` still lists who saw,
     heard or was told.
   - **OPEN SECRETS**: the prompt lists the chat's current secrets (fact text, holders, kept from), as it lists
     open promises (ADR 0019). A new predicate `learned` (subject: the character who now knows; value: the
     listed secret exactly as listed) records a reveal in the target turn.
   - The recent window is re-extracted at the provider's cost (ADR 0014); older turns keep their facts until
     "Extract all history".
2. **Secret end (read side, deterministic).** A `learned` assertion on the active worldline ends `hidden_from`
   for that character on the listed secret from its turn on. A later turn marking the character in `known_by`
   of the same fact version ends it too. As-of reads (ADR 0027) respect the turn. Deleting or editing the
   revealing turn restores the secret (invariant 7).
3. **Scene cast.** The characters who act or speak in the last turns (subjects and participants of their
   assertions, Phase 8) plus the persona, computed on the request path from data already read.
4. **`packet-v3` (default; `packet-v2` stays available).** Facts known by everyone in the scene cast, public
   and unmarked facts stay as they are. Others go in a `<Private>` section with their holders and, when set,
   whom they are kept from; the note says holders may act on them and nobody voices them in front of those
   they are kept from unless the story reveals them.
5. **Per-chat memory mode (migration 0021).** `strict` (off by default): lines not known to everyone in the
   scene cast become "something X know and Y is not known to know". `narrator` (none by default; the persona or
   a character of the chat): only public, unmarked and narrator-known lines. Set in the NMOS panel's settings
   for the current chat; read by the sidecar per request; recorded in the trace.
6. **Inspector.** A chat's secrets: holders, kept from, the turn that made it, the turn that ended it and by
   whom; the scene cast and mode of the last request.
7. **Evaluation.**
   - Public, synthetic memory-evaluation cases (in the repository and CI): a kept secret, absence that is not a
     secret, a reveal that ends it, an edit that restores it, strict mode, narrator mode.
   - `tools/eval_secrets.py`: replays requests with a case directory given on the command line. The owner's
     real-chat cases stay outside the repository; reports carry numbers only.

## Out of scope

- Separate model calls per character, or any host orchestration (Stage 8 or later).
- Hiding what the host itself sends: card, lorebook, recent transcript.
- Belief states beyond knows and kept-from (believes, suspects, misremembers) until a case needs them.
- Ending a secret by hand (Q1 alternative; Stage 6), and reading the POV from the preset (Q3 alternative).
- Any release (owner, 2026-09-27).

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; no stale memory in any mode; `packet-v2` still
      reproduces its recorded traces.
- [ ] The new synthetic cases pass deterministically in CI, including a secret restored after its revealing
      turn is edited, and replay of a Phase 9 trace under `packet-v3`.
- [ ] Real-model extraction tier with the owner's extraction model (`gemma4:31b-cloud`), 3 runs per synthetic
      Korean scene: deliberate secrets get `hidden_from` and mere absence does not, and a reveal is reported
      against its listed secret; every miss is listed in the evidence, and any scene below 2 of 3 is shown to
      the owner before the phase closes.
- [ ] On a copy of the owner's database re-extracted with `extract-v12` (read-only against production), the
      revealed secret of the pilot is no longer placed as hidden after its reveal, and the trivia marked
      hidden in the pilot are not marked hidden.
- [ ] Response-model tier on the owner's real-chat cases (outside the repository), Opus 5.5 and Gemini 3.1 Pro,
      budget agreed first: no leak in any case whose fact marks whom it is kept from; the holder remembers the
      secret whenever the scene calls for it (never below the pilot's `packet-v2` rate); slips reported
      separately (Q4).
- [ ] Retrieve latency at 10,000 messages within +5 ms p50 of `v0.1.0-beta.21`.
- [ ] Real-host smoke on an isolated PocketRisu: per-chat mode set in the panel reaches the sidecar and the
      trace; a `<Private>` section reaches the model's prompt.
- [ ] Upgrade from a `v0.1.0-beta.21` database (`tests/test_upgrade.py`).
- [ ] `ARCHITECTURE.md` (decisions from D43), ADRs, README, the Korean guide, KNOWN-ISSUES (K11 rewritten to what
      remains), CHANGELOG (Unreleased).

## Steps (one pull request each)

1. This document, approved.
2. `extract-v12`: prompt rules, OPEN SECRETS, `learned` (ADR for knowledge marks, revising ADR 0007).
3. Secret end on the read side, as-of aware.
4. Scene cast and `packet-v3` (ADR for the packet).
5. Per-chat memory mode: migration 0021, API, panel (ADR for the mode).
6. Inspector.
7. Evaluation: synthetic cases, `tools/eval_secrets.py`, the model tiers (each paid run approved first).
8. Documentation, real-host smoke, upgrade check.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- the extraction model cannot tell absence from secrecy on the synthetic scenes (below 2 of 3 on most);
- ending a secret would need reinterpreting stored rows without a revealing turn;
- the scene cast needs data the sidecar does not have on the request path, or a plugin change beyond the panel
  setting;
- a paid run would exceed its agreed budget;
- `packet-v3` loses a memory-evaluation gold that `packet-v2` reached.
