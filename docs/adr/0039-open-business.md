# 0039 — Open business: goals, questions, threats and debts end, and causes the story states

Status: accepted, 2026-09-28. Phase 11 steps 4 and 5 (`docs/phases/PHASE-11.md`, Q2, Q3, Q4). New extractor generation
`extract-v13`; migration 0022 (`assertion.outcome`, `assertion.because`). Extends ADR 0019 (promise threads) and
ADR 0033 (the OPEN list pattern).

## Context

- **Goals pile up.** `goal` is multi-valued and nothing ends one: across the owner's chats 115 goals were all
  current, one character held 40 (PHASE-11, Evidence), and none reached any of M0's 12 packets
  (`docs/perf/m0-baseline.md`). The owner confirmed that two of one character's goals were long finished while two
  were still under way; the memory could not tell them apart.
- Promises already have a lifecycle (ADR 0019): the prompt lists OPEN PROMISES, and `fulfilled` or a negative
  `promised` names one by its text. It works: 26 promises, 8 kept, in the same data.
- "Why is she angry?" has no answer when the cause lives only in the text: M0's "why" case failed.

## Decision

1. **Four more thread kinds (Q2):** `goal` (an aim, plan or task someone is set on, not a passing wish), `question`
   (something a character wants to know that the story leaves open, or a mystery), `threat` (a danger that hangs over
   the subject and has not played out; `with` names who threatens) and `owes` (a debt, favor or return; subject owes
   object). Kinds `goal`, `question`, `threat`, `debt` beside `promise`.
2. **They open like promises**, from narration or the owner's own words, `actual` or `hypothetical` (a plan is labelled
   either way); a threat from anyone's words (the one who threatens says it), a debt from either side's. A new one
   restates an open one of the same kind and owner when one text contains the other, or, unlike promises, when they
   are as similar as a resolution must be to match: a turn often states the same aim twice in other words (M0 data).
3. **OPEN THREADS and `resolved` (Q3).** The prompt lists open goals, questions, threats and debts, at most 8: those the
   target turn's words are about first (a thread can only be ended while it is listed, and an old goal the story comes
   back to must be), then those whose owner or counterpart the prompt names, then the persona's own. `resolved`
   (subject: the owner; value: the text as listed; `outcome`) ends one: achieved, abandoned or failed for a goal;
   answered for a question; averted or failed for a threat; paid, or abandoned, for a debt. Matching is ADR 0019's:
   owner, then equal text or clearly the most similar; no match or a tie ends nothing and is listed as unmatched.
   `fulfilled` and a negative `promised` still match promises only, and `resolved` never matches a promise. A
   `resolved` without a valid outcome is pending.
4. **Only `extract-v13` and later open them.** Earlier generations never report an end, so their goals stay facts,
   as before; a turn moves to threads when it is extracted again (the recent window at once, older turns by "Extract
   all history", ADR 0014).
5. **`because` (Q4).** On `event`, `feels_toward`, `relationship`, `has_status` and `goal`, the cause as the TARGET turn
   or its CONTEXT states it, a short phrase; never guessed. Stored (migration 0022); the read side uses it in step 6.
6. **Secrets before threads.** A thread copies the knowledge marks of the row that opens it, so the fact read now
   applies reveals (ADR 0033) before folding threads: a revealed goal or promise is revealed as a thread too. Before,
   a promise kept from someone stayed hidden from them after they found it out.
7. **The packet** shows open threads of every kind in `<Threads>` (ranked as ADR 0019 and its amendment 1 rank
   promises), and its Note explains each kind only when one is kept, so packets with promises only read as before.
   The Inspector's thread table has a kind column and the new outcomes.

## Consequences

- Production re-extracts each chat's recent window once (about 124 turns on 2026-09-28, the owner's model through
  Ollama); the owner pulls it after a backup.
- Threads compete with facts for the packet: `threads_limit` (3) is unchanged; on M0 a limit of 5 or 8 held one of two
  old open goals, not both, so it stays.
- M0 on 28 owner-confirmed cases: 13 before Phase 11, 15 after step 3, 17 with `extract-v13`; no category worse
  (`docs/perf/extract-v13.md`).
- K23 now covers every kind: a thread stays open until the story ends it (nothing ends one because it is old).
