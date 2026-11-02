# Phase 54 — A name written in Hangul word by word is asked about by its first word

Status: **proposed**, 2026-11-02 (an owner request, not a roadmap stage: "이름부터 부탁할게", after the memory map of
the trial install's longest chat showed six characters split in two). Step 2 is built on a draft PR for the owner's
decision; nothing is merged, deployed or made a default before Q1–Q6 are answered.

**High risk** (`AGENTS.md §14`): **identity**. The change decides which name pairs the extractor is asked about; a
pair it confirms becomes an `also_called`, and an alias joins two names' facts and knowledge marks (ADR 0012).

Invariants it touches (`AGENTS.md §3`): **every automatic claim has provenance** (an alias written from a confirmed
pair keeps its turn, its quote and the pair listed in the extraction's stored hints, as before); **derived memory is
rebuildable** (stored extractions are unchanged; Q2).

## Why

Read on the trial install (6113, `0.5.0`, database `nmos_p32_try`), read-only, no model call.

1. **Six characters are two entities each.** In the trial install's longest chat (153 messages, 75 turns,
   `extract-v16` on `gemma4:31b-cloud`; a fantasy setting whose names are Western names written in Hangul) the
   entity list holds three main characters twice each, as a full name of two or three words and as its first word
   (mentions 67 and 36, 77 and 26, 64 and 22), and three minor ones so. None of them has a lorebook entry, so ADR
   0046's keys do not join them, and none has an alias row in the active generation. (Names below are synthetic.)
2. **The extractor was never asked.** NAME PAIRS (PHASE-28 Q4, ADR 0064) lists a known full name with a part of it
   that the turn writes apart, and the model confirms a pair by number. `name_parts` splits two shapes: a Hangul name
   of three or four syllables (윤하나 → 하나) and a Latin name of two words or more (Hana Yoon → Hana, Yoon). A name the
   story writes in Hangul word by word — a Western or Japanese name, the usual shape in fantasy and Japanese settings
   — gives no part, so no pair is ever listed for it. ADR 0064 records the gap ("NAME PAIRS splits Hangul names of
   three or four syllables and Latin names only") and left it until after 1.0 (owner, 2026-10-03; NMO-34).
3. **One model wrote the alias unasked, and it was lost.** The chat's first turns were extracted with
   `google/gemini-3.8-flash`, which wrote the alias of two of the three main characters' full names and first words
   on its own (`also_called`, valid, turn 1). The chat was then extracted again under `gemma4:31b-cloud`'s generation, which is
   active; its turn 1 has no alias, so the two pairs split. As PHASE-28 found on S2 (81 calls, no free alias), a model
   that is not asked mostly does not write it.
4. **Of 67 multi-word Hangul character names** stored on the trial install and the preserved gate databases, most are
   names (Western and Japanese names written in Hangul, of two or three words); the rest are descriptions (a possessive
   such as 윤서하의 아버지, an adjective and a creature such as 붉은 고블린, a role such as 주인 할머니) and a name with a
   title (에반 교수, 하준 씨).

## Questions

| # | Question | Recommended | Alternatives |
|---|---|---|---|
| Q1 | Which part of a Hangul name of several words is asked about? | **The first word**, of two syllables or more, for a name of two or three Hangul words (a one-syllable particle such as 델 or 폰 may follow), unless the first word ends in a modifier syllable (은, 는, 운, 던, 의: 검은 고양이, 윤서하의 아버지). It covers every split pair found (all six are the first word), and a title is never the part (에반 교수 → 에반). The pair is still listed only when the turn writes the full name and the part apart, not for a part two known full names share, not for the persona (PHASE-28 Q6), and it becomes an alias only when the model confirms it with a quote of the turn. | The first and the last word, as for Latin names: also covers a family name used alone (벨로스 for 리아나 벨로스), but a title or a creature's kind becomes a part (교수, 고블린), and no split by family name was found. A read-side join without the model: withdrawn in PHASE-28 Q4 (no proof of identity). |
| Q2 | Does it change the extractor generation? | **No.** `name_parts` is not in the generation fingerprint today, the prompt text is unchanged, and the pairs a turn was shown are stored in its extraction's hints (`names`), so provenance holds. No chat is re-extracted: turns extracted from now on list the new pairs; an existing split joins when a later turn writes both names, or after "Extract all history". | Put the rule in the fingerprint: every chat's recent window is extracted again under a new generation (paid on the owner's install) and the quiet weeks restart. |
| Q3 | How is it measured? | **(a) done, zero calls:** deterministic cases in CI and the replay below. **(b) the confirmation, bounded:** the 93 replayed turns that gain a pair, extracted again on isolated copies with the owner's extraction model, three runs each; pass = every listed name pair confirmed in a majority of runs where the turn says both names of one person, no description pair confirmed, and no other change in the turn's assertions beyond the run-to-run noise. An exact call and token estimate goes to the owner before any call. | The full live gate (`AGENTS.md §7` item 6, "Extraction"): the prompt text is unchanged, only which pairs are listed, so (b) measures exactly what changes. Only trying it on the trial install in play. |
| Q4 | What about the pairs the current rule lists for a three-syllable name that is not Korean (a transliterated name such as 카이토 / 이토)? | **Out of this phase, recorded.** The replay finds one transliterated three-syllable first name and its last two syllables (a 올라-like verb fragment) listed on 82 turns, and two more such pairs once each; the model refused every one (no such alias is stored). They cost tokens and can take a slot of `NAME_PAIRS` (8), and ADR 0064 lists 카이토 / 이토 as a candidate on purpose. | Ask only for a three-syllable name whose first syllable is a common family name (`variants.FAMILY`), as Phase 24 does on the read side; a Korean name with a rare family name would no longer be asked. |
| Q6 | What about a name whose first word has one syllable (얀 하르트, a Western name such as Jan or Lin)? | **Left out, recorded.** A one-syllable part is written at the start of countless words: the matcher lets a Hangul name take any following syllable, so 솔 is in 솔직히, 린 in 린넨, 윤 in 윤기가. Replayed (zero calls, same 5,246 extractions): allowing it adds 519 turns, 511 of them one name and title's one-syllable family name in words such as 오늘 and 오랜만에, 5 a family name and a title, 6 the one real given name. Allowing it only when nothing or a particle follows (은, 이, 에게, 씨, …) still adds 99 turns, 93 of them the same syllable as an interjection ("오!", "오, 그래?") and 6 the given name. Such a character is joined by a lorebook key (ADR 0046), the owner's link (ADR 0025) or an alias the model writes unasked. | The particle-only match with a list of one-syllable interjections and common words left out: brittle, and the replay has one such character in 67 names. |
| Q5 | When does it ship? | **Merged to `main` after Q3 (b); tried on the test install (6113) first; on the owner's install only after `1.0.0`.** `1.0.0` is tagged on `0.5.0`'s build (R8), so `main` moving does not change it; this reverses the deferral of ADR 0064's consequence (NMO-34) only for this gap. | Keep it after `1.0.0` as ADR 0064 says, on this branch. |

## Scope

In: `extraction.name_parts` (Q1), its deterministic cases, ADR 0064 decision item 6, `docs/KNOWN-ISSUES.md` K31, this
spec. Out: the prompt text, the generation fingerprint (Q2), the resolver, recall, any read-side join (PHASE-28 Q4),
the three-syllable rule (Q4), a one-syllable first word (Q6), kana or kanji names, a re-extraction, a default, a
deploy.

`name_parts` has a second caller, and it changes with it: `role_party_named`, which accepts a listed role's ending
only when the TARGET turn names the counterpart, counts the counterpart's given name alone (ADR 0064 item 4, the
owner's run of `7dbef46`: 강무진 called 무진). A counterpart written in Hangul word by word is now named by its first
word too (리아나 벨로스 called 리아나), under the same guards: not a part another known full name or alias holds, not
the persona's (`test_role_endings_target.py`). Before, such an ending was dropped unless the turn wrote the full name.
Q3 (b)'s copies count role endings as well.

## Step 2 evidence: the zero-call replay

`name_pairs` replayed on every stored `extract-v16`/`v17` extraction that kept its hints, with the old and the new
`name_parts`, from the extraction's own KNOWN ENTITIES, its turn text (the members' normalized text, joined as the
worker joins them) and the conversation's persona. 27 databases on the test Postgres: the trial install and the
preserved gate copies (`nmos_age24_9947d2c_*`, `nmos_b030_*`, `nmos_age28_s2`). The old rule's pairs equal the pairs
each extraction stored on every turn that stored any, so the replay rebuilds what the model was shown.

| | turns |
|---|---:|
| extractions replayed | 5,246 |
| a pair added | 93 |
| a pair removed | 0 |

| Pair added (listings) | turns |
|---|---:|
| main character, Western name of two words / its first word | 44 |
| minor character, Western name of two words / its first word | 18 |
| main character, Western name of three words with a one-syllable particle (델) / its first word | 11 |
| minor character, Western name of three words / its first word | 9 |
| character, Japanese name of two words / its first word (the family name) | 8 |
| main character, Western name of three words / its first word | 8 |
| minor character, Western name of three words with a particle / its first word | 2 |
| minor character, a name and a title / the name | 1 |
| a creature: a rank word and its kind / the rank word | 6 |
| a creature: a kind word and its kind / the kind word | 3 |
| two more creatures of the same shape | 2 |

Eight characters (101 listings) and four creature descriptions (11). A description is listed, not joined: the model
must confirm it with a quote of the turn, which Q3 (b) measures. The name with a title is listed once, not on the 13
other turns where the character's full name is known too: two known full names then share the part, and the namesake
guard leaves it out. Of the six split characters of the chat in Why (1), four gain a pair (the three main characters
and one minor); one has no stored turn that writes both of its names, so a later turn that does is the first chance;
one is a described character and its name, a shape ADR 0024 already handles. (Character names are left out: the
measured chats are the owner's.)

*Amended on the replay:* the first build asked for every word to have two syllables or more, and so gave no part for a
name with a one-syllable particle (세라 델 모렌); two of the main characters were such names. Only the first word needs
two syllables (a one-syllable first word, 윤 하나, still gives none).

## Acceptance criteria

- [x] Deterministic: a Hangul name of two or three words gives its first word; a description, a one-syllable word,
      a mixed-script name and a name of four words or more give none; the pair is listed only when the turn writes
      both apart, not for a shared part or the persona (`test_extract_v16.py`).
- [x] The generation key is unchanged (Q2): for the tests' settings `extract-v16` is
      `extract-78315fad68d2cef20e5e02e88e227f37` and `extract-v17` `extract-ca7705d83b48131b164c7444e6af612b` on `main`
      and on this branch alike, and the existing fingerprint tests pass unchanged.
- [x] Zero-call replay (above): no pair removed.
- [ ] Q3 (b), after the owner's estimate approval.
- [ ] Owner decisions Q1–Q6.
