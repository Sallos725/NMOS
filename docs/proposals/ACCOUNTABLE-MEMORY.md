# Accountable Memory — what NMOS contributes to long-term memory for LLMs

> Proposal and position paper, 2026-09-26. It does not authorize work. It states, in terms that are not
> specific to role-play, the design NMOS has converged on through Phase 9. It separates what is measured
> from what is proposed, and it lists the next experiments.

## 1. Claim

Long-term memory for LLM applications is usually built as *store → retrieve → inject*. The work goes into
the store (vector databases, summaries, knowledge graphs) and into retrieval (hybrid search, reranking).

Long sessions fail on something else. The system cannot say, for a given reply:

1. what memory the model was given,
2. where each piece came from and whether it was still true,
3. what was left out and why,
4. whether the model used it,
5. whether a different selection would have done better.

Without answers to these, memory cannot be debugged by its user, evaluated by its builder, or improved
without experimenting on live conversations.

**Accountable memory** is memory that can answer all five questions for every request, deterministically
and after the fact. NMOS now does, with six mechanisms that are not specific to role-play:

| # | Mechanism | What it answers | NMOS |
|---|---|---|---|
| 1 | Immutable evidence ledger + worldline membership | "was it still true?": edits, deletes, regenerations and branches invalidate derived memory before the next request | invariants 1, 7; D4, D8; 0 stale packets in every evaluation mode |
| 2 | Derived memory bound to generations | "which extractor, prompt, model produced it?" | D20, ADR 0006, ADR 0014 |
| 3 | Packet ledger with provenance | "what was the model given, from where, what was dropped and why?" | ADR 0027 |
| 4 | Bitemporal reads (story position × knowledge time) | "what did the system know then?": every past request can be compiled again exactly | ADR 0027 |
| 5 | Echo from the next turn | "did the model use it?": a free, weak, deterministic label | ADR 0027 |
| 6 | Named selection policies + counterfactual replay | "would another selection have done better?": offline A/B on real requests | ADR 0027 |

Mechanisms 1–2 are known as event sourcing and projection versioning; NMOS applies them strictly to
conversational memory. Mechanisms 3–6 are what Phase 9 adds, and together they turn memory selection from
guesswork into something that can be measured.

## 2. Why selection, not storage, is the frontier

Evidence from NMOS (`docs/perf/phase9-packets.md`):

- **Budgets saturate.** On the owner's chats the reserved 600 tokens were full (median 566) and a raw
  excerpt got in on 7 of 168 requests. Distilled facts had crowded out the only memory that carries exact
  words.
- **Distilled and raw memory are complements, not substitutes.** In an answer probe with two response
  models, questions whose answer existed only in a message's words were answered every time the packet
  held that message. They were never answered when facts filled the budget. Questions about facts
  answered alike whether or not an excerpt took one fact line's place.
- **Selection errors are invisible without a ledger.** The ledger's first real-host run showed an older
  bug on its first request: the user's own current message recalled as "memory". It had never been
  noticed, because nothing recorded what went in.
- **Obvious metrics are wrong.** The first definition of "use" (share of a line's words in the reply)
  found no use at all in replies that plainly answered from memory. Models reuse the key phrase, not the
  line. Measuring on real replies corrected it the same day.

A memory system that only stores more, or retrieves better, still fails these cases. It has to choose
under a budget and account for the choice.

## 3. Design principles (portable)

1. **Evidence is immutable; memory is a projection.** Every derived row names the evidence revision and
   the generation that made it. Changing a prompt or model makes a new generation, never an overwrite.
2. **Invalidate before use, recompute later.** A request never waits for a model to repair memory. It
   masks what is stale and falls back to raw evidence or to nothing (fail open, never stale).
3. **The unit of accountability is the packet line, not the memory item.** A request's memory is a
   ledger of offers, each with provenance, cost, outcome and reason.
4. **Every read can be asked "as of".** Story position (which evidence was on the active worldline) and
   knowledge time (what had been derived by then) are both parameters of every memory read. This makes
   every past request reproducible.
5. **Budgets are first-class.** Kinds of memory compete, and some carry what no other kind can (exact
   words). Reserve room per kind, and never spend it twice on the same content.
6. **The next turn is a label.** Whether a reply reuses a placed line is observable without a judge
   model. It is weak (use without echo exists, and echo without use), but it is free, deterministic and
   collected on every real turn.
7. **Change selection offline first.** A new policy is compiled against recorded real requests before it
   serves one. Lines both policies place are compared directly. Lines only the new policy places are
   counted, not credited: the real reply never saw them.
8. **The model never writes memory.** Accountability requires that memory be a function of evidence,
   code and configuration. Self-edited memory has no ledger to answer from.

## 4. What is portable beyond role-play

The mechanisms assume only a conversation with messages that can be edited, deleted, regenerated or
branched. That covers chat assistants, coding agents (tool logs as evidence, edits as reverts), and
multi-session assistants. Many chat products expose these operations, and none of the mechanisms needs
model internals. Role-play is a demanding test bed: sessions of thousands of turns, heavy
regeneration, multiple characters with private knowledge, and users who notice every lapse.

## 5. Honest limits

- **Echo is off-policy.** It labels only lines that were placed. A line never placed gets no label, so
  echo cannot show that a dropped line would have helped. The ledger's "unplaced but reused" count is a
  hint of such misses (the reply knew it anyway), never proof.
- **Small evidence.** One owner's chats, synthetic probes, two response models that are not the owner's.
  The mechanisms are verified; the rates are not yet.
- **Surface measures.** Echo and the leak flag compare text. A paraphrase escapes them.
- **Replay is exact while the gathering code is unchanged.** The compiler is versioned (policy names);
  gathering is not.

## 6. Next experiments (ordered)

1. **First real A/B.** Release migration 0020 and let the owner's chats record ledgers for a week. Then
   run `tools/replay_packets.py` for `packet-v0` against `packet-v1`. Metrics:
   - excerpt placement rate;
   - reply-echoed lines kept;
   - lines only one policy places.
2. **Echo rates per kind.** From those ledgers, measure how often each kind of line is echoed:
   - relationship and address lines;
   - major and minor events;
   - traits;
   - excerpts.

   Hand-set ranking priors (e.g. the "standing" prior of the fact-ranking work) can then be replaced by
   measured ones, still read-side and still reproducible.
3. **Token calibration per host tokenizer (K26).** Up to 40 % of a Korean packet's reserve is unused.
   Offer a per-tokenizer estimate, chosen by the owner, never guessed.
4. **Leak monitoring as a contract with VEIL (O1).** NMOS reports placed secrets that the reply reused.
   VEIL decides disclosure pacing. The data flows one way and is read-only.
5. **Exploration without harming users.** Echo cannot label unplaced lines, and serving random packets
   to learn would degrade real conversations. A candidate: when the budget has slack (empty packets are
   frequent, 47 of 168), place one extra below-threshold line and record it as exploratory. The reply's
   echo then labels it, at no cost to what would have been placed.

## 7. Relation to existing NMOS decisions

- Invariant 8 (retrieval ≠ utilization) now has all four stages represented: retrieved (candidates),
  visible (knowledge marks, still soft), placed (ledger), used (echo).
- Invariant 10 (provenance) now holds from storage to packet line.
- Nothing here changes an invariant, adds a dependency, or touches the plugin.
