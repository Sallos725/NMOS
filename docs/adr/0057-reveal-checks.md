# 0057 — A reveal check instead of a re-extraction

Status: accepted, 2026-10-01 (Phase 22 step 2, `docs/phases/PHASE-22.md` Q1–Q4; AGE-25). Amends ADR 0033 amendment 2
(G2: "Extract all history" extracted such turns again) and ADR 0014 (a turn's served rows: its extraction and, now,
that extraction's reveal check).

## Context

A turn extracted before an earlier turn's secret was could not report finding it out: its OPEN SECRETS listed nothing
(K29). Since ADR 0033 amendment 2, "Extract all history" discarded such a turn's extraction and extracted the turn
again. On the owner's M0 main chat one press re-extracted 68 turns: 727,232 input and 85,306 output tokens, and the new
extractions did not state again 77 of their 237 narrated facts, 30 of them held nowhere else in the chat — among them
character A's occupation, which the packet then lacked (AGE-25). Model output varies from call to call; a new call words
every fact anew. Only the reveal was missing.

## Decision

1. **A reveal check.** "Extract all history" keeps the turn's extraction and queues a job of kind `reveal` for each turn
   that needs one (item 4). The worker loads the turn as a turn extraction does (the extractor's context turns), lists
   the OPEN SECRETS before the turn from the served memory (`secret_hints`, at most 8), and asks the extraction model a
   short prompt with only the secrets rules (`reveals.PROMPT`): the answer is `{"secrets": [...]}`, checked as a turn
   extraction's (`revealed`: a listed secret, characters it is kept from, evidence in the turn) into `learned` rows.
   No other fact. A turn with no open secret before it is checked without a call (usage `{"calls": 0}`). An answer
   without a `secrets` list fails the job, which is retried.
2. **Stored as canon facts are (ADR 0047).** A check is an extraction of a generation of kind `reveal` (migration 0028;
   key: the extractor's endpoint and model, JSON mode and temperature, `reveal-v1`, the prompt's fingerprint, the
   compiler that builds its input and checks its answer (`extraction.COMPILER_VERSION`), the normalizer and the context
   settings), against the
   turn's anchor revision, under the window `reveal:<turn hash>`. Its hints record the extraction it checked
   (`checks`) and the secrets it listed (with their turn hashes, as a turn extraction's, ADR 0033 amendment 2). No
   other reader of a turn's extractions takes it: they match the turn hash itself. One live check per turn and
   generation: a new check of the turn discards the previous one (kept for audit).
3. **Served while the extraction it checked serves the turn.** The fact read (`facts.ACTIVE_ASSERTIONS`) joins a turn's
   extractions and its checks in one probe of the turn's revision; the extraction chosen to serve the turn is chosen as
   before (ADR 0014), checks never among the candidates; a check's rows are served when `checks` names the chosen
   extraction, and read as that extraction's generation and compiler. A rebuild, the re-extraction after a join's undo
   (ADR 0055) or a new extractor generation serves the turn with another extraction, and the check stops counting with
   it. The read as of an earlier request takes only the checks made by then (ADR 0027).
4. **Which turns.** As amendment 2's rule, with a check counting as looking: a turn needs one when its live extraction
   of the active generation was made, and its latest live check of that extraction too (if any), before any
   extraction holding an earlier turn's secret existed. Jobs run at background priority, queued after that press's
   extract jobs and in turn order, so `claim` takes them oldest first and a later turn's OPEN SECRETS leave out what an
   earlier check found. A job already done is queued again when the turn needs a check again. A second press queues
   nothing. The chat's coverage reports checks pending, failed and made (`extraction.reveal_checks`), and their usage
   counts in the chat's model usage (ADR 0051).
5. **After the check.** As after a turn extraction, the summaries a secret held back are scheduled again (a secret
   found out changes what a summary may say).

## Consequences

- "Extract all history" no longer discards anything. A turn keeps the facts it had; the reveal is the only new row.
- A full extraction would also record what the character now knows (`knows`); a check does not (PHASE-22 Q2). The
  reveal itself already counts the character as knowing the secret (ADR 0033 amendment 1).
- Two workers can still check neighbouring turns at once (K29's remaining limit): another press fixes it.
- The fact read gains a probe pattern, not a probe: request-path latency is measured in step 4.
- A rebuild still extracts every turn, recent ones first; K29 can follow it, and a press of "Extract all history"
  then checks those turns. Facts a rebuild drops are Phase 22 step 3's report.
