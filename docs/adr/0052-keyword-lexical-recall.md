# 0052 — Keyword lexical recall

Status: accepted, 2026-09-30. Phase 18 step 3 (`docs/phases/PHASE-18.md` Q1, Q2, Q4, approved by the owner; the
secret rule below chosen by the owner the same day). Amends ADR 0004 / D15. No migration, no plugin build.

## Context

Lexical recall scores the whole user message against each head message (`word_similarity ≥ 0.4`, ADR 0004). A natural
question dilutes that score with its own words: on the evaluation queries it returned any candidate for 43 of 145
(30 %, `docs/perf/lexical-recall.md`), and production recalled without vectors 70 % of the time (K34). A question that
names a pet scored 0.32 against the message that answers it; each of its two nouns alone scored 1.0 on that message.

## Decision

1. **Keywords, deterministically** (`keywords.py`, Q1). The cleaned message split into words; Korean question endings
   and particles taken off a word's end from fixed lists, choosing the longest suffix that leaves two syllables; a word
   that would shrink under two syllables keeps its form (민지, 사과); a one-syllable suffix keeps the longer form as a
   fallback (it may end a name). Question words and a short stop list are dropped; a word ending like a verb goes after
   the names and nouns. At most four, longest first, fallbacks last. No morphological analyzer.
2. **A second lexical route** (Q2). Each keyword matches a head message at `word_similarity(keyword, text) ≥ 0.8`
   (`KEYWORD_THRESHOLD`, the trigram index still serves it). A keyword in more than 200 head messages (D15's bar), or in
   more than half of them, names what every scene holds and is dropped. A message's score is the sum of its keywords'
   `log(messages / matches)` (at least log 2, since a keyword in more than half is dropped), messages counted as the lookup filters them (accepted, not hidden, not a comment,
   after the last cut). Each keyword's lookup gets at most `KEYWORD_SLICE_MS` (25 ms): a word that takes longer is as
   common as a dropped one (a two-syllable word's three trigrams can leave the index thousands of long messages to
   recheck) and is dropped, the others still count. All keywords share one budget, `NMOS_LEXICAL_TIMEOUT_MS`; when it
   runs out, before any statement of the route (a lookup, the count, the final read), the route abstains. Candidates are ordered by score, then the later message, then the id,
   before the first CANDIDATE_LIMIT are kept, so a replay picks the same ones. The trace records `keyword_mode` ("on", "none", "too_broad", "timeout", "off") and each candidate's
   `keyword_score`.
3. **Fusion** (Q2). The keyword list joins the whole-message and vector lists in the same reciprocal-rank fusion, and a
   keyword hit is its own admission signal: a keyword-only hit is kept with vectors off and under the whole-message
   bar. A lexical or keyword hit is excerpted from the whole message; a vector-only hit from its chunk.
4. **No new secrets** (owner, 2026-09-30). An excerpt only the keyword route found is left out when its text repeats a
   secret still kept from someone, by the test a summary passes (`summaries.leaks`, PHASE-12 Q3: stricter when someone
   it is kept from is in the scene, which is worked out for this even with facts, threads and summaries off). Both forms
   the packet may place are checked (the full excerpt and its best sentence), and such an excerpt is never cut to fit:
   it is placed in a checked form or not at all. The trace counts them (`keyword_withheld`). Excerpts the other routes also found
   are unchanged: raw excerpts in the default memory mode are not filtered for secrets today, and doing so for every
   route would change `packet-v9`; that is a separate proposal.
5. **Replays** (Q4). `lexical_keywords` is a recorded recall option, on for new requests. A trace that did not record it
   replays with it off, so a request from before this ADR replays as it was. The evaluation tool can force it
   (`tools/eval_rp.py --keywords on|off`).

## Consequences

- More raw passages reach the packet for natural questions, with or without vectors.
- A chat's main names are dropped as too common on short chats too (the half rule); a question about them relies on
  facts, vectors and the other keywords.
- Latency at 10,000 messages (`tools/bench_story.py`, budget 4,000, three alternating runs): p50 +10.0 ms, p95
  −203 ms (slow words used to take the whole lexical budget). Measured again in step 5.
- Verbs and one-syllable-particle forms can still take a slot; the rules are fixed lists and can be retuned.
