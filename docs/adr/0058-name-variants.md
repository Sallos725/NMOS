# 0058 — A name as the story says it: given names and romanized names

Status: accepted, 2026-10-01 (Phase 24 step 2, `docs/phases/PHASE-24.md` Q1–Q5, approved by the owner; AGE-28). Amends
how a message is matched against a character's names (ADR 0012 resolution unchanged; ADR 0023, 0034, D19, D44). No
migration, no plugin build, no new packet policy.

## Context

Korean role-play calls a character written in full as a three-syllable name (백이안) by the given name alone (이안), and
a story written in English stores a Korean character under a romanized name (Hajin) that the user writes in Hangul
(하진). Neither was a mention: a name counts when the message contains it whole, and names join only through a stated
alias, a lorebook key (ADR 0046) or the owner's join (ADR 0025, 0055). The character's facts stayed out of the packet
(K31). Measured on replays (PHASE-24 Q6): the synthetic chat's first-cue cases 5/15; on a restored production chat whose
story is mostly in English, 104 of the 228 name combinations its facts carry are in Latin letters only, and questions
in Hangul about those characters found their values 8 of 24 and 0 of 6 times.

## Decision

1. **Given names** (Q1). `variants.given`: a normalized name of three Hangul syllables whose first is one of 60 common
   one-syllable family names (`variants.FAMILY`) also goes by its last two syllables. Characters only, not the persona.
2. **Romanized names** (Q2). `variants.key` folds a Latin spelling to a key (letters only, lower case, `FOLDS` in order);
   `variants.hangul_keys` romanizes a Hangul word of two to four syllables syllable by syllable (Revised Romanization)
   and, for three or four syllables, with its family name's usual spellings (`SPELLINGS`). A character's Latin name
   has the keys of the whole name and of its last part when it has two (`latin_keys`, at least `KEY_MIN` letters). In
   a run of Hangul in the user's message or the previous reply, the first four, three, then two syllables are tried;
   the first prefix whose keys meet any Latin character's decides: when exactly one, that word goes by its name for
   this request; when more, no word of that run does. One direction only (a Hangul word for a Latin name).
3. **One owner per variant.** A given name or a Hangul word counts for no one when it is another entity's name or the
   persona's given name, or when two characters would share it, whichever rule gives it to each (백하진's given name
   and Hajin's spelling are both 하진: neither). A name that only knowledge marks hold (someone a secret is kept from,
   ADR 0034), an open thread's included (a thread keeps the marks of the assertion that opened it), is a character of
   its own for these rules, so a secret's holder addressed by a variant is still recognized; with the option on, the
   scene's cast reads an open thread's marks too.
4. **Everywhere a message is matched against names** (Q3), from one mapping per request (`variants.aliases`, computed
   once by `retrieval._aliases` whichever path asks first): fact selection (`relevant_facts`, facts and claims: a mention, and a secret's holder addressed,
   D19), open threads (`relevant_threads`), the scene's cast (`scene.cast`, D44: a fact kept from a character addressed
   by a variant is private) and its names (`scene.names`: knowledge marks, the cast's groups, summaries and the keyword
   route's secret check). Nothing is stored; entity resolution, joins and the Inspector are unchanged.
5. **The character asked about keeps its cast group.** A given name in the previous reply brings more characters into
   the scene, and `<Cast>` shows at most four (PHASE-12 Q4) in the cast's order; on the synthetic chat a character the
   message named in full lost its group to two the reply had named by given name (a case 1 → 0). With the option on,
   the characters the user's message names come first, the rest in the cast's order.
6. **Replays** (Q5). `name_variants` is a recorded recall option, on for new requests. A trace that did not record it
   replays with it off, so a request from before this ADR replays as it was. The packet policy stays `packet-v10`.

## Consequences

- "이안은 어디 있지?" brings 백이안's facts, and "하진은?" Hajin's; with the character in the scene its secrets are marked as
  kept from them.
- A given name that is also a common word or contraction ("하진" in "그렇게 하진 않았어") brings that character's facts
  when the message has the word; it adds a mention and removes none.
- A three-syllable foreign name whose first syllable is on the family-name list (도로시 → 로시) is split too; such a
  given name rarely appears alone.
- Each request reads the resolution's entities once more and scans its message for Hangul runs.
- Evaluation and latency: Phase 24 step 3. K32 (a persona narrated in the third person) is unchanged (PHASE-24 Q4).
