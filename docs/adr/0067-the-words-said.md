# 0067 — The words said, from the turn that said them (`packet-v13`)

Status: proposed, 2026-10-07 (`docs/phases/PHASE-33.md` Q1–Q5, approved by the owner as proposed; AGE-10). Adds the
policy `packet-v13`; `packet-v12` stays the default until the owner decides on the measurement (Q9). No prompt,
generation key, stored row or migration changes.

## Context

A question about what someone said ("13턴에 추오월이 해도를 보고 뭐라고 했어?") is answered by the words, and the
packet gave a summary of them at best. On the exact-quote set (24 synthetic questions, `fixtures/quotes/s3-quotes.json`)
`packet-v12` placed the source turn and the words in 4: the lexical route found the message in all 24, and the excerpt
grew around the sentence that best matched the question's words, which is rarely the quoted one
(`docs/perf/phase33-baseline.md`).

## Decision

Under `packet-v13` (`packet.QUOTE_POLICIES`), in `retrieval.gather`, the module `quotes`:

1. **The forensic path runs on a speech cue** (Q1): a word about speaking (말했, 뭐라고, 물었, 대답했, said, told …)
   or a phrase in quotes in the question, without a model call; not a question about what someone is called now
   ("뭐라고 불러?", `retrieval.CALLED`'s words), which the facts answer and quotes would answer with every older form
   (the v0.3.0 bench replay: S1 turn 120 lost two address cases), unless it carries a history cue ("처음에 뭐라고
   불렀더라?", K44). Every other question takes the normal path, unchanged.
   The trace records the path (`path`: normal or forensic), the quotes placed and the route's own search
   (`quote_mode`: on, none or timeout).
2. **Candidates** (Q2, Q3): the first 12 messages recall found outside the prompt; the messages of turns N−2…N+2 when
   the question names a turn ("N턴", "turn N"); under a first cue, the opening turns and the turns where every character
   the question names had first been named (`first met`, unless that is the opening); and the route's own lexical search
   for messages holding a quote and the question's words, 30 at most, rarest words first, under its own 150 ms
   statement timeout (Q4: it abstains past it).
3. **Scoring.** Every quoted span ("…", “…”, 「…」, 『…』, 4 to 300 characters) of a candidate is a quote; its line is
   its sentence and the sentences around it, grown outward up to 600 characters, verbatim. A quote scores by the
   question's words: twice in the quote, 1.5 in its sentence or the one either side (narration before a quote often
   sets its scene), once anywhere else in its line; each word
   weighted by its rarity on the head (ln(1 + N/df) / ln(1 + N), scaled so the question's rarest word weighs 1; a
   verb-like word half; speech words, question words, first cues and "…에 대해" not counted); plus a phrase the
   question quotes, the message's rank, the named turn (+4 on it, +1 within two, −2 elsewhere), the first-met turns
   (+3) or, without them, earliness, what the question says the words did (+1: "물었어" for a line that is a question,
   "대답했어" for a line right after one), and the one asked about (below). Of two quotes one line would hold, one is
   placed.
4. **The speaker only where the quote's own sentence says so** (Q2). The user's own message is the persona's;
   `X가 "…" 하고/라고 …` is X's (the subject nearest before the quote); `"…" X가 … 말했다` is X's (the first subject
   after it, with a verb of speaking in its clause). A nearest subject that is no known character leaves the line
   unattributed. A character the question names as its subject ("이안이 … 도윤한테") is the one asked about: a quote
   attributed to them gains, one attributed to someone else loses, and an unattributed quote with their name in its
   narration gains as one attributed to them.
5. **`<Quote turn="N" speaker="X">…</Quote>`**, two at most, before the excerpts, never cut (placed whole or not at
   all), never dropped for restating a fact; the ledger kind is `quote`. The secret gate's withheld lines and the
   keyword route's rule for secrets apply to quotes as to excerpts.
6. **A turn extraction has not reached** (Q5): an excerpt from a turn with no extraction of the active generation
   (a first sight still catching up) is not dropped for restating a fact, and one such excerpt may take one slot past
   `top_k` inside the same budget. The ledger marks it `unextracted`. A turn is extracted once, on its last message, for
   every message of it.

## Consequences

- On the exact-quote set: 21 of 24 with the source turn and the words in four replays of six, 20 in two
  (`packet-v12`: 4); the bar is 20 (PHASE-33 Q11). Placed quotes attributed: 4 of 48, none wrong. The misses: a named
  turn whose message is long and whose question's words sit in another exchange of it; a first-cue question whose
  first visit spans two turns; one message the candidates did not reach; and one near tie (0.001) that recall's order
  decides.
- On the v0.3.0 bench replayed (`docs/perf/phase33-replay.md`): every set equal to `packet-v12` case by case, forbidden
  phrases equal; `packet-v12`'s compiled output unchanged on all 314 probes.
- Attribution is rare by design. An earlier rule that also read the next sentence named a speaker on about 40 of 48
  quotes and named the wrong one on about 15: the next sentence of a quote is most often the listener's reaction
  (추오월이 말없이 그를 보았다). PHASE-33 Q2 proposed the sentence before the quote too; measured, it named the listener
  as often and was not adopted.
- A forensic question spends up to about 1,050 tokens of the packet on two quote lines; they displace excerpts and
  facts lower in the order.
- Rejected: a model call to classify the question or to attribute a quote (C8; cost and latency on the request path);
  scoring the quote's neighbourhood only (9 of 24 then, the line placed was not the one scored); more than two lines.
