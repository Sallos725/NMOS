# Phase 24 — A name as the story says it: given names and romanized names

> **Status: draft, awaiting the owner's approval.** Not a roadmap stage: a correction found by measurement, tracked as
> AGE-28 under AGE-24. The owner decided on 2026-10-01 that `0.3.0` waits for AGE-24's fixes (`docs/STATUS.md`,
> Decisions); this phase is one of them, next to Phase 23 (current, another session). K32 (a persona narrated in the
> third person) was measured with it and is left out (Q4).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | When does a given name alone mention a character? | **When the character's name is three Hangul syllables and the first is a common one-syllable family name** (a fixed list of about 60): the last two syllables also count as that character's name (백이안 → 이안). **Not** when those two syllables are another entity's name, when two characters would share them, or when the name is the persona's: the persona's given name becomes a persona name, which is never a mention (ADR 0023). Characters only (a place's name is not split). Read side only, as a name already counts: no new extractor generation. | No family-name list (measured the same on every set; a three-syllable foreign name would be split too). The extractor writing the given name as `also_called` (`extract-v15`, model-dependent, and only after a re-extraction). |
| Q2 | When does a Hangul word mention a character NMOS holds under a romanized name? | **When the word spells it:** a fixed spelling key on both sides — the Hangul word romanized syllable by syllable (Revised Romanization; the usual spellings of common family names, such as 박 → Park, 이 → Lee), both sides folded to one key (letters only, lower case, `oo`/`u`, `eo`/`u`, `ee`/`i`, `ui`/`i`, `k`/`g`, `p`/`b`, `t`/`d`, `l`/`r`, …). A word of the message (its first two to four syllables, before a particle) whose key equals a Latin character name's key, or the key of its last part when the name has two (the given name), counts as that name. The same exclusions as Q1; one direction only (a Hangul word, a Latin name). | Joining the two names in entity resolution (ADR 0012 links names only by stated aliases; a join is the owner's, with its preview, ADR 0055). The extractor writing the Hangul spelling as `also_called` (`extract-v15`, model-dependent). |
| Q3 | Where do the new names count? | **Only as a mention in fact selection** (`relevant_facts`, facts and claims), like the names a fact already carries. Not for `hidden_from` (a secret's holder addressed), the scene's cast, the Inspector or entity resolution. | Everywhere a name is matched. |
| Q4 | K32: the persona asked about in the third person? | **Not in this phase; K32 stays recorded** with this phase's measurement. Two rules were tried (below); neither gained without a loss. | Rule A or B below. |
| Q5 | How do recorded requests replay? | **A recall option `name_variants` recorded in the trace, on for new requests; a trace without it replays with it off** (as `first_cue`, Phase 21). The packet policy stays `packet-v10`. | A new packet policy `packet-v11`. |
| Q6 | How is it measured? | **Replays only, no model call:** the synthetic 240-turn chat's 15 first-cue cases and its 25 cases at two cuts; the owner's M0 main chat; sample 2 (window B, lexical) and its full-name/given-name probes; the two restored production copies' generated who/first probes (20-message window); **generated Hangul probes for the characters held only under romanized names** on the restored copies (below); deterministic cases for Q1–Q3 and Q5. Each set three times: the packet's size moves by about 1 % between runs of the same code. | One set per question. |

## Goal

Korean role-play calls a character written in full as 백이안 by "이안", and a story written in English with Korean
characters stores "Ryu Ha-jin" while the user asks about "류하진". Today neither is a mention, so the character's facts
stay out of the packet unless a lorebook key or a stated alias joins the names. After this phase both count.

## Evidence behind the scope

Measured with read-only replays of recorded requests on the test database (vectors off, `first_cue` and
`history_marks` on as on `main`; counts only; scripts outside the repository).

| Set | Today | Q1 | Q1 + Q2 |
|---|---|---|---|
| Synthetic 240-turn chat, 15 first-cue cases (packet only) | 5/15 | **8/15** | — |
| Synthetic chat, 25 cases at the 240 cut; the same 25 after a first connection | 23/25, 24/25 | 23/25, 24/25 | — |
| Owner's M0 main chat, cases that need memory | 7/10 | 7/10 | — |
| Sample 2, window B, lexical (cases that need memory) | 9/17 (5/13) | 9/17 (5/13) | — |
| Restored copies, generated who-probes / first-cue probes | 7/7, 4/4 / 5/5, 7/8 | the same | — |
| Restored copies, Hangul probes for characters held only under a romanized name (two chats) | 8/24, 0/6 | — | **10/24, 2/6** |

- No set lost a case or placed a forbidden phrase with Q1. Q2 was measured on its own probes only ("—"): the other
  sets name almost no character in Latin letters. Step 3 measures every set with both. One M0 case changed once in
  six runs of the same variant: noise from the packet's run-to-run variation, which is why Q6 asks for three runs.
- **Why Q1 has its exclusions.** A first version split every three-syllable name. It split a place's name, and the
  persona's given name became a mention: the persona is named in almost every message, so its facts filled the slots
  and two stale values were placed (synthetic 25-case set 23 → 22, two forbidden phrases). With characters only and the
  persona's given name made a persona name, no set changed for the worse. Sample 2's given-name probes were unchanged:
  its lorebook already lists those given names (ADR 0046).
- **Q2's key.** On the lorebook of the restored chat that writes its characters in Latin letters, the key matched 77
  of the 79 pairs of a Hangul name and its romanized spelling that one entry lists together (the two misses spell 아 as
  "Ah"). It also matched six pairs across different entries: a common word and a given name that sounds the same (a
  word for "sky" and a romanized given name). That chat's story is mostly in English: 104 of the 228 name combinations its
  facts carry are in Latin letters only, while the user writes in Korean.
- **Q2's probes.** For each character held only under a Latin name, with at least two facts outside the window and a
  Hangul spelling the chat itself writes, two questions in Hangul ("<name>는 어떤 사람이야?", "…지금 어디에 있어?"); a
  probe passes when the packet holds one of that character's values.
- **K32 (Q4).** Rule A, "the persona named in a question counts as a first-person question": sample 2 +1 (an early
  case) and −1 (a stale rank placed), the synthetic 25-case set −2 with three forbidden phrases, one copy's who-probes
  −1. Rule B, the same but only for the persona's facts that share words with the message: at a low bar sample 2 −1
  and no gain anywhere; at the lexical bar (0.30) no change at all. The persona's facts outnumber any other character's,
  so a bonus for all of them crowds the others out.
- **Risk kept by Q1 and Q2.** A given name that is also a common word or contraction ("하진" in "그렇게 하진 않았어")
  counts as a mention when the message has that word. The mention adds facts of that one character; it removes nothing
  the message names, and the exclusions keep it from the persona and from shared names.

## In scope (Phase 24)

1. **Given names (Q1) and romanized names (Q2)** in fact selection only (Q3), behind the recorded option (Q5).
2. **Deterministic cases:** a given name brings its character's fact; a place's three-syllable name is not split; a
   given name shared by two characters, or equal to another entity's name, brings neither; the persona's given name is
   no mention and not a first-person question; a Hangul word with a particle after it mentions a character held under
   its Latin full name and under its Latin given name; a common family name's usual spelling (Lee, Park) matches; a
   word whose key matches two Latin characters brings neither; a trace without `name_variants` replaying unchanged.
3. **Evaluation (Q6)** and docs: an ADR, `ARCHITECTURE.md` (a decision), CHANGELOG, `docs/perf/name-variants.md`,
   K31 (reduced) and K32 (measured, not changed) in `docs/KNOWN-ISSUES.md`.

## Out of scope (Phase 24)

- K32 (Q4); a Latin word in the message for a character held under a Hangul name; names in `hidden_from`, the scene's
  cast, the Inspector or entity resolution (Q3).
- A model call; an extractor change (AGE-27's `extract-v15` is a separate phase); packet budget or fill changes.

## Acceptance criteria

- [ ] Every existing test and memory-evaluation case passes; recorded `packet-v10` requests without `name_variants`
      replay as they were.
- [ ] The deterministic cases of In scope 2.
- [ ] Q6's sets, three runs each: the synthetic first-cue cases at least +2; the restored copies' Hangul probes more
      than today on each chat; no other set worse than today; no new forbidden phrase placed on any set.
- [ ] Request-path latency unchanged within noise (`tools/bench_story.py`, 10,000 messages).

## Steps (one pull request each)

1. This document, approved; AGENTS §2 and STATUS name Phase 24 current.
2. The given-name and spelling-key rules, the recorded option, the deterministic cases (ADR 0058).
3. The evaluation and docs; Phase 24 complete.

Every merge reaches the owner's `:edge`; no tag (AGENTS.md §13).

## Stop conditions

Stop and ask the owner when:

- a recorded request without `name_variants` replays differently;
- any Q6 set gets worse, or a forbidden phrase appears that did not before;
- a rule needs more than the message and the names NMOS holds (a model call, a dictionary of Korean words).
