# 0046 — Names from canon: a lorebook entry's keys name one thing

Status: accepted, 2026-09-28. Phase 14 step 4 (`docs/phases/PHASE-14.md`, Q6). Builds on ADR 0045 (canon sources)
and ADR 0012 (entity identity); the owner's splits (ADR 0044) apply.

## Context

A character written in full as a three-syllable Korean name is usually called by the given name alone, and the given
name alone is no mention (K31). The story rarely says both in one turn, so no alias joins them. The lorebook often
does: an entry about a character lists the names it goes by as its keys, since the host activates the entry by them.
On sample 2 the lorebook keys hold the given names of six of the characters NMOS knows (`docs/perf/canon.md`).

## Decision

1. **An entry's keys name one thing, on top of the story.** After the story's resolution (its aliases, the owner's
   links and splits, ADR 0012, 0025, 0044), each lorebook entry of the canon a read uses is checked:
   - the keys the story knows must all name one entity, a character other than the persona;
   - no key may name anything else the story knows (a place, an item), or a name the story left ambiguous.

   Then the keys the story does not know become that entity's aliases, and each is a name a message can mention
   (K31). The persona's names are never a mention (ADR 0023), and the persona takes no canon alias.
2. **Canon never unsettles the story.**
   - A canon alias joins no two entities and splits none.
   - It changes nothing the story or the owner settled: a story alias or an owner's link stays, and no name becomes
     ambiguous because of canon.
   - A key the entries give to two entities is ambiguous, joined to neither, and listed with the story's ambiguous
     names.
3. **The owner decides.** The owner's split of an alias from its entity keeps that alias out (ADR 0044). The Inspector
   lists a canon alias with `canon` where a story alias shows its turn.
4. **Which canon.**
   - A request reads the names of its own manifest (ADR 0045) when the sidecar has it, else the canon in force. It
     records which manifest it used, none included.
   - A replay reads exactly that manifest.
   - A read as of an earlier time reads the canon applied by then.
   - A chat without canon adds no query to a read.
   - Extraction's entity hints use the canon names too.
5. **Card and persona names** add nothing here. The bot's name is known from the host (ADR 0012), and the persona's
   (ADR 0023).

The step's Codex review found three defects, all confirmed and fixed with tests:
- two entries sharing two aliases could merge two characters;
- a canon alias could make a story-joined name ambiguous, or take a persona alias away from the persona (the first
  design joined canon keys inside the story's alias graph);
- a request that named a manifest the sidecar did not have yet read the current canon, but its replay read the
  manifest that arrived later.

## Consequences

- On sample 2, with its canon, the given-name probes find the fact they ask for as often as the full-name probes (2
  of 3; 0 of 3 before). Its 17 M0 cases are unchanged, with and without vectors (`docs/perf/canon.md`).
- A lorebook whose keys are not names (the longest measured chat's) changes nothing.
- A key that is a common word ("시장") becomes an alias only of the one character its entry names, and a message
  that uses the word mentions that character. The owner splits it if it misleads.
