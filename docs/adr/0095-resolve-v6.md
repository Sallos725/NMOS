# 0095 — `resolve-v6`: an alias has a direction, a composite persona name is several names, derived names are links

Status: accepted, 2026-11-25, PHASE-65 (S3). The owner's plan, decision 2 (directed ambiguity; `secondkey` out of the
aliases; composite and bilingual persona names, their given and first names and spellings linked in the resolution,
splittable). Amends ADR 0012 (items 2 and 3 and the 2026-10-03 amendment), ADR 0023 (item 3), ADR 0046 (item 2) and
ADR 0058. `RESOLVER_VERSION` is `resolve-v6`. Recorded as built at `361130c`.

## Context

Four faults of the read-time resolver (audit B1, B2, B4, B5):
- Ambiguity was read from the alias graph without direction (ADR 0012 item 3), so a character with two nicknames that
  are not parts of the name (`세라 → Sera`, `세라 → 별빛`) became ambiguous and joined nothing.
- Canon never joined two entities (ADR 0046 item 2), so a lorebook entry whose keys are one character's full name and
  given name could not join what the story kept apart; and the plugin sent PocketRisu's `secondkey` (trigger words,
  not names) among an entry's keys.
- A host persona name made of several names (`A / B`, `A (B)`) was one unknown name; `node()` folded any name ending
  in the persona's last word into the persona, so an NPC whose name ended that way was taken and could not be split.
- Single-syllable Korean names, Western first names, two-syllable family names and `@name` with a vocative or an
  honorific were missed.

## Decision

1. **Direction.** Beside the undirected alias edges the resolver keeps who named whom (`subject → value`). A name that
   is the subject of every alias counted for it is one person, however many aliases it has. A target two names share
   stays ambiguous. A name with aliases both ways keeps the undirected rule (ADR 0012 amendment of 2026-10-03, so the
   S1 turn-237 letter case resolves as before). A `?` description never makes a name ambiguous. An owner link on an
   ambiguous name drops only the aliases by which other names claimed it.
2. **Canon may join one person's names.** After the story's resolution, a lorebook entry joins character roots the
   story keeps apart when their names are one person's: a word of the other name, its given name, or a romanized
   spelling. Refused when the entry names the persona, a key names an entity of another type, another entry names one
   of the roots together with a different known entity, or the owner split any pair of them. An entry naming unrelated
   characters (a pair or group entry) still joins nothing. The plugin sends `secondkey` as
   `metadata.trigger_keys`, never as keys.
3. **A composite persona name.** `persona_parts()` splits the host's persona name on `/`, `|`, `·` and parentheses into
   primary names; `node()` folds only `USER_NAMES` and those into `{{user}}`, and no longer folds a name by its last
   word.
4. **Derived persona names are links, not folds.** A primary name's given name (two-syllable family names and spaced
   names included), a Western first name, Hangul spellings of a Latin name (strict keys, or vowel-folded keys of 5 or
   more for the persona only), Latin spellings of a Hangul name, and surname plus persona without a title join the
   persona in the resolution as links the owner can split (`name_split`, ADR 0044). One stays off the persona when the
   owner split it from any persona name or linked it elsewhere, when another name gives it as its alias, or when
   another character's full name holds it. The persona's entity id stays the `{{user}}` node's.
   `entities.names_persona(type, name, persona)` reads one name against the persona without a resolution
   (extraction's `role_toward` check, `scene.is_persona`, carry).
5. **Names and mentions.** `given()` knows two-syllable family names (`FAMILY_TWO`, pinned equal to extraction's) and
   spaced names; `latin_keys` indexes the first word that is not a title; Hangul spellings and the alias scan go to six
   syllables. `@name` strips vocatives (아 / 야 / 여), 께서 / 께 and honorifics (님 / 씨 / 군 / 양, before at most one
   particle), takes up to three words and inner apostrophes, and reads aliases; an alias two keys share names neither.

## Consequences

- Entity ids change once (`resolve-v6`). They are not stored: pins and exclusions are kept by name, and a recorded
  request's ledger refers to assertion ids, so only chats whose grouping actually changes replay differently.
- A nickname two characters share, written reversed (`별명 → A`, `별명 → B`), now merges A and B: an accepted cost. The
  guards are the owner's split and the alias confirmation (ADR 0064).
- 크리스티나 / Christina and 에단 / Ethan still do not match (Hangul adds a vowel; the keys do not fold th to d);
  vowel-folded keys can over-match for the persona. The owner splits such a link (K52).
- A persona whose name changes in the middle of a chat still takes the new name for the whole chat (ADR 0023); a
  per-turn persona is PHASE-67's.
