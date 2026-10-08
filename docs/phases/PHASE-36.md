# Phase 36 — A name in the message is not a question about everything (`packet-v16`)

> **Status: approved 2026-10-08 (the owner: as proposed), a correction phase (AGENTS §7 item 5) found on Phase 34's
> live run; step 2 under way (#283: `packet-v16`, ADR 0070, the trial chat replayed).** Under AGE-10,
> after Phase 35; `0.4.0` waits for it (the owner, 2026-10-08: in the release, then two weeks of use before 1.0).
> Recall only: no extraction prompt, generation key, stored row or migration changes.

## Why now

Phase 34 rests a supportive line that no reply used (ADR 0068) and never rests a required one. On the owner's trial
chat (the live run of PHASE-34 Q8 d; aggregates only) about three quarters of each packet's tokens were required, so
the rest had little to act on. The owner asked whether a character's basic facts need to be there at all, since the
host's prompt already carries the card, the persona and the lorebook entries it triggered.

Reading the 13 `packet-v14` requests of that chat (210 required lines, 20,935 tokens; read-only):

| Why the line was required | Lines | Tokens | Share |
|---|---:|---:|---:|
| The story-so-far summary | 13 | 4,023 | 19 % |
| A named character's current state (`located_in`, `has_status`, `feels_toward`, `possesses`) | 50 | 4,527 | 22 % |
| **A named character's other facts, the message naming the character and nothing more** | **91** | **5,575** | **27 %** |
| Threads, claims, the first excerpt, quotes | 52 | 6,572 | 31 % |

(Four lines whose fact the story has replaced since are not counted.)

The third row is how PHASE-34 Q1's "a fact the question names" was built: `facts.relevant_facts` marks a fact named
when the message holds **any name of its subject or object** (`named.add`), so a message that mentions a character
makes every fact about that character required, and none of them rests. None of the 91 shared the message's words
(the lexical overlap under `LEXICAL_BAR`). By predicate: `event` 30 lines (2,924 tokens), `relationship` and
`addresses` 24 (1,281), `member_of`, `identity` and `has_trait` 34 (1,166), `knows` 3 (204).

The owner's first idea, leaving out a fact the canon in the prompt already states, reaches less: of the 34 trait,
membership and identity lines, 12 (342 tokens, 1.6 % of the required tokens) had a canon fact of the same character and
predicate whose source the request's prompt held (`canon_held`); the others differ in predicate or need a translation
to compare (the canon was read in English, the story in Korean).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q1 | When does naming a character make its fact required? | **When the fact is how things stand now or between them, or the message's own words point at it.** A fact the message names (as now) stays required when its predicate is a current-state one (`located_in`, `has_status`, `feels_toward`, `possesses`) or a standing one (`relationship`, `role_toward`, `addresses`: how two characters speak and stand shapes every reply, ADR 0026), when it is a knowledge boundary (`known_by`, `hidden_from`), or when the message's words hit it (overlap at least `LEXICAL_BAR` with the fact's words). **Otherwise it is supportive**: a past `event`, `member_of`, `identity`, `has_trait`, `knows`, a world fact, named and nothing more. It is offered exactly as before (ranking and limits unchanged); only its label changes, so it rests when no reply used it (ADR 0068). | Leave out a fact the canon in the prompt states (1.6 % of the required tokens on the trial chat; needs a translation to compare); demote every named fact (relationship and address lines set the speech level of every reply); keep the rule (the rest has little to act on). |
| Q2 | Do current-state facts ever rest? | **No**, as now: they and the Cast stay required. | Rest them too (the scene changes with them). |
| Q3 | How does it ship? | **`packet-v16`** behind `NMOS_PACKET_POLICY`, on top of `packet-v15`. The default is the owner's decision on the measurement. | A recall option. |
| Q4 | How is it measured? | **(a)** Deterministic cases: a named event and trait are supportive and rest when unused; a named location, relationship, address and boundary stay required; a named event the message's words hit stays required. **(b)** The sequential replay of the trial chat's recorded requests (`tools/replay_sequence.py`, as PHASE-34 Q8 b) and of S1's live run, under `packet-v15` and `packet-v16`: the required share, the supportive repeat and stale shares, the whole packet's. **(c)** The zero-call replay of every probe of the v0.3.0 bench and the quote set, three replays each (AGENTS §7 item 6). **(d)** No live run proposed; the owner's two weeks of use after `0.4.0` are the live check, with testers' comments. | A paid paired run (the extraction is unchanged). |
| Q5 | What is the bar? | On (b): the required share of placed tokens lower on the trial chat; the whole packet's repeat share not higher. On (c): no case lost against `packet-v15` on the majority of three replays; forbidden totals not higher; the quote set at least as `packet-v15`. | — |

## In scope

1. `packet-v16`: Q1 in `facts.relevant_facts` (or where `named` is read), behind the policy.
2. Deterministic tests; the replays (Q4 b, c) and their report in `docs/perf/`.
3. An ADR (0070) and an ARCHITECTURE decision; README, guide and CHANGELOG lines.

## Out of scope

Which facts are offered and in what order (ranking, limits, the Cast); a translation of canon facts; extraction; a
model call; the story-so-far summary (required since PHASE-34 Q1's amendment).

## Steps

1. This document, approved.
2. `packet-v16` with deterministic tests, the ADR, and the replays (Q4 b, c).
3. The owner's decision on the default; then `0.4.0`.

## Stop conditions

Stop and ask the owner when: a replayed set loses a case under `packet-v16`; a forbidden total rises; the required
share does not fall on the trial chat; the change needs a stored row, a migration or a dependency.
