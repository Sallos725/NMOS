# Phase 33 — Forensic recall, part 1 (Stage 7): the source turn, quoted

> **Status: approved 2026-10-07 (the owner: every question as proposed), the current phase; step 2 done (the baselines,
> `docs/perf/phase33-baseline.md`), step 3 next.** Stage 7 of `docs/ROADMAP-1.0.md` ("Forensic recall";
> original §46, §48, §78; Track B, B6), part 1 of 2 (Q0). Under AGE-10. Until 1.0 a new phase is a Stage 7 item (R7);
> this is the roadmap phase, not a correction phase, and the current one. Phase 32 (the
> Inspector timeline, AGE-39, an exception to R7) runs beside it; Q7 links to its bars once it is merged.

## Why now

Stage 7 is the last roadmap stage before `0.4.0` and the 1.0 gate (R7). Its first done criterion, an exact-quote case
set answered with the source turn, has no path today:

- **No route reads a turn for what was said.** Excerpts come from three routes over raw text (whole-message trigram,
  keywords, vectors over 700-character chunks; fused by RRF) and grow around the sentence that best matches the
  question's words (`packet.grown_excerpt`, ADR 0053). Nothing detects a question about what someone *said*, nothing
  addresses a turn by its number or by "the first night", and an excerpt's `speaker` is the host message's name, not
  the character who spoke. `assertion.evidence` holds checked quotes (PHASE-19 Q3) that never reach the packet.
- **Measured on `v0.3.0`** (the S0–S6 bench of 2026-10-05/06 on `0ace76c`, one run per set, aggregates only):
  memory cases 28 of 37. The real-chat set misses three of ten: a form of address the story used before (what one
  character called another earlier) and two small early details (an object, a person seen once). The set that installs
  NMOS on a 120-turn chat and asks while extraction catches up (S6) answers one of three: the turns not yet extracted
  have no facts, and their excerpts compete for the same slots as everything else.
- **Echo is report-only** (PHASE-9 Q3). There is no measure of the same memory placed request after request, so the
  second done criterion ("overuse measured by echo before and after") has no "before" yet.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q0 | One phase for Stage 7, or two? | **Two.** Phase 33: the forensic path for what was said (Q1–Q4), the turns extraction has not reached (Q5), the Inspector's way back to the source (Q7), and the overuse *baseline* (Q8, measurement only). Phase 34: candidate labels (required, supportive, risky, hidden), the overuse penalty and the activation threshold for supportive memory (§48–49), measured against Q8's baseline. `0.4.0` after Phase 34. | One phase (the penalty would ship without a measured baseline); labels first (nothing to measure them by). |
| Q1 | When does the forensic path run? | **When the user's message carries a speech cue, without a model call.** Speech cues: 말했, 말한, 라고 했, 뭐라고, 했던 말, 대사, 한마디, 물었, 대답했; "said", "say", "told", "asked", "words"; or a phrase in quotes in the message. A turn anchor (`N턴`, "turn N") or a first cue (`FIRST_CUE`, `HISTORY_CUE`'s 첫날, plus 첫날 밤, "the first night", "the first day") narrows it (Q3). Every other message takes today's path, unchanged. The cue list is recorded in the policy and reported per case. | A model call to classify the question (C8 of `IDEA-SURVEY-2026-09-29.md`; cost and latency on the request path, not part of Stage 7's scope); the forensic path on every message (its slots displace facts). |
| Q2 | What does the forensic path add? | **A quote route and a `<Quote>` line.** The route searches the quoted speech inside messages (text between “”, "", 「」, 『』 of at least four characters) with the question's keywords, lexically (§78: exact quotes prefer lexical over embeddings), over the whole chat. A candidate scores by keyword hits, by its speaker matching a character the question names, and by Q3's anchor. At most two quotes reach the packet, as `<Quote turn="N" speaker="X">` with the quoted words verbatim and one sentence of narration around them, 600 characters at most each, placed above the excerpts. The speaker is the one character named in the quote's sentence or the sentence before it; otherwise the message's speaker when the message is the user's persona; otherwise the attribute is left out rather than guessed. | Whole-message excerpts only (today; the quote is often not the anchor sentence); attribution by a model (a model call); `assertion.evidence` as the quote (a model's choice of span, and only for turns that produced a fact). |
| Q3 | How are time anchors read? | **Turn numbers and "first" only.** `N턴` / "turn N" restricts candidates to turns N−2…N+2. A first cue orders candidates oldest first and keeps the earliest third of the chat ahead of later matches. Story days and nights ("그날 밤", "the third day") are not resolved: there is no day segmentation, and a guess would point at the wrong turn. | Story-day segmentation from scene summaries (Stage 5 summaries do not mark days reliably); no anchors (a "first night" question gets the most recent match). |
| Q4 | How do fast, normal and forensic paths relate, and what does the forensic path cost? | **Normal is today's `gather`; fast is the floor it already falls back to when a route times out or is too broad (state, canon, rules, cast: no new code, now named in the ledger); forensic is normal plus the quote route.** The quote route has its own lexical slice (150 ms) inside the plugin's deadline and abstains on timeout or a too-broad match, as the lexical routes do (D15). The ledger records which path ran. Bar: forensic p95 at most 150 ms above normal p95 at 10,000 messages (`docs/perf/scale.md` method). | A tier picked by remaining deadline (adds a moving part the measurement cannot pin); a slower background forensic answer for the next turn (the answer is needed now). |
| Q5 | What does the packet give the turns extraction has not reached? | **Their excerpts are judged as raw evidence, not as restatements, and they may take one more slot.** While a chat's first-sight window is being extracted (D74, ADR 0065), an excerpt from a turn with no extraction yet is not dropped for restating a fact (there is no fact of that turn to restate), and the excerpt limit rises by one for such turns, inside the same character budget. The ledger marks them `unextracted`. Measured on S6 (Q10). | Leave it (S6 stays at one of three while catching up); hold the packet until extraction finishes (blocks the user). |
| Q6 | The form of address used before? | **Diagnosed first, by replay.** The address history already prints inline ("; before, turn N: …", ADR 0038 amendment 1) when a history cue is present. Step 2 replays the missed real-chat case and the S1 address cases to find whether the fact, the cue or the line is missing. A recall cause is fixed under `packet-v13`; an extraction cause is recorded as a known issue for a later generation (no extraction change in this phase). | Fix blind (the cause is unknown); a new history route (more than the case needs if the line exists). |
| Q7 | What is evidence traversal in the Inspector? | **A source-turn page and links to it.** `/inspector/c/{conv}/t/{turn}`: the turn's raw text with every checked evidence quote of its facts highlighted, the facts it produced (current and superseded, by generation), the packet lines that used it, and links to the turns before and after. Links lead there from each packet-ledger line (a fact or claim to its source turn, an excerpt or quote to its turn), from each fact row and fact version, and from Phase 32's timeline bars once Phase 32 is merged. The same read-only rules and token handling as the rest of the browser Inspector (H15, K21); the panel's Inspector tab shows the page. | A side panel inside the fact table (cramped on a phone); a full-text browser of the chat (the host already shows the chat). |
| Q8 | How is overuse measured before Phase 34? | **A report, not a ranking input.** Per chat, over the recorded requests: how many consecutive requests placed the same `ref`, how often a placed line was echoed by the next reply (`spans.reuse`, ADR 0027), and the share of packet tokens spent on lines placed in each of the last three requests. `tools/` reports it on the v0.3.0 bench databases and the owner's restored copy (counts only). Phase 34's penalty is measured against it. | A penalty now (no baseline); the host's request log (outside NMOS). |
| Q9 | How does it ship? | **`packet-v13` behind `NMOS_PACKET_POLICY`** (Q1–Q6), `packet-v12` unchanged and still selectable; recorded requests replay as they were (ADR 0027). The Inspector page (Q7) and the overuse report (Q8) ship without a policy: they change no packet. The default is the owner's decision on the measurement. | A recall option per rule (several options to keep in step). |
| Q10 | How is it measured? | **(a)** Deterministic cases for each cue, the anchor, attribution, abstention and the unextracted rule. **(b)** An exact-quote case set on the synthetic 240-turn bench chat (committed with the cases; synthetic text only): 24 questions, 8 by turn number, 8 by a first cue, 8 by a speaker and words, each with the source turn and the quoted words as gold. **(c)** A zero-call replay (AGENTS §7 item 6, recall only) of the v0.3.0 bench databases under `packet-v12` and `packet-v13`, three replays with the majority deciding. **(d)** One reduced live run of the sets the change is for, once each: S6 and the quote set on fresh extraction (about 300–400 model calls at the corrected pacing; the owner's estimate of the cloud cost first, since the eval account's credit is limited). **(e)** Latency at scale (Q4). | The full live gate (an extraction change only); real-chat quote cases (kept local by the owner if wanted; aggregates only in the repository). |
| Q11 | What is the bar? | On (b): at least 20 of 24 with the source turn and the quoted words in the packet; no quote attributed to the wrong speaker. On (c): every set no worse by more than one case than `packet-v12` in the same replay; forbidden totals not higher; S6 at least two of three. On (d): S6 at least two of three and the quote set at least 18 of 24 on fresh extraction. On (e): Q4's bar. | — |
| Q12 | Release? | **None at the end of this phase.** `0.4.0` follows Phase 34 (Stage 7 complete, R7). | Release after each part. |

## Baseline

`v0.3.0` (`0ace76c`, `packet-v12`, `extract-v16`). The S0–S6 bench of 2026-10-05/06 at the corrected pacing, one run
per set; owner-local evidence `/home/grantkim725/nmos-eval/bench-v030-0ace76c/` (every probe request, packet text and
score; databases `nmos_b030_*` on the test Postgres). The quote set's baseline is measured under `packet-v12` in
step 3, before any change.

## In scope

1. `packet-v13`: the speech cue and anchors (Q1, Q3), the quote route and `<Quote>` line (Q2), the path in the ledger
   (Q4), the unextracted rule (Q5), and Q6's recall fix if the diagnosis finds one.
2. The source-turn page and its links (Q7).
3. The overuse report (Q8) in `tools/`.
4. The quote case set and its scorer (Q10 b); deterministic cases; a pin that `packet-v12` compiles every recorded
   request as before.
5. An ADR (next free number) for the forensic path and the quote line; ROADMAP's Stage 7 section updated.

## Out of scope

Candidate labels, the overuse penalty and the activation threshold (Phase 34); any model call on the request path
(C8); read-only MCP (R5); story-day segmentation; extraction changes (Q6's extraction cause goes to a later generation);
a migration unless Q7's page needs an index (then stop and ask).

## Steps

1. This document, approved; AGENTS §1/§2, STATUS and ROADMAP name Phase 33 as current.
2. The quote case set and scorer (Q10 b), the overuse report (Q8), and Q6's diagnosis; the baseline under `packet-v12`.
3. `packet-v13` with deterministic cases and the ADR, behind the policy; the zero-call replay (Q10 c) and its report.
4. The source-turn page and links (Q7), with a real-host smoke of the panel's Inspector tab.
5. The owner's decision on the default; then the reduced live run (Q10 d) and latency at scale (Q10 e).

## Stop conditions

Stop and ask the owner when: a replayed set gets worse by more than one case; a quote is placed with the wrong
speaker; a secret or private line reaches a packet it did not reach before (quotes are raw text: the secret gate's
withheld lines and knowledge marks apply to them as to excerpts); `packet-v12`'s compiled output changes for any
recorded request; the forensic path's p95 exceeds Q4's bar; a migration, a runtime dependency or a model call on the
request path would be needed.

**Known risk.** Speech cues are common words ("말했" in a question about something else); the path only adds up to
two quote lines and the replay reports every message it fired on. Quoted speech without a named speaker in its
sentence is left unattributed, which a "what did X say" question needs; the case set measures how often.

**High risk (AGENTS §14):** recall semantics that change memory selection (a new packet line from raw text), secret and
knowledge handling of quoted text, replay of recorded requests, and Inspector pages that show raw turns (token
handling, H15/K21).
