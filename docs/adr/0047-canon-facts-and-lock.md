# 0047 — Canon facts: read by the model, before turn 0, and the owner's lock

Status: accepted, 2026-09-28. Phase 14 step 5 (`docs/phases/PHASE-14.md`, Q3, Q4, Q5, Q7). Builds on ADR 0045
(canon sources), ADR 0046 (names from canon), ADR 0014 (generations serve what they cover), ADR 0027 (replay) and
ADR 0044 (owner repair). Migration 0026.

## Context

Step 3 keeps each chat's canon (the card, the persona, the author's note, the lorebook entries) as immutable sources,
and step 4 takes names from the lorebook keys. What canon says about the characters and the world is not memory yet:
a card that makes one character another's sister, or a lorebook entry that says who someone is, reaches the model
only when the host sends that text. The host sends the card and the persona every time, and a lorebook entry only when
its keys come up (H19). What NMOS keeps must also stay the story's: the story changes things, and the owner decides
when canon and story disagree.

## Decision

1. **A projection of its own (Q3).** A `canon` generation reads canon with the extraction model and endpoint. It is
   its own kind: the message extractor, its prompt and its generation do not change, and nothing is extracted again.
   Its key hashes its version (`canon-v1`), prompt, predicates, normalizer, model settings and part size.
   - It reads each text of the canon in force once: the card's story fields and greeting, the author's note and the
     persona at once, and a lorebook entry once a request's prompt held it (the plugin reports which), then each new
     text of that entry. An entry the story never activates costs nothing.
   - A text is read in parts of up to 6,000 characters, at most 4 (24,000 characters); what is left is recorded as
     not read. Each part is one model call, stored as an extraction of the canon revision (window `canon:<part>`)
     with its assertions, like a turn's.
   - The host's name macros (`{{char}}`, `{{user}}`) are replaced by the card's and the persona's names first, as the
     host does in a prompt. A text that uses them is read for the names its manifest gives (the window records them),
     so renaming the card or the persona reads such texts again; a text without them is not.
   - A text counts as read once every part is: a read stopped between parts (a failure, then the switch turned off
     and on) goes on with the parts it lacks.
   - The prompt asks for how things stand before the story: who someone is, traits, condition, relationships,
     feelings, forms of address, places, belongings, groups, knowledge, the past (`event`) and the world
     (`world_fact`). Instructions to the AI, templates and example dialogues are not facts. Open business (goals,
     promises, threats, debts, questions) and the story's own moves belong to the story: such an answer is kept as
     pending ("not a canon predicate"), never a fact. Canon's names come from the lorebook keys (ADR 0046), not from
     the model (`also_called` is not asked for).
   - Jobs are queued when a manifest becomes the canon in force, after a request whose prompt held a lorebook entry
     for the first time (after the answer, off its path), when the generation changes, and on "extract all history"
     and a rebuild (which discards the canon's extractions too). `NMOS_CANON_FACTS=0` or the panel's switch turns it
     off: nothing is read and no canon fact is used.
2. **Before turn 0; the story supersedes it (Q4).** A read takes the canon facts of the manifest its request names,
   served per revision by the active canon generation or else the most recently activated one that read it (ADR
   0014). While the sidecar lacks that manifest (its upload is under way), the read has no canon facts: the canon in
   force may still hold an entry the host no longer shows. (Names fall back to the canon in force, ADR 0046.) They are facts from before turn 0 (turn -1, `canon` set to the key) and
   fold with the story's: a story statement of the same fact is a new version from its turn. Canon facts take no part
   in secrets, threads or the scene's cast, and a canon claim (a greeting's line) is a claim.
3. **A contradiction is listed (Q4).** For `identity` and `relationship` (since amendment 1, `relationship` only), who someone is and how two stand, a story
   statement that replaces or denies a canon one saying something else is listed in "Needs attention" with the
   owner's choices: keep canon's (a lock, below), keep the story's (canon's statement retracted, ADR 0044), or leave
   it (the story's stays current). A place, a condition, a feeling or a form of address changes as the story goes;
   there the story supersedes canon without a listing.
4. **The owner's lock (Q7).** `fact_lock` is an owner repair (ADR 0044's table, undo and audit) on a canon fact or the
   owner's correction. The locked version stays current: a later statement that would replace or end it is held off
   and listed as a conflict (`locked`), and one that says the same (subject included: a new holder is a change) is
   left out. A relationship's two directions hold their own locks. A lock finds a canon fact by what it
   says in its canon text (the key stands for the turn), so a new generation or a card edit that keeps the fact keeps
   the lock; one that matches nothing is listed. A story fact cannot be locked: the owner corrects it first.
5. **The packet (Q5, D3).** A canon fact whose text the request's prompt held is not sent again: the host sent it.
   Otherwise it reaches the packet like any fact, marked `source="canon"` in place of a turn (an entry the host did
   not activate this time, a correction of a card line). A locked fact that holds off a story statement is sent even
   when the prompt holds its text, marked `locked="true"`: the prompt's recent messages may say otherwise. The Note
   explains either mark only when a kept line uses it. No new packet policy: only lines of canon facts are new, so
   recorded packets replay as they were.
6. **Replays.** A request records the canon generation it read (`canon_key`) and the manifest whose facts it read
   (`canon_facts`, none included) with its recall options; its replay reads exactly those, as NMOS had them at its
   time, with the keys its prompt held. A request from before this step reads none.
7. **Plugin.** The plugin's check of which canon texts a prompt holds puts the names in for the name macros first,
   and counts a text as held when 80 % of its lines are in the prompt (the host renders other syntax too). Before,
   a card whose description used `{{char}}` never counted as held, so the plugin read the card again on every request.
   The panel has the switch and the lock button. New plugin build.

The step's Codex review found five defects, all confirmed and fixed with tests:
- a request whose manifest had not arrived read the facts of the canon in force, so an entry the owner had just deleted
  could still reach the packet;
- a read did not depend on the names the macros stand for, so a renamed card or persona kept facts under the old name;
- a text read in part counted as read, so its other parts were never read after the job was retired;
- only the last lock of a relationship pair held: the other direction's could be superseded;
- a new holder of a locked item counted as a restatement, so it was dropped instead of held off, and the lock did not
  reach the packet.

## Consequences

- Canon costs model calls in the background, a few per chat at first (on sample 2: its card, persona and 45 always-
  active entries), then one per new text a prompt holds. The Inspector's coverage shows the calls made and what is
  left; the canon table shows which texts were read.
- A card's line the story contradicts is listed once per contradiction; a chat whose story changes who someone is
  often lists each change until the owner chooses.
- A lorebook entry read once stays in memory while it is in the canon in force, whether or not later prompts hold it;
  its facts reach the packet only when the prompt does not hold its text.
- Renaming the card or the persona reads again every text that uses the name macros (on a real card, most of it).
- Measurements on the two measured chats (the calls canon takes, M0, the secret gate, latency) are step 6: amendment 1.

## Amendment 1 — relationships only are listed; the cost measured (Phase 14 step 6, 2026-09-29)

**Context.** On the two measured chats with their canon (`docs/perf/canon.md`, step 6), 10 canon conflicts were listed
and about one was a contradiction. Sample 2's lorebook and persona are written in English, so their facts are in
English, and the story's Korean statement of the same identity read as "something else" (6 of its 8). `identity`
holds one value, so a second true description (a job, then where someone lives) replaced the first (both of the
longest chat's). No relationship conflict was listed on either chat. Latency with a 200-entry lorebook every entry of
which was read missed the +5 ms criterion: a canon fact costs what a story fact costs in the fold.

**Decision** (the owner, 2026-09-29):
1. Only `relationship` is listed (item 3). A story statement of who someone is supersedes canon's without a listing,
   as a place does; the owner can still lock or retract a canon identity from its line, and a lock holds as before.
   Telling a new identity from the same one in other words needs a model; that is left for later.
2. The canon-facts query is prepared once per connection (its planning took longer than its run). The rest of the
   cost is recorded, not optimized here: a faster fold serves story facts as much as canon's.

**Consequences.** "Needs attention" lists nothing on the two measured chats. A card whose identity the story really
contradicts is not flagged; its canon version stays in the fact's history. The latency is `docs/perf/canon.md`
(K36).
