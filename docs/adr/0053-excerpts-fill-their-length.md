# 0053 — Excerpts that fill their length (`packet-v10`)

Status: accepted, 2026-09-30. Phase 18 step 4 (`docs/phases/PHASE-18.md` Q3, Q4, approved by the owner).

## Context

`packet-v9` (ADR 0049) grows `excerpt_chars` with the budget (480 at 2,000, 960 at 4,000, up to 1,920), but an excerpt
was always the two consecutive sentences sharing most trigrams with the query: on the owner's M0 chat excerpts had a
median of 69 characters at 2,000, 4,000 and 8,000 alike, maximum 150 (`docs/perf/lexical-recall.md`). The right
message was often recalled while the answer stood in a neighbouring sentence (a pet's name one sentence after the
sentence naming the pet).

## Decision

1. **`packet-v10`**, the new default, is `packet-v9` with one change: an excerpt starts from its best sentence and adds
   whole neighbouring sentences, after then before in turn, while the text stays within `excerpt_chars` and holds at
   most four sentences (`GROW_MAX_SENTENCES`, owner, 2026-09-30) (`packet.grown_excerpt`). Every other section and limit
   is `packet-v9`'s. Growing to the whole length was measured too: it answered 4 more M0 cases needing memory without
   vectors, and placed values the story had since replaced far more often on the synthetic chat (29 against 17 with
   vectors); the owner chose the four-sentence cap.
2. **The best sentence** holds most of the user message's keywords (`keywords.py`, ADR 0052), then shares most trigrams
   with the query and the previous AI turn, the earlier sentence on a tie. The one-sentence form the packet fitter
   falls back to is that sentence.
3. **Edges.** A best sentence longer than `excerpt_chars` is cut there with one "…"; an excerpt that left sentences out
   before or after is marked "…" on that side. Under budget pressure the fitter still places the one-sentence form, a
   cut of it, or nothing (packet-v1); a keyword-only excerpt is still never cut (ADR 0052).
4. **Replays.** A request recorded with `packet-v9` replays with it; `packet-v9` and its `excerpt` rule are unchanged.

## Consequences

- Excerpts grow to up to four sentences (M0 median 98 characters against 69), so more of a packet's budget goes to
  raw text; under pressure the fitter still falls back to the one-sentence form.
- The token estimate of a packet rises toward its budget more often; the budget advice (ADR 0036) is unaffected in
  rule, measured in step 5.
