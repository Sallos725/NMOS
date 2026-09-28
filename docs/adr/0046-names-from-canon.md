# 0046 — Names from canon: a lorebook entry's keys name one thing

Status: accepted, 2026-09-28. Phase 14 step 4 (`docs/phases/PHASE-14.md`, Q6). Builds on ADR 0045 (canon sources)
and ADR 0012 (entity identity); the owner's splits (ADR 0044) apply.

## Context

A character written in full as a three-syllable Korean name is usually called by the given name alone, and the given
name alone is no mention (K31). The story rarely says both in one turn, so no alias joins them. The lorebook often
does: an entry about a character lists the names it goes by as its keys, since the host activates the entry by them.
On sample 2 the lorebook keys hold the given names of six of the characters NMOS knows (`docs/perf/canon.md`).

## Decision

1. **An entry's keys name one thing.** For each lorebook entry of the canon in force, the resolver joins the keys as
   aliases of one character, but only when three conditions hold:
   - exactly one key is a character the head mentions, other than the persona;
   - no key names anything else the head mentions (a place, an item);
   - it is not the persona's entry. The persona's names are never a mention (ADR 0023).

   The other keys become that character's aliases, and each is a name a message can mention.
2. **The guard.**
   - An entry whose keys name two known characters joins nothing: it is about both, or about something else.
   - The guard looks only at the names the head mentions before any canon, so one entry's aliases never decide
     another's.
   - Two entries that give one key to two characters make that key ambiguous (ADR 0012), joined to neither.
   - One entry's names are joined to each other, so three keys of one entry are one thing, not an ambiguous name.
3. **The owner decides.** A canon alias is an alias like the story's: the owner splits it (ADR 0044), and the split
   says which names still join the two. The Inspector lists it with `canon` where a story alias shows its turn.
4. **Which canon.**
   - A request reads the names of its own manifest (ADR 0045) when the sidecar has it, else the canon in force.
   - A replay reads its request's manifest.
   - A read as of an earlier time reads the canon applied by then.
   - A chat without canon adds no query to a read.
   - Extraction's entity hints use the canon names too.
5. **Card and persona names** add nothing here. The bot's name is known from the host (ADR 0012), and the persona's
   (ADR 0023).

## Consequences

- On sample 2, with its canon, the given-name probes find the fact they ask for as often as the full-name probes (2
  of 3; 0 of 3 before). Its 17 M0 cases are unchanged, with and without vectors (`docs/perf/canon.md`).
- A lorebook whose keys are not names (the longest measured chat's) changes nothing.
- A key that is a common word ("시장") becomes an alias only of the one character its entry names, and a message
  that uses the word mentions that character. The owner splits it if it misleads.
