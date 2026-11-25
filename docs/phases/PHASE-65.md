# Phase 65 — Tier 1 fixes and Tier 2: bug fixes under every policy, `packet-v21`, the author's note in the chat's language, status windows by more shapes

Status: **approved**, 2026-11-25, as a correction phase beside the current phase (`AGENTS.md §7` item 5). The owner
approved the remediation plan of an audit of 52 painful gaps (finding ids A1…G7) with twelve design decisions before
the run, and decided four more things during it (below). Not a roadmap stage. Numbered 65 because Phase 63 (scene
contrast, closed) and Phase 64 (conditional forms of address, on production since 2026-11-25) were taken.

**This document records what was built, at `361130c`** on `Sallos725/audit-conditional-address-terms` (the
integration branch of the Tier 1–4 run, Phase 64's PR #343 merged in as its base). Later commits on that branch are
not described here. **Nothing of it is pushed, merged to `main`, deployed or measured on a live host; no paid model
call was made.** Every check is zero-call.

The same branch also holds work of two later phases, still being built: **PHASE-66** (`clean-v4` and `extract-v21`'s
typed ontology with its read side; migration `0041_extract_v21_ontology.sql` and a selectable `extract-v21` are
already merged) and **PHASE-67** (Tier 4: extraction right after a reply, repair anchoring, branch inheritance; the
plugin's background sync after a reply is already merged). Their phase documents come with them. Where a deploy of
this branch would carry their parts, the deploy section says so.

**High risk** (`AGENTS.md §14`), each with the guarantee it touches:
- **retrieval and injection semantics under every packet policy**: Tier 1's read-side fixes (secret matching, the
  symmetric-relationship words, the claim key, carried rows as secrets, the scene cast without excluded entities,
  canon blocks, the status questions and clock keys, the story's leak bar) change what `packet-v20` and older policies
  select. ADR 0027 says the packet compiler is versioned and the gathering code is not, so a recorded request whose
  gathering such a fix touches no longer replays byte for byte (the list is under "What a deploy does");
- **identity** (`resolve-v6`): composite persona names, the direction of an alias, derived persona names, canon joins
  (ADR 0095);
- **canon**: which canon read is served (persona and card texts read under the chat's names, earlier `plain` reads
  carried forward; ADR 0047 amendment);
- **secrets**: the author's note's cross-script check, carried secrets, the reveal check's turn selection
  (ADR 0057 amendment, ADR 0093), and every `packet-v21` gate;
- **stored data written from now on under unchanged generation keys**: the extraction worker's post-processing, the
  reveal check's rules and what the summarizer is sent changed without a new extractor, reveal or summarizer version
  (Open question 1);
- **the worker's job order** (`claim`: a chat's turns in story order) and the discard lock;
- **stored state keys** of status windows (ADR 0094);
- **the request path in the plugin**: prompt matching, placement, trimming and its refetch, fail-open.

Invariants it touches (`AGENTS.md §3`): **character knowledge is not world knowledge** (secret matching, carried
secrets, every `packet-v21` gate, the author's note check); **inactive sources may not influence the next packet**
(the scene cast's exclusions, the `allBefore` cut in the plugin); **every automatic claim has provenance** (the
evidence check reads the text the model was shown, `shown_target`); **unknown is a valid result** (an unrecognized
polarity parks the row pending instead of turning it positive; an ambiguous alias stays ambiguous); **the system
fails open** (the plugin's trim refetch, the note's leak check failing closed for the note only).

## Why

The audit listed 52 gaps found by reading the code (no live run). Some were plain bugs under every policy: a row cap
that cut derived reveals, a polarity read as positive when the model wrote "NEG", a revealed secret ending every
other belonging of its holder, a lorebook alias that made a character's real name ambiguous, canon facts lost to one
`{{#if}}`, a plugin that matched a reasoning model's reply to nothing. Others changed what a packet selects and so
need a new packet policy (ADR 0027): the forensic quote route started on ordinary dialogue quotes, the persona was
missing from `<Cast>`, feelings recorded since Phase 58 were never printed. The owner's decision 1 set the split:
Tier 1 bug fixes go in under the existing policies; selection changes go behind `packet-v21`; replays of `packet-v20`
and older stay as they are except where a bug fix in the gathering code reaches them.

## Scope, by area

Each item names its finding ids, the files and the test file that pins it. Test files are under `apps/sidecar/tests/`
unless they are the plugin's (`adapters/pocketrisu-plugin/test/`).

### S1. Extraction, predicates, worker order, read model (Tier 1; every generation; no key change)

`extraction.py`, `predicates.py`, `readmodel.py`; `test_tier1_extraction_bugs.py` (45 tests).
- **D1.** The 40-assertion cap applies to the model's own assertions only (`own_items`, `capped`); reveals, role
  endings and confirmed name pairs the worker derives are never cut. A model item can no longer carry the worker's
  internal markers (`listed`, `listed_pair`, `held`, `doubt`).
- **D2.** `polarity_of` reads `negated`, `neg`, `false`, `no` and JSON `false` as negative; an unrecognized polarity
  parks the row `pending` instead of turning it positive (`ended_roles` reads the same). Name pairs, reveals and
  `same_names` read the TARGET as the model was shown it (`shown_target`).
- **D4.** A stray `value` on `located_in`, `possesses`, `member_of` is dropped (`takes_value`). Rows written before
  keep theirs (Leftovers).
- **C4.** `revealed` takes the resolution, so an alias or another name of the persona counts for the listed
  kept-from name.
- **C5, D4.** `load_context` reads the owner's repairs in force before the target turn; the promise, thread, secret
  and role hints apply retract, correct and restore and the thread and secret repair events before folding.
- **G2.** `story_clock` strips a `<prefix>.` from a key, reads 현재 시간 / 현재 시각 / 일차 / day / 요일 / 계절 as their own
  categories, and never shows fields more than one turn older than the newest one (no clock stitched from two turns).
  `places_later` keeps a LATER clause unless the clause dates the change itself now (오늘부로, 예정보다 일찍, "as of
  today", "effective immediately"); bare 이미 / 당장 / 방금 / already / just / today are not such markers.
- **D5.** `claim` holds an extract job while an earlier job of its chat and generation, in its lane or a more urgent
  one, is running or queued, so a chat's live turns run oldest first (a live turn does not wait on an earlier live
  turn in retry backoff). `discard_turns` locks the jobs of the turns it obsoletes (`FOR UPDATE`, ordered by id).
  `readmodel.turn_generations` reads one commit; `readmodel.membership` falls back to the generation serving the turn.

### S2. Secrets, fact folding, threads, dropped facts, repairs, scene cast (Tier 1; every policy)

`secrets.py`, `facts.py`, `threads.py`, `dropped.py`, `repairs.py`, `scene.py`;
`test_tier1_secrets_facts_repairs.py` (24 tests).
- **C1, C5.** A secret line of a predicate that takes no value ("X possesses Y") splits its object off as content, so
  revealing one belonging no longer reveals the others; secret heads compare by subject, predicate and object (by
  entity when the resolution knows both names, else similarity per part), so near-identical names do not collide;
  rule 1 of a reveal needs content overlap except for the one same-head secret of a valued turn (ADR 0033 amendment 2
  kept); `[turn -1]` parses.
- **C4.** `hidden_from` drops a revealed character under every name it goes by.
- **F2.** Rows carried by a `continue` link (ADR 0085) fold as secrets of the target.
- **A7.** A claim is keyed by its speaker's entity (with Phase 64's address slot).
- **A3.** 적 counts as a symmetric relationship word only on its own or in 숙적; English possessives and ex-, former,
  fake, unrequited, one-sided are not symmetric.
- **C3, C7.** A thread's `closed_by` keeps the closing row's knowledge marks; a short aim (under 4 characters) said
  again word for word restates the open one; a `resolves` claim by the thread's counterpart, or anyone's `answered`
  for a question, closes it; gossip still closes nothing. Thread folding takes the rows the owner's fact repairs left.
- **D6, D7.** `dropped` reads `feeling`; a multi-valued fact is held only by the same value, and every fact only by
  the same polarity. `repairs.match_fact` tells story, canon and carried facts apart (`fact_target` records which;
  a legacy target with only turn -1 stays canon's); `_restates` needs equal polarity and, at level 2, a similar value
  for a multi predicate; an exclusion never hides the persona.
- **D6.** `scene.cast(excluded=…)`: an entity the owner marked not a character is never in the scene cast. Wired at
  every `retrieval.py` call site (`_scene_cast`) for **every policy** (in `a52e85b`). Latin names match as whole
  words; a knowledge mark's given name maps to its entity.

### S3. Identity, aliases, the persona, `@name` (Tier 1; `resolve-v6`)

`entities.py`, `variants.py`, `mentions.py`, and the call sites in `extraction.py`, `scene.py`, `carry.py`
(`aa331c1`); `test_tier1_identity_persona.py` (47 tests). Decision: ADR 0095.
- **B1.** An alias has a direction. A name that is the subject of every alias counted for it (one name pointing at
  two others) is one person, not ambiguous; a target two names share stays ambiguous; a mixed name keeps the
  undirected rule. A `?` description never makes a name ambiguous. An owner link on an ambiguous name drops only the
  aliases by which other names claimed it.
- **B2.** A lorebook entry joins characters the story keeps apart when their names are one person's (a word of the
  other name, its given name, a romanized spelling), unless the entry names the persona, a key names another kind of
  entity, another entry names one of them with a different known entity, or the owner split them. An entry naming
  unrelated characters still joins nothing (a deviation from the plan, below). The plugin sends `secondkey` as
  `metadata.trigger_keys`, not as keys (S7).
- **B4.** A host persona name made of several names (`A / B`, `A | B`, `A · B`, `A (B)`) splits into its primary
  names, the only ones folded into `{{user}}`; `node()` no longer folds a name by its last word. Derived names (a
  given name, a Western first name, Hangul spellings, a Latin spelling of a Hangul name, surname plus persona without a
  title) join the persona in the resolution as links the owner can split, unless the owner split or linked them
  elsewhere, another name gives them as its alias, or another character's full name holds them.
  `entities.names_persona` checks one name against the persona without a resolution (extraction's `role_toward` check,
  `scene.is_persona`, carry).
- **B5.** `given()` knows two-syllable family names and spaced names; `latin_keys` indexes a Western first name;
  Hangul spellings up to six syllables. `@name` strips vocatives (아 / 야 / 여), 께서 / 께 and honorifics (님 / 씨 / 군 /
  양), takes up to three words and inner apostrophes, and reads aliases.

### S4. Canon, divergence, status questions, clock keys, summaries, coverage (Tier 1)

`canonfacts.py`, `divergence.py`, `statechange.py`, `source_time.py`, `summaries.py`, `coverage.py`;
`test_tier1_canon_state_coverage.py` (16 tests), `test_tier1_canon_carry_forward.py` (8 tests).
- **B6.** A conditional block's verdict is taken on the text the model read (cleaned, name macros replaced), cached
  per revision and names, so one `{{#if}}` no longer drops unconditional facts that quote `{{char}}` / `{{user}}`.
- **B7.** A persona or `card:*` text is read under the chat's names (`wtag()`, `WTAG`), never `plain`, so another
  chat's read under other names is not copied and a rename reads it again; lorebook entries and the note keep
  `plain`. **Owner decision (below): an earlier `plain` read of such a text without name macros keeps serving**
  (`47a020a`): per canon generation, its read under the chat's names if one exists, else its `plain` one. ADR 0047
  amendment.
- **B8.** `divergence` leaves CBS conditional spans out of the setting; a quote with Hangul needs `QUOTE_MIN_KO`
  (6) characters; an optional `held_keys` would limit lorebook candidates to entries the chat's prompts held, but no
  caller passes it yet (Leftovers).
- **G1.** `statechange.tell` tells a key the message asked about even when it did not change.
- **G2.** `source_time` matches clock keys by their last part (`Status.Date`), gives new clock keys their own
  categories and reads more temporal cues (일차, 무슨 요일, 며칠째 …).
- **C1, C3, G4.** `summaries.content` gives a valueless secret's object as its content (stored summaries listed under
  the older whole-line key stay valid); the story leaves out scenes at `LEAK_NEAR`; a scene window the prompt holds
  only in part can be offered; `coverage.read` does not count a summary held at `LEAK_NEAR`.

### S5. Carry, regression, the API's carried reads, archive (Tier 1)

`carry.py`, `api.py`, `archive.py`; `test_tier1_carry_archive.py` (23 tests). ADR 0085 amendment.
- **F1.** A regression may name the persona (`{{user}}` or any of its spellings), alone or with characters; its
  rememberers follow knowledge marks for every row (public: everyone named; limited with `known_by`: those named;
  otherwise only those involved), so world facts, item places and told third-party secrets are kept.
  `carry.MAX_ROWS` is 5,000 (was 2,000).
- **F2, F3.** Owner entity links and the named regressors' aliases are carried; persona aliases map by spelling; a
  source's own `continue` link is read (a chain of chats, with the first chat's provenance, never the target's own
  memory back); the story is held at `LEAK_NEAR`. Previews, joins, repairs, the repair list and the author's note read
  the link in force (`carried=True`); the link is part of the preview fingerprint. `carry.regression_threads` returns
  closed regression threads (read by `packet-v21`, S10).
- **C5.** A `secret_keep` or `secret_found_out` repair, made or taken back, queues `summaries.schedule_stale`.
- **F4.** An archive's manifest lists the carry links it leaves out and the chats they point to, by id
  (`carry_left_out_details`, `carry_left_out_conversations`). A self-contained snapshot was not built: the link's
  foreign keys are `NOT NULL`.

### S6. Reveal checks, the embedding cap in the panel, wiring (Tier 2 wiring)

`api.py`, `runtime.py`, `config.py`, `reveals.py`, `models.py`; `test_tier2_api_wiring.py` (27 tests).
- **C5.** `reveals` reads each turn's serving extraction as the fact read chooses it (fallback generations after a
  carry-on included); skips a turn whose active-generation extraction is queued or running (it is about to be
  replaced); judges "already listed" per secret; matches stale listings with the read side's fold. `process` passes
  `shown_target` and the resolution to `revealed`. No reveal version change (Open question 1). ADR 0057 amendment.
- **E8.** `embed_max_chunks` is a panel setting (`GET /v1/config` `embeddings.max_chunks`, `PUT` `embed_max_chunks`,
  1–64; a change is a new embedding projection, re-embedded with no extraction call); the environment's value stays
  the default. **Startup now refuses `NMOS_EMBED_MAX_CHUNKS` above 64.** ADR 0062 amendment.
- **C2.** The author's note's cross-script check is wired (S8).
- **G4.** `TrimRequest.keep_recent_turns` defaults to 16 (was 20; a multiple of the 8-turn summary window).
- The memory map reads the carry link in force.

### S7. The plugin (Tier 1, and two Tier 2 controls)

`adapters/pocketrisu-plugin/src/prompt.ts`, `trim.ts`, `placement.ts`, `canon.ts`, `core.ts`, `form.ts`, `ui.ts`,
`i18n.ts`, `scripts/build.mjs`; `test/tier1.test.ts`, with updated `core`, `trim`, `prompt`, `host`, `form`, `dom`
tests.
- **G5.** `cleanText` drops `<thoughts|think|thinking>` blocks as `packet.py` does, so a reasoning model's reply
  still matches its anchor. A `disabled: 'allBefore'` message and every message before it are inactive
  (`activeStartIndex`, in `latestUserIndex`, `matchPromptToHost`, `queryTexts`, `trimPrompt`). Multipart text parts
  are joined, not JSON-stringified. A short user turn (under 6 characters) matches an exact message first, searched
  after the newest prompt message matched to earlier chat; a prompt holding none of the chat is rejected. Matching
  prefers a prompt message of the fitting role.
- **G7.** `hasPacket` also sees a whole packet in a user block that is not chat text; a chat message that itself
  mentions `[NMOS.memory]` no longer takes the preset's placeholder.
- **G3.** `name`, `removable` and `cachePoint` may ride on a dropped message; a cache point moves to the first kept
  message; unmatched system blocks between dropped turns are kept; `canTrimPrompt` decides before `/v1/retrieve`
  whether to ask for a trim; a boundary the prompt refuses is never paired with the pre-cut packet: the packet is
  fetched once more without trim inside the same deadline (fail open if that fails), and the refusal is remembered
  for 10 minutes. HOST-FACTS "Keys on a prompt message".
- **G4.** The trim's default `keep_recent_turns` / step is 16 (was 20).
- **B2, G6, G7.** `secondkey` goes to `metadata.trigger_keys` (only when non-empty); `heldKeys` reads multipart
  prompts; the card is read again when personality or scenario drops out of a prompt that held it; an empty packet is
  cached 60 s and dropped after a reply.
- **Tier 2 controls:** "Embedding chunks per message" in Recall tuning (sent only when `GET /v1/config` reports
  `embeddings.max_chunks`); the Author's Note Studio's "Note language" select (`chat`, the first option, or `en`).

### S8. The author's note in the chat's language, with a cross-script secret check (Tier 2)

`notes.py`, `api.py`; `test_tier2_notes_status_vectors.py` (notes part), `test_notes.py` (two tests changed to the
new contract), `test_tier2_api_wiring.py`. Decision: ADR 0093.
- **C2.** `notes.Ask.language`: `"chat"` (the default, and what an older plugin's request without the field gets)
  or `"en"`. `"chat"` reads the chat's language from its scene summaries (then threads and facts) and has the model
  write in it; `"en"` keeps the prompts byte-identical to before. **So the default changed**: a Korean chat's
  chronicle and custom part are written in Korean with no switch.
- With `"en"` and secrets left out, a model-written part is also checked by meaning (`semantic_leaks`): by the
  configured embedder (`embedding_leak_checker`, cosine ≥ 0.62), else by one call of the note's model
  (`model_leak_checker`); a checker that fails counts as a leak (fail closed for the note). The lexical check
  (`tells`) runs on every line as before.
- Open-thread and assembled lines go through `tells` line by line; open threads are capped at 15 newest and 25 % of
  the part, with "+N more".
- Before the first scene summary (or with the summarizer off, or every summary held), the chronicle and the custom
  part are made from the shown threads and NOW facts; `no_scenes` only when there are neither. That is a model call
  where there was none.

### S9. Status windows by more shapes, keys that stay (Tier 2; owner decision on keys)

`statusshape.py`, `parsers.py`, `statechange.py`, `statewatch.py`; `test_tier2_notes_status_vectors.py` (status
part), `test_tier2_status_key_compat.py`. Decision: ADR 0094.
- **G2.** Windows read in more shapes: a nested-aware `|` split, 【】《》『』 brackets, a short bare segment continuing
  the field before it, multi-line windows (a bracket, a header line, a status-word header, a fence), two-column
  Markdown tables, HTML cards through an offset-mapped text pass (`<style>`/`<script>` dropped, block and cell
  boundaries kept); dialogue and speech-like values are no window.
- **Owner decision on keys:** stored keys do not move. A window is keyed `<character>.<key>` only when one reply holds
  windows of two or more different characters sharing a non-scene key; scene keys (clock, place, weather, season) are
  never prefixed; a place is never an entity; a one-character window keeps its bare keys. A bare pin or watch covers a
  key by its last part (`HP` covers `서연.HP`), a full one only itself. What the earlier rules read is read the same way
  (the one-line `[..]` window wins an overlap; the split falls back to every `|` when that reads more keys).
- **Status questions:** `retrieval.asked_keys(..., every_window=True)` under `packet-v21` only: a message that names
  no character any key is prefixed with asks that key of every window ("HP 얼마야?" with two characters' windows).
  Earlier policies ask none of them, as PHASE-39 Q3b pins (`361130c`).

### S10. `packet-v21` (Tier 2; opt-in)

`packet.py`, `retrieval.py`, `audit.py`, and the opt-in rules in `quotes.py`, `keywords.py`, `gone.py`,
`overuse.py`; `test_tier2_packet_v21.py` (56 tests), `test_tier2_quotes_kw_gone_overuse_map.py`. Decision: ADR 0092.
`packet-v21` is `packet-v20` plus what only it does; every addition is gated on `V21_POLICIES`; `DEFAULT_POLICY`
stays `packet-v19`.
- **E1.** The quote route starts only beside a question or recall cue read outside the quoted words; a `<Quote>`
  longer than the excerpt share no longer collapses the excerpt reserve (the first excerpt that fits takes it).
- **E2.** v21 keywords strip at most one question ending and one particle that fits the final consonant, keep tokens
  with digits, demote literary verb endings; particle lookup accepts plurals.
- **E3.** The reranker reads `sem_query` and the matched vector chunk (padded by 200 characters); after a rerank its
  own order decides what clears the excerpt floor.
- **C3, C6, E5.** Every excerpt and quote is checked against the secrets still kept from someone present: fenced in
  `<Private>` with its marks in normal mode, withheld (`secret_gate`) in strict and narrator modes. `<State>` and
  `<StateHistory>` values that repeat such a secret are withheld (values with fewer than 3 letters are not gated).
  A public line drops a `because`, `disputed_by`, `before` or `first` clause that repeats such a secret. A settled
  thread reads under its closing's marks when they are narrower. `told` lines read `participants` and are gated only
  for someone present. Strict mode keeps an unspoken `feels_toward` (limited, kept from no one by name) readable in
  `<Private>`.
- **A4, C8, E4, E5.** A `feels_toward` line carries its feeling detail (extract-v18). `<Cast>` reads 4 turns
  (`CAST_TURNS_V21`); holds peer feelings and forms of address between scene characters (a pair's address slots
  together or not at all; a pair with a slot the scene may not read stays out), and a persona group (where, condition,
  what they carry); these extras are placed after every `packet-v20` line within `CAST_EXTRA_SHARE` (0.15) and never
  into the room held for lead and `<Private>`. Facts `<Cast>` or a gone pin already say are not said again and the
  next one takes the slot. A title the persona uses for one character becomes an alias; `@이안` pins 백이안 (variants).
  A first-person message brings the persona's own aims, questions and threats; the persona's settled threads are
  included. Supportive summaries yield to lead and `<Private>` lines.
- **E6.** Gone and the return gap read only rows that show the character present (narrated, actual, as the subject);
  v21's gone word lists; a death carried by a `continue` link stays pinned.
- **E7.** Rerolls of one turn count once for rest, the current request's earlier attempts not at all; standing facts
  (`addresses`, `feels_toward`, `relationship`, `role_toward`) and settled threads never rest. `audit.replay` passes
  the same `dedupe_positions` / `exclude_position` under v21, so a v21 replay matches the live request.
- **E8.** A replaced value drops an excerpt only when the excerpt names the fact's subject; `when_happened` is scored
  on temporal questions; a history cue keeps standing facts that have out-of-window history.
- **F1.** Closed regression threads reach `<Regression>`; a promise kept or broken in that timeline is remembered.
- **Phase 64 compatibility:** a conditional-address line under v21 is byte-identical to v20's; v21's
  limit-then-slice selects what v20 selects (`test_v21_selects_conditional_address_rows_as_v20_does`).

### S11. UI-only changes, on by default

`memorymap.py` (in `test_tier2_quotes_kw_gone_overuse_map.py`): the memory map's told chains link paraphrased relays
and fork branches into their own paths; events carry `when_happened` and knowledge marks when present; the graph
leaves out excluded groups and places. No packet reads it.

## Out of scope

- **PHASE-66:** `clean-v4` (`packet.clean_text_v4` exists and nothing calls it), `extract-v21` and its typed ontology,
  migration `0041`, the read side of the ontology. Selectable or merged on the branch; specified and measured there.
- **PHASE-67:** extraction right after a reply (the plugin's background sync is merged; the sidecar's handling and its
  switch are not, at `361130c`), the Continue recall query, repair anchoring on `host_logical_id`, branch inheritance,
  per-turn persona, status windows bound to a card id.
- **Hard POV isolation** (`character_pov`): not authorized (`AGENTS.md §2`). Every `packet-v21` gate and the note's
  check are soft (instructions and fences), as ADR 0034 is.
- **Making `packet-v21` the default**: after the replay below and the owner's decision.
- **Live measurement and paid calls**: none were made (the owner's no-spend rule since 2026-10-25).

## Owner decisions

From the plan approved before the run (its section 0; numbered as there): 1 Tier 1 bug fixes under the existing
policies, recall and packet changes behind `packet-v21`, Tier 3 as a carry-on later; 2 identity (directed ambiguity,
`secondkey` out of aliases, composite and bilingual persona names with splittable derived names); 3 carry and
regression; 4 trimming (pre-flight, droppable keys, step a multiple of the window); 5 secret gates, the strict-mode
feeling, the note's cross-language check; 6 the quote route, rest and gone; 7 `<Cast>`, feeling, the persona; 12 the
note's language (the chat's by default, English on request with a check by meaning). Decisions 8–11 are PHASE-66 and
PHASE-67's.

During the run, 2026-11-25:
1. **Canon reads carried forward** (on B7): an earlier `plain` read of a persona or card text without name macros
   keeps serving; a deploy queues no canon job for them.
2. **Status-window keys do not move**: existing pins, watches and stored state keep matching; a prefix only when one
   reply holds two or more characters' windows; a bare pin or watch matches by last part; a place is never an entity.
3. **Three paid-work items after a deploy are accepted as they are** (the list under "What a deploy does"); nothing is
   built to avoid them.
4. **Workers run wide**: the coordinator's cap of two workers at a time was lifted (a run-level decision; no effect on
   the code).

## Acceptance criteria

1. **Every generation key is unchanged.** Met: the 1,120-key grid (7 compilers × 2 caps × 2 chunk caps × JSON mode ×
   extra body × no-temperature, 5 kinds) is identical to Phase 64's `cdf2c9a` at `dd267a0`, `2304342`, `47a020a` and
   on the output-trigger branch's base `7d0ce70` (the m-phase64-base and w3-output-trigger reports). Not re-run on
   `361130c`, whose one commit after `7d0ce70` touches only `retrieval.asked_keys`.
2. **`packet-v20` and older compile as before, outside the listed bug fixes.** Met by differential checks: against
   `aa331c1`, `compile_lines` over 3,000 random inputs × 21 policies and the cast, gone, appearances, settled, told,
   moded and pin readers over 600 random views × v19/v20 × strict: no difference; against `dd267a0`, the same with
   `address_condition` rows and an excluded entity: differences only in the scene cast without the excluded entity
   (744 of 2,400 checks, each asserted to differ by that entity alone) and in `asked_keys`, which `361130c` put back
   behind `packet-v21`. The Tier 1 read-side fixes are not covered by those differentials: they change gathering by
   design (the list below).
3. **The full sidecar suite passes on the final code.** **Not yet met.** Runs on the fast test database
   (`NMOS_TEST_REQUIRE_DB=1`), each including PHASE-66 tests merged by then: `dd267a0` 3,358 passed, 0 failed;
   `2304342` 3,394 passed, 1 failed (`test_hidden_ledger.py::test_narrator_hidden_rows_never_count_as_offered_memory[True]`,
   intermittent: 0 failures in 5 file runs and 40 single runs since); `7d0ce70` 3,450 passed, 1 failed
   (`test_state_history.py::test_asked_keys_words_and_boundaries`, real, fixed in `361130c`, after which 557 state,
   replay and audit tests passed). No full run on `361130c`.
4. **The plugin's tests, typecheck and build pass.** Met at the merge of the plugin branches (`9ae8c2c`): 506 tests
   (the coordinator's run). No plugin source changed after it up to `361130c`. `dist/` carries build `c228ef49152e`.
5. **Every fix is pinned by a test that fails without it.** Met per area as the workers report (S2: 23 of 24 fail on
   the base; S4: 15 of 16; the canon carry-forward: 7 of 8; S6: the reveal tests fail on the old `reveals.py`).
6. **The recall-only part is replayed (AGENTS §7 item 6).** **Not yet met.** To run: `audit.replay` of an earlier
   gate's databases, every probe, `packet-v20` (and `packet-v19`, the default) beside `packet-v21`, three replays each
   with the majority deciding; any miss fixed before a live call. Then one reduced live run of the sets the change is
   for. This gates making `packet-v21` the default, not its existence.
7. **The extraction-side part is gated (AGENTS §7 item 6).** **Not yet met, and not planned under the no-spend rule.**
   S1 changes the worker's order (`claim`) and its post-processing, which §7 item 6 puts under the full live gate.
   No key changed, so no turn is re-extracted; the gate would measure the rows written from now on.
8. **The replay drift of the Tier 1 fixes is listed.** Met (below).
9. **Docs reflect the change** (`AGENTS.md §12`). This document, ADRs 0092–0095 and the amendments, `ARCHITECTURE.md`
   D94–D97, `docs/KNOWN-ISSUES.md` K52–K58, `docs/HOST-FACTS.md`.

## What a deploy of this branch does

Nothing below has happened: production runs Phase 64's image (`exp-phase64-cdf2c9a`).

**Without any switch:**
- Every Tier 1 sidecar fix (S1–S5), the reveal-check rules (S6), the scene cast without excluded entities, the memory
  map (S11).
- **Recorded requests that can replay differently** (ADR 0027 "Consequences"): under any policy, a request whose
  gathering read a valueless or near-named secret, a symmetric-relationship word, a claim keyed by speaker spelling, a
  carried row (now a secret), an excluded entity in the scene cast, a canon block with name macros (B6), a status key
  the message asked about (G1), a clock key with a prefix or a new category (G2), a scene summary held at `LEAK_NEAR`
  or offered in part (C3, G4), or a chat whose grouping `resolve-v6` changes. Extraction-side changes (S1) do not change
  replays; they change rows written from now on.
- **The author's note** writes its model parts in the chat's language by default; makes a chronicle from threads and
  NOW facts before the first scene summary (one model call where there was none, on the owner's request only); caps
  open threads.
- **Status windows** read in more shapes; a reply with two or more characters' windows sharing a key writes prefixed
  keys from then on (a value told under a new key has no link to the bare key before it); a window the old rules
  misread reads its value right, which shows once as a change on that turn (the rules version is unchanged).
- **Startup refuses `NMOS_EMBED_MAX_CHUNKS` above 64** (production uses 52).
- **The sidecar's `TrimRequest` default** is 16 recent turns (only a request that sends none uses it).
- **The plugin** changes (S7), including the trim default 20 → 16 for a chat that never saved its own value. Its build
  changes (`dist/` says `c228ef49152e`), so the owner re-imports the plugin from the sidecar and reloads the page (H13).
  The canon manifest id changes for lorebook entries with a `secondkey`; that is metadata only and queues no canon read
  (`canonfacts` keys on `revision_hash`).

**Opt-in:** `NMOS_PACKET_POLICY=packet-v21`; the note language `en` (with the check by meaning); the panel's
embedding chunks per message (a change re-embeds every chat locally); `vectors.CHUNK_OVERLAP` exists in code only and
no projection uses it.

**Paid work after a deploy, and when** (owner decision 3 accepts the first three):
1. **Summaries of chats with a carried open secret** (F2): every scene and story summary written before, in a chat
   whose `continue` link carries a row still kept from someone, becomes unlisted, is held from packets and queued
   again by `summaries.schedule_stale` after that chat's next extraction or reveal job: one summarize call each. Count:
   over chats with at least one open carried secret, scene summaries written plus one story. Not counted on
   production.
2. **Reveal checks on "Extract all history"** (S6): the first press in a chat queues a check for each turn served by
   an earlier generation's extraction that has no check of it (turns still served by v16/v18/v19 rows after the switch
   to v20): one paid call each. Not at startup. Not counted.
3. **A new chat of an existing bot and persona** pays once for its persona and card texts without name macros (one
   call per text part), where Phase 64's image copied them from another chat's `plain` read. Later chats with the same
   names copy it (Phase 57).
4. **Canon reads already made:** none are read again (owner decision 1). A canon version change still reads again
   under the names, as before.
5. **The note's check by model** (with `en`, secrets left out and no embedder configured): one call per model-written
   part, on request.

**Stored state:** PHASE-65 adds no migration and rewrites no row. A deploy of the branch also applies PHASE-66's
`0041_extract_v21_ontology.sql` (nullable columns; `extract-v21` stays unselected). Entity ids change with
`resolve-v6`; they are not stored (pins and exclusions are kept by name). Status keys: as above.

**Also on the branch, not this phase:** PHASE-66's migration and selectable `extract-v21`; PHASE-67's plugin
background sync about 20 s after a reply (`trigger: "output"`, which the sidecar at `361130c` ignores, so the sync
only records the provisional reply; a request of that chat may wait up to 1 s for a running sync) and its Continue
query.

**Rollback: not rehearsed.** What is known from the code: PHASE-65 adds no column; status keys were already free
text; a carry link's snapshot keeps its keys (its alias rows now include owner links and the regressors' aliases),
and an archive's manifest gains two lists. Whether
Phase 64's image reads a database this branch wrote was not checked; it is to be rehearsed on a copy, as every deploy
since Phase 60 was. The plugin goes back by re-importing the earlier build. A database `0041` reached keeps it.

## Known limits and leftovers

Checked against the code at `361130c`; each is in `docs/KNOWN-ISSUES.md` where a user can meet it.
- `held_keys`: `divergence` takes it, `notes.make` and `api.py` do not pass it (a TODO in `api.py`), so the
  "diverged from the setting" part still reads every lorebook entry (B8).
- Stored rows keep a stray `value` on value-less predicates (D4), so a new value-less negative does not match an old
  valued positive in `facts.version_key`.
- Carried secrets are not listed to the extractor as OPEN SECRETS; only an owner repair ends one (K53).
- The C5 residual: a turn with two same-head valued secrets, one dropped by a re-extraction, still ends the survivor at
  a score of 0.0 (ADR 0033 amendment 2 pins it).
- Identity: 크리스티나 / Christina and 에단 / Ethan still do not match; vowel-folded keys can over-match for the persona;
  a nickname two characters share, written reversed, now merges them (K52).
- The reverse title lookup of `packet-v21` reads titles from the persona only; only supportive summaries yield; a
  conditional-address label in a secret's head is compared as part of the object name (K54); the plugin's 10-minute
  packet cache can still serve a non-empty packet after an extraction finished or an edit outside the panel.
- `claim`'s story-order barrier costs about 110 ms per claim at 25,000 active extract jobs (was about 50 ms; no
  index, which would need a migration).
- `tools/replay_sequence.py` builds `recent` itself without collapsing rerolls, so a `packet-v21` sequence replay rests
  differently from the live request (`audit.replay` does not).
- Claim `because` clauses are not secret-gated under `packet-v21` (claims render through `claim_entry`).
- A repair of a carried row is tied to its link id and orphans on relink; regression aliases are stored but only
  `continue` rows feed resolution; a persona with two or more nicknames in the target can read as ambiguous.
- A fact repair on a carried fact: `repairs.match_fact` matches it (pure test); an end-to-end API repair on a carried
  fact is not tested (being looked at with PHASE-66's repairs).
- Being fixed on the branch after `361130c` (review findings of the Phase 64 base merge): a complete `plain` canon read
  beside a partial names read loses the unread parts' facts (reachable only from a build never deployed); the address
  label in a secret's head; `": "` inside an address `when` cutting the head.

## Plan and build

Where the build differs from the plan (the code is the authority):
- The plan numbered Tier 2 as PHASE-63 and Tier 3 as PHASE-64 with `extract-v20` / migration `0040`; those were taken,
  so this is PHASE-65 and Tier 3 is PHASE-66 with `extract-v21` / `0041`.
- B7: built, then narrowed by the owner's decision 1 (earlier `plain` reads carried forward).
- B2: an entry naming unrelated characters (a pair or group entry) still joins nothing.
- B4: derived names are links in the resolution, not `node()` folds, as planned; the persona example's shape only is
  recorded here.
- G2 (LATER markers): narrower than the brief: bare 이미 / 당장 / 방금 / already / just / today are not markers.
- E1: a speaking verb or a quoted phrase asks only beside a question or recall cue outside the quotes (the brief's
  examples contradicted "a speech cue still triggers").
- E6: `gone.is_gone_vital` is a thin wrapper; no `vital_status` predicate exists in PHASE-65.
- `asked_keys`: first merged as a bug fix for every policy, then put behind `packet-v21` (`361130c`) because PHASE-39 Q3b
  pins the earlier behavior for sim bots.
- Status-window shapes came in Tier 2 (the plan's decision 11e put multi-character and HTML windows in Tier 4); the
  key rule follows the owner's decision 2, not the first build (which prefixed every leading name and read
  `[교실 | …]` as `교실.날짜`).
- E8: the 100-character chunk overlap is a function argument, not wired into any projection.
- F3: `MAX_ROWS` raised to 5,000; no ordering of rows by importance when the cap is reached.
- F4: no self-contained snapshot in a single-chat export; the manifest lists what is left out.
- The author's note language follows the plan (the chat's language by default); it is not opt-in.
- G6: the 10-minute cache's invalidation is only partly done (60 s for an empty packet, dropped after a reply).

## Open

1. **Rows written under unchanged keys.** The extraction worker's post-processing (S1), the reveal check's rules (S6)
   and what `summaries.content` sends the summarizer (S4) changed without a new extractor, reveal or summarizer
   version, so rows of one generation written before and after a deploy differ. `AGENTS.md §4` and D20 ask a prompt,
   registry, normalizer, chunker, model or endpoint change for a new generation; these are code changes around the
   prompt, and a version change would re-extract or re-summarize at the owner's cost. Not decided by the owner.
2. The replay of criterion 6 and the decision on `packet-v21` as the default.
3. Whether `held_keys` is wired into the note (it needs `canon.held` read beside the manifest).
