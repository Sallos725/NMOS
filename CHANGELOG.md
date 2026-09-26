# Changelog

Each release's "Known limitations" describe that release. The current list, with what was resolved
later, is `docs/KNOWN-ISSUES.md`.

## Unreleased

- **Sidecar and worker always get the same settings** (audit A-03). The development `docker-compose.yml`
  passed `NMOS_LLM_JSON_MODE` to the worker only. Both processes build the extraction generation from their
  settings, so with `NMOS_LLM_JSON_MODE=0` (and no value saved in the panel) the worker never picked up the
  sidecar's jobs and extraction stayed pending. Both compose files now give the two services one shared
  environment, and `NMOS_EXTRACT_HINTS` (documented, but never passed to the containers) is included. The
  worker also logs a warning when queued jobs of the active generation match none of its handlers. A test
  checks that every documented variable reaches both services.
- **Docs follow the code again** (audit A-07). The README lists every plugin argument (`route`, `language`,
  `hud` were missing) and no longer calls `extract-v10` unreleased. K1's 10,000-message margin is stated
  for what was measured: chats with no facts or vectors; extraction and embeddings add to it. CI now fails
  when a summary's host-fact, decision, known-issue, ADR or phase range falls behind.

## 0.1.0-beta.20

Three fixes from the 2026-09-26 audit (`docs/audits/NMOS-AUDIT-2026-09-26.md`, review
`docs/audits/NMOS-AUDIT-2026-09-26-REVIEW.md`). No schema, generation or hash change: nothing is
re-extracted or re-embedded.

- **A broken emoji no longer stops a chat's sync** (audit A-01, ADR 0029, sidecar). A message holding half
  of an emoji (a lone UTF-16 surrogate, e.g. cut by a script) made every sync of that chat fail with HTTP
  500, so the chat went on without memory. A persona, chat or character name with one failed every sync
  the same way. The sidecar now checks the message as sent and stores U+FFFD in place of the broken half.
  The same applies to names, the recall query, extraction replies and stored JSON. The plugin is unchanged.

- **A reply quoting the memory tag no longer turns memory off** (audit A-02, plugin). The plugin took any
  message containing `<NarrativeMemory version="0" source="nmos">` for its own injected packet and
  skipped the request as a host retry (H2). Once a reply (or your own message) quoted that tag, the chat
  silently got no sync and no memory until the message left the prompt. Only a system message now counts.
- **One bad job no longer stops the worker** (audit A-04, worker). An error other than the expected
  provider, database and validation errors (for example a provider reply with `"message": null`) ended
  the worker thread while the process kept running, so extraction and embedding stopped with jobs left
  pending. Such an error now fails that job (retried with backoff, then `dead`) and the worker goes on;
  malformed chat replies are reported as provider errors.

Pull the new sidecar image (sidecar and worker) and restart. Replace the plugin file and reload PocketRisu.
Each fix works on its own: an older plugin with this sidecar gets the A-01 and A-04 fixes.

### Known limitations

- A message whose text holds half an emoji is stored with U+FFFD in its place (ADR 0029); recall and the
  Inspector show that character. A host message id holding one is refused (HTTP 422); it has not been seen.
- A bot whose Lua `request` trigger rewrites the injected system message into another role can get the
  memory twice when the host retries a failed request (H2, H3).
- Otherwise unchanged from 0.1.0-beta.19; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.19

Phase 9 — Accountable Packets (ADR 0027, D39), plus two owner-reported fixes to what the packet keeps:
standing facts first (ADR 0026, D37) and speech level and forms of address (ADR 0028, D38). Schema:
migration 0020 (applied at startup). New extractor generation `extract-v10`. The plugin code is unchanged
apart from its version.

- **Settled relationships stay in the packet in crowded scenes** (ADR 0026). When a message names
  several characters, every fact about them scored the same, and a fact's list of who knows it decided
  the order, so trivia ("엘피 knows: 계란 껍질 …") took the few slots a 600-token packet has. A character's
  agreement to speak 반말 ranked 23rd and was forgotten. Now, among facts of equal mention, how two
  characters stand (`relationship`, `feels_toward`) comes first, then major events, and standing facts
  get the budget before promise threads. A name in a fact's "known by" list no longer ranks it.
- **Speech level and forms of address are remembered** (ADR 0028). New extractor generation `extract-v10`
  with the fact `addresses`: how one character speaks to and calls another, one per direction, e.g.
  "라디아 addresses {{user}}: 반말, '유우마'라고 부름". It is recorded when the story settles it (an
  agreement, a requested form of address, a decided change back), not when a reply merely slips into
  another speech level, and a newer one replaces the older. It ranks with relationships. On upgrade each
  chat's recent turns are re-extracted once at the provider's cost; run "Extract all history" in the
  Inspector for older turns.
- **See how much memory fit.** Inspector → conversation → Retrievals shows facts as kept/offered.
  If most facts do not fit, raise **기억 예산(토큰) / Memory budget (tokens)** in the panel (and lower the host's max
  context by the same amount).

- **Raw words get room again.** On real chats the facts filled the whole memory budget, and an excerpt
  (a password, the words of a promise, a line of dialogue) reached the model in 7 of 168 requests. The
  new packet compiler (`packet-v1`) keeps room for the best excerpt, shortening it to its best sentence
  when needed, and caps status-window state. In an answer probe with a real response model, questions whose
  answer was only in a message's words were answered in 6 of 6 runs with `packet-v1` when recall found
  the message, and in none with the earlier compiler, which never placed it
  (`docs/perf/phase9-packets.md`). `NMOS_PACKET_POLICY=packet-v0` restores the earlier compiler.
- **Every line of the packet is accounted for.** Each request records every line it offered: the fact,
  claim, promise, excerpt or state value and the assertion or message it came from, its cost, and whether
  it went in or why not. The Inspector shows this as **Last packet**, and the retrievals table shows what
  each packet held.
- **What the reply used.** Once the reply to a request is in the chat, the Inspector shows which placed
  lines the reply reused, and flags a hidden fact the reply repeated (a possible leak). This is a report
  only.
- **Replay.** A recorded request can be compiled again exactly as it was, as of its own time, or with
  another packet compiler: `GET /v1/trace/{id}/replay`, and `tools/replay_packets.py` for an offline
  comparison over many requests (read-only).
- **Fix: your own message is no longer recalled as memory.** A short message (under 16 characters) as
  the first of a chat was not recognized as already in the prompt and came back as an excerpt of itself.
  The latest message is now always treated as in the prompt.

**Upgrading.** Pull the new sidecar image and restart it. Migration 0020 is applied at startup; it adds
nullable columns and needs no backfill. With an LLM configured, `extract-v10` becomes active, and each
chat's latest `NMOS_EXTRACT_BACKFILL` turns (default 100) are re-extracted once at the provider's cost.
Older turns keep their earlier facts until **Extract all history**. Replacing the plugin file is optional
(its code is unchanged). If you replace it, reload PocketRisu.

### Known limitations

- A speech level or form of address can still be missed or cut (K25), and turns before `extract-v10`
  have none until "Extract all history".
- Traces recorded before this release cannot be replayed or audited. Real-chat comparisons of packet
  policies need traces recorded from now on.
- The packet's token estimate still over-counts Korean, so part of the reserve goes unused (K26).
- Echo is a surface measure: a secret the reply rightly keeps is used without being echoed.
- Otherwise unchanged from 0.1.0-beta.18; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.18

Plugin only: the Status tab shows the memory the last request injected. No schema change; the sidecar
is unchanged apart from its version.

- **See what memory went in.** The Status tab's "Last request" card has **Show the injected memory**,
  which opens the exact text the last request carried. The progress display only gave its length. The
  text stays in the plugin's memory until the page reloads; nothing new is stored. A reroll served from
  the plugin's cache now updates the card too.

Replace the plugin file and reload PocketRisu. Updating the sidecar image is optional.

### Known limitations

- Only the last request's memory is shown, and only until the page reloads. Earlier requests keep only
  counts (Inspector → conversation → Retrievals).
- Otherwise unchanged from 0.1.0-beta.17; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.17

Salience by what an event changes, names revealed later, and owner links between names (ADRs 0024,
0025, D35, D36). Schema: migration 0019 (applied at startup). New extractor generation `extract-v9`.

- **Important events are judged by what they change** (ADR 0024). The extractor labeled turning points
  told only in words `minor`: a change from formal to informal speech, a new form of address, a
  relationship someone allowed, an admission of responsibility; and an incident everyone had to deal with
  (a measuring device bursting) as well. A minor event comes back only when you ask about it, not when
  you name the people involved. `extract-v9` names these categories; routine business (meals, chores,
  travel) stays minor.
- **Someone shown without a name joins their name later** (ADR 0024). The extractor writes such a
  character as a `?` description (e.g. `?검은 망토의 남자`), lists them to later turns, and records the
  name when a turn reveals it. Until then the `?` in the packet tells the response model the identity is
  unknown.
- **Join two names by hand** (ADR 0025). On an entity's page in the Inspector tab, "Same as another
  entity" joins it with another entity of the same type; "Undo" takes it back. Joins survive "Rebuild
  memory" and need no re-extraction.
- **Entity ids change once** (`resolve-v4`); Inspector links saved before the upgrade no longer open.
- Switching to `extract-v9` re-extracts each chat's recent window (`NMOS_EXTRACT_BACKFILL` turns). Older
  turns keep their `extract-v8` labels and names until "Extract all history".

Upgrade both parts (migration 0019 is applied at startup), then replace the plugin file and reload
PocketRisu.

### Known limitations

- An admission is still often recorded as the past act it tells of and labeled minor (2 of 3 runs
  major on the owner's chat). On `gemma4:31b` short dialogue scenes sometimes yield no event at all, so
  no label (`docs/perf/extract-v9.md`).
- A name the model links to the wrong listed description stays linked until its turn is edited or
  deleted; there is no owner split. Names written by `extract-v8` have no `?` and are joined only by
  hand.
- More major events means a character with many of them fills the 3-event cap with major ones.
- Each extraction prompt is about 350 tokens (≈19 %) longer.
- Otherwise unchanged from 0.1.0-beta.16; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.16

Bug fix: a named persona is the persona (ADR 0023, D34). Schema: migration 0018 (applied at startup). Upgrade both parts, then replace the plugin file and
reload PocketRisu.

- **A named persona is the persona** (ADR 0023). The extractor wrote your persona both as `{{user}}`
  and by its name (e.g. 유우마), and NMOS kept them as two characters: two current locations, split
  promises, and every fact naming 유우마 counted as mentioned in every message you narrate by name.
  The plugin now reads the persona's name from PocketRisu (the chat's bound persona, else the selected
  one) and sends it with each sync; both spellings are one entity, the persona's names never count as a
  mention, and KNOWN ENTITIES leaves it out. Facts already extracted join up at the next read, with no
  re-extraction.
- **A second permission dialog at load.** PocketRisu asks *"Plugin nmos_memory is requesting to access
  the full database, which may expose sensitive information."* NMOS reads only persona names with it.
  Answering No leaves the behavior as before (reset: Settings → Plugin → NMOS row menu → **Reset
  permission responses**).
- **Entity ids change once** (`resolve-v3`); Inspector character links saved before the upgrade no
  longer open.

### Known limitations

- A chat's persona joins up at its first sync with the new plugin. Without the database permission
  (answered No, or an older plugin) nothing changes from 0.1.0-beta.15.
- NMOS follows the persona PocketRisu uses now. A different persona bound to the chat later takes over
  the persona role, and facts written under the old name become an ordinary character again.
- A persona name that is also another character's name merges the two (K8).
- The extraction prompt still allows either spelling (`{{user}}` or the name); both resolve to one
  person. Asking the model for one spelling would be a new extractor generation, deferred.
- Otherwise unchanged from 0.1.0-beta.15; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.15

Phase 8: typed event participants (`docs/phases/PHASE-8.md`, ADR 0021, D33), plus Google Vertex AI
keys for extraction (ADR 0022) and an Inspector status-window example. Schema: migration 0017 (applied
at startup). New sidecar dependency: `google-auth`. Upgrade both parts: `docker compose pull && docker
compose up -d`, then replace the plugin file and reload PocketRisu. The plugin's request path is
unchanged; its settings panel gains the Vertex AI preset.

**One-time cost after upgrading.**
- **LLM extraction:** the prompt is `extract-v8`, a new generation. With an LLM configured, each chat
  re-extracts its latest `NMOS_EXTRACT_BACKFILL` turns (default 100) once. Older turns keep their
  `extract-v7` facts, without participants, until **Extract all history** on that chat (ADR 0014). The
  prompt grows by ≈161 tokens per call (+9.7 % on the measured control scenes,
  `docs/perf/phase8-extraction.md`).
- **Entity ids change once** (`resolve-v2`). Inspector character links saved before the upgrade no
  longer open; the entities themselves and the KNOWN ENTITIES hints are unchanged.

- **The person an event happened to brings it back** (ADR 0021). Extraction lists the other characters
  or groups an `event`, `goal`, `knows` or `destroyed` fact involves (`with`). A participant named in
  your message counts like the fact's subject, for facts and character claims: `Hana event: betrayed
  Kaito` comes back when you address Kaito. The persona never counts, and being there is never read as
  knowing (`known_by` / `hidden_from` are unchanged). Real-model check (`deepseek-v4.1-flash`, 3 runs
  per scene): participants 3/3 in all ten scenes, none in 12 control runs, and the owner-reported
  "present but not told" case never put the person in `known_by`. Fact reads at 10,000 messages take
  ≈5 ms longer.
- **Inspector.** The facts table has a "With" column (a chip marks groups). A character's page gains
  "Takes part in": facts where they are a participant but not the subject or object. A character who is
  only ever a participant has a page too.
- **Inspector state example.** When nothing has been parsed yet, Current state shows a sample status
  window matching `config/parsers.example.json`'s rules, so a first-time user sees the expected format.
  The guide and README show the same example.
- **Google Vertex AI for fact extraction** (ADR 0022). The LLM API key field also takes a Google
  service-account JSON key: the sidecar exchanges it for access tokens and renews them every hour. A new
  **Google Vertex AI** provider preset fills the endpoint's project from the pasted key. LLM only; a JSON
  key for embeddings is rejected. Checked with a mocked token endpoint, not yet against real Vertex.

### Known limitations

- Older turns have no participants until **Extract all history**; they recall through their subject and
  object only.
- Participants depend on the extraction model (K22). On one model they agreed with a manual review in
  83 of 87 assertions: one extra person on a fall into a river, three missed (two `knows`, one goal).
- A relationship change can leave the earlier relationship or feeling current (K24; 2 of 9 runs in the
  Phase 8 relationship report).
- The Phase 7 minor-event scene "chores" passed 1 of 3 runs with `extract-v8`, because two runs
  extracted no event at all. Ten more runs gave `extract-v7` 3/10 and `extract-v8` 4/10, so this is not
  a regression; the owner accepted it (2026-09-24). No minor scene was labeled major.
- Vertex AI is untested against the real service (JSON mode and model listing unverified).
- Otherwise unchanged from 0.1.0-beta.14; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.14

Phase 7: promise threads and event salience (`docs/phases/PHASE-7.md`, ADRs 0019–0020, D32). Schema:
migration 0016 (applied at startup). Upgrade both parts: `docker compose pull && docker compose up -d`,
then replace the plugin file and reload PocketRisu. The plugin's code is unchanged apart from its version
number; the Inspector changes below come from the sidecar.

**One-time cost after upgrading.**
- **LLM extraction:** the prompt is `extract-v7`, a new generation. With an LLM configured, each chat
  re-extracts its latest `NMOS_EXTRACT_BACKFILL` turns (default 100) once. Older turns keep their
  `extract-v6` facts until **Extract all history** on that chat (ADR 0014). The prompt grows by
  ≈239 tokens per call (+16.8 % on the measured control scenes), plus one line per open promise listed
  (`docs/perf/phase7-extraction.md`).
- **Real-model check** (`deepseek-v4.1-flash`, 3 runs per scene): promises opened, kept, broken and
  released 3/3 in every scene; no false closing in 12 control runs; no thread from a reported promise;
  major events 3/3, minor events 2/3 to 3/3; the Phase 5 and 6 bars still hold.
- **Fact read:** +4 ms p50 at 10,000 messages (+10 to +15 ms when four characters hold 500 promises).

- **Events no longer take every fact slot.** At most `NMOS_EVENTS_LIMIT` (default 3; `events_limit` in
  `PUT /v1/config`) of a packet's facts are `event` facts, so a main character's newest events leave
  room for older facts about them. Applies to existing facts at once.
- **Promises are remembered until kept or broken** (ADR 0019). A promise a character makes, in
  dialogue or narration, is an open thread:
  `<Thread kind="promise" by="하나" to="{{user}}" turn="10">…</Thread>`, in a `<Threads>` section before
  the facts, whenever its maker or recipient comes up (at most `NMOS_THREADS_LIMIT`, default 3). Before,
  a spoken promise was only a claim, and half the time labeled hypothetical and never shown. A promise
  the story breaks, withdraws or releases leaves the packet. Applies to existing facts at once.
- **Extraction `extract-v7`.** A promise that was made is labeled actual; extraction is shown the
  chat's open promises (OPEN PROMISES, when the prompt names their maker or recipient) and records
  `fulfilled` when one is kept, or a negative `promised` when it is broken, withdrawn or released. Each
  `event` gets `salience` (`major` / `minor`). New generation: each chat re-extracts its latest
  `NMOS_EXTRACT_BACKFILL` turns once; older turns keep their `extract-v6` facts. Schema: migration 0016
  (`assertion.salience`).
- **Important events first** (ADR 0020). Among the events that fit the cap, `major` ones come before
  minor and unlabeled ones, and a `minor` event reaches the packet only when the user's message is
  about it, not merely when its subject is named. Events of older turns are unlabeled and rank as
  before.
- **Inspector.** A Promises section lists every promise with maker, recipient, turn, status (open,
  kept, broken), the assertion that closed it and the turns that restated it. Beside it is a list of
  kept or broken statements that matched no open promise. A character's view lists their promises.
  Events show their salience (`—` for older, unlabeled ones).

### Known limitations

- A promise stays open until the story keeps, breaks or releases it; a forgotten promise is never
  closed for being old, and there is no owner correction yet (K23, Track B, B7).
- A turn that keeps a promise but was extracted before `extract-v7` has no `fulfilled`: the promise
  stays open until **Extract all history** or a later turn closes it.
- A resolution worded very differently from the promise matches nothing and closes nothing (listed in
  the Inspector). In the real-model check every resolution repeated the listed text exactly.
- Salience depends on the extraction model (K22). Only one model was measured; 2 of 9 minor-scene runs
  extracted no event at all.
- Extraction prompts are ≈17 % longer than with `extract-v6`.
- Otherwise unchanged from 0.1.0-beta.13; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.13

Phase 6: item transitions and conflicts (`docs/phases/PHASE-6.md`, ADRs 0016–0017, D30), and the
retention decision O5 (ADRs 0015, 0018, D29, D31). Schema: migration 0015 (applied at startup).
Upgrade both parts: `docker compose pull && docker compose up -d`, then replace the plugin file and
reload PocketRisu. The plugin's request path is unchanged; its panel gains the Inspector changes below.

**One-time cost after upgrading.**
- **LLM extraction:** the prompt is `extract-v6`, a new generation. With an LLM configured, each chat
  re-extracts its latest `NMOS_EXTRACT_BACKFILL` turns (default 100) once. Older turns keep their
  `extract-v5` facts until **Extract all history** on that chat (ADR 0014). The prompt grows by
  ≈96 tokens per call (+7.2 % on the measured control scenes, `docs/perf/phase6-extraction.md`).
- **Worker:** the worker compacts the host observations already stored (above) in its first
  maintenance passes. Nothing is re-embedded.

- **An item is in one place** (ADR 0016, D30). An item's holder and its place are one fact history.
  "Hana puts the map on the table" ends Hana's holding, and "Kaito takes the map" ends "on the table".
  Both stated in one turn stay together. This applies to existing facts at once (K10).
- **Burned, eaten, used up** (ADR 0017). Extraction records `destroyed`, which ends the item's holder
  and place: `<Fact kind="destroyed">letter destroyed: burned</Fact>`. A damaged item is not
  destroyed (K9). In the real-model check, 4 of 4 scenes gave 3/3; damaged items and the control
  scenes gave no `destroyed` in any run.
- **Contradictions are shown, not settled.** If the story uses an item after destroying it, the fact
  is marked `disputed="true"` and names what it contradicts:
  `Hana possesses letter; but turn 5: letter destroyed: burned`. The packet Note explains the mark
  only when it is used.
- **Inspector: item timelines and conflicts.** Each item's history is listed oldest first, with what
  became of every statement (current, superseded, ended, conflicting). A conflicts table lists facts
  the story contradicts. Fact history in the API carries the same `outcome`.
- **Inspector: easier to read, and a view per character** (read-only). A conversation page opens with
  contents and counts (a conflict is highlighted) and folds each section; retrievals, commits and messages start
  folded, and conflicts come before facts. Predicates, lifecycles, commit reasons, freshness, modality
  and entity types read as words (the raw value is in the tooltip); ids are folded away. A **character**
  picker (a drop-down in the panel, links in the browser) opens one character's page: profile, what they
  hold with its timeline, facts about them, what they know and what is kept from them, and claims by or
  about them (`/inspector/c/<id>/e/<entity>`, read-only; it changes nothing in the packet). In the panel,
  Refresh keeps the scroll position and open sections, **Back** returns to the previous page where you
  were, Back and Refresh stay at the top while scrolling, and times show in the viewer's time zone
  ("3 minutes ago").
- **Edits and rerolls no longer store the whole chat again** (ADR 0018, D31). The record of each
  edit, reroll, swipe or delete used to keep every message row (≈1.1 MB at 10,000 messages). The worker
  now stores it as the rows that changed, and only when they rebuild it exactly. At 10,000 messages,
  20 such actions went from 23.3 MB to 1.1 MB. Existing databases are compacted too.
- **Old vectors are cleaned up** (ADR 0015, D29). After an embedding model or endpoint change, the
  previous vectors are deleted once the new ones cover the chat (the worker checks every 10 minutes).
  Normalized text of older normalizers is deleted at startup. Superseded LLM extractions are kept.
  Switching back to a pruned embedding model re-embeds that chat.

### Known limitations

- Older turns keep their `extract-v5` facts, and so no `destroyed`, until **Extract all history**. An
  item that older turns left with a holder keeps it until a v6 turn ends it.
- `destroyed` depends on the extraction model (K22). Only one model was measured. In 1 of 3 runs of a
  scene where a map was lost at sea, it was recorded as destroyed rather than lost; the holding ended
  either way.
- Conflicts are detected only for an item used after it was destroyed. Contradictions in other facts
  still resolve to the newer statement, and there is no owner correction yet (Track B, B7).
- Fact reads at 10,000 messages with item facts take ≈23 ms longer (`docs/perf/phase6-extraction.md`).
- Abandoned branches and their vectors and extractions are kept, by decision (K17).
- Otherwise unchanged from 0.1.0-beta.12; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.12

Phase 5: entity identity and semantic assertions (`docs/phases/PHASE-5.md`, ADRs 0012–0014), plus
cleaner text and an optional progress display. Schema: migration 0014 (applied at startup). Upgrade
both parts: `docker compose pull && docker compose up -d`, then replace the plugin file and reload
PocketRisu.

**One-time cost after upgrading.** The normalizer (`clean-v2`) and the extraction prompt
(`extract-v5`) are new generations. Every message is re-embedded once (cheap). With an LLM configured,
each chat re-extracts its latest `NMOS_EXTRACT_BACKFILL` turns (default 100) once; older turns keep
their `extract-v4` facts, marked *older generation* and *legacy* in the Inspector, until **Extract all
history** on that chat (ADR 0014). Nothing re-extracts all history by itself.

- **Negation** (ADR 0013). "Hana lost the map" or "Alice did not enter the hall" is stored as a
  negative assertion. It ends the current fact it denies (the same holder of an item, the same place)
  and shows as `negated="true"`; a negation of something else ("not at the station" while at home)
  stands as its own negative fact and leaves the current one alone.
- **Claims are not facts.** What a character says in dialogue is a claim (`asserted_by`). It never
  replaces narrated state, even when newer, and reaches the packet only as `<Claim by="…">` after the
  facts, when relevant, including claims whose truth the model marks unknown. A lie no longer
  overwrites the story.
- **Plans, conditions and dreams are labeled, not facts.** They are stored with their modality
  (`hypothetical`, `dreamed`, `unknown`) and listed in the Inspector, never injected. A missing
  modality counts as unknown, not actual.
- **One entity, several names** (ADR 0012). When the story itself gives two names for someone or
  something in one turn ("하나(Hana)"), both names become one entity: a fact under "Hana" and one under
  "하나" are versions of the same fact, and recall matches either name. Only the story links names:
  never spelling similarity, a dream, or a character's claim about someone else. A character who
  introduces their own nickname ("다들 하루라고 불러 줘") does link it. A name given to two different entities
  (a nickname two people share) stays ambiguous and links neither. The same name for an item and a
  place stays two entities; `{{user}}`, `user` and `유저` are one persona. Nothing is stored: deleting
  the turn that gave the alias splits the entity again at the next request.
- **Extraction reuses names** (ADR 0012). The extraction prompt lists up to 40 entities mentioned
  earlier in the chat (`NMOS_EXTRACT_HINTS`, `0` = off), newest first, and asks the model to reuse a
  listed name when the turn clearly means that entity. "해안 지도" then stays "해안 지도" instead of becoming
  "지도" a few turns later. Each extraction records the names it was shown. Deleting the turn a name came
  from does not invalidate extractions that used it.
- **Cost per extraction call** (`docs/perf/phase5-extraction.md`, `deepseek-v4.1-flash`, release
  candidate): prompt tokens 910 → 1,328 for the new fields and rules, 1,676 with a full 40-name hint
  list; completion tokens (mostly reasoning) ≈2,800 per call, so a call costs roughly 10–25 % more in
  total. Fewer known names send a shorter list; `NMOS_EXTRACT_HINTS=0` sends none.
- **Checked on a real model** (`deepseek-v4.1-flash`, 18 Korean test scenes × 3 runs): no plan, dream
  or claim became a fact (0 of 21), 1 of 34 plain events was labeled non-actual, losses ended the
  right holding 3/3, a different item next to a hinted one kept its own name 3/3. On PocketRisu v1.12.0
  the plugin injected `negated="true"` and `<Claim>` unchanged.
- Inspector: an entity list (names, mentions, the turn each alias came from) and ambiguous names.
  API: `GET /v1/conversations/{id}/entities`.
- The packet Note explains `negated` and `Claim` only in packets that use them.
- Inspector: facts marked *negated* or *legacy* (`extract-v4` and older), a list of claims, and a list
  of non-actual assertions.
- **A missing entity type no longer loses the fact.** A model sometimes leaves `object_type` empty on a
  name it typed elsewhere ("소우타 — relationship — 스즈키 히나타" while 히나타 is a `character` two lines up),
  and validation parked the fact as pending. When the same reply or the known-entity list gives that
  name exactly one type, the type is filled and the assertion is noted `object_type inferred`; a type
  the model gave is never replaced, and conflicting evidence fills nothing. The extraction prompt now
  also asks for both types and, more firmly, for values in the chat's language (never translated).
- **Inline images are no longer read as story** (normalizer `clean-v2`). Image plugins write markup
  into the message itself; an illustration insert (`<div><span style="…"><img src="{{raw::…}}">`)
  outgrew the old 500-character tag limit, so the whole `<img …>` tag reached embeddings, extraction
  and excerpts on every illustrated turn. `clean-v2` also drops RisuAI inlay/asset tokens
  (`{{inlay::…}}`, `{{raw::…}}`, …), markdown images and `data:` URIs, lets HTML tags span lines with
  attributes of any length, and no longer eats prose such as `HP < 30 … 3 > 2` as a tag. Upgrading
  re-embeds every revision once and folds into the same one-time re-extraction as `extract-v5`.
- **Progress display** (plugin, D28; outside Phase 5, owner decision). An optional pill at the top right
  of the chat screen shows each request's memory outcome and the open chat's background extraction and
  embedding progress. Off by default; turn it on in the panel (Settings or Status), which asks for
  PocketRisu's main-document permission. New plugin arg `hud`. Replace the plugin file and reload
  PocketRisu to get it.

### Known limitations

- Older turns keep their `extract-v4` facts (no negation, claims or name hints) until **Extract all
  history**; the upgrade does not pay for all history by itself.
- What becomes a fact depends on the extraction model's labels (K22). Only one model was measured; a
  model that marks real events as plans or dreams loses those facts (see the Inspector's "not actual"
  list). One run in the evaluation inferred a negation from a clue the narration did not state.
- A destroyed, eaten or used-up item with no statement that it is gone keeps its holder, and an item's
  holder and place are separate facts (K9, K10; transition rules are Track B, B2).
- A name the story never ties to another stays a separate entity; a character introducing themself under
  someone else's name merges the two until that turn is edited or deleted (K8).
- The extraction prompt is longer (above). Fact reads at 10,000 messages take ≈95 ms (≈70 ms before;
  `docs/perf/scale.md`).
- Otherwise unchanged from 0.1.0-beta.11; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.11

Fix release with the first step of Phase 5 (`docs/phases/PHASE-5.md`). No schema change (migrations
stay at 0013), no plugin change (its version is bumped only to keep versions in step). Upgrade the
sidecar: `docker compose pull && docker compose up -d`. Replacing the plugin file is optional.

- **Changing the LLM no longer re-extracts whole chats** (ADR 0014). A new extraction model, endpoint
  or prompt re-extracts only each chat's latest `NMOS_EXTRACT_BACKFILL` turns (default 100). Older turns
  keep the previous model's facts, marked "older generation" in the Inspector, until **Extract all
  history** on that chat. Each turn uses one model's facts, never a mix. **Rebuild memory** now discards
  the facts of every model for that chat. Embedding changes still re-embed everything, as before.
- **Fact and state reads no longer stall after an edit in a long chat.** After an edit, reroll or swipe
  (a new head commit whose statistics PostgreSQL has not gathered yet), the facts query could re-run
  its `allBefore` check once per row: about 7 s at 10,000 messages instead of about 60 ms, so that
  request went without memory. The check now runs once. The state query had the same shape and is
  fixed the same way (`docs/perf/scale.md`).
- `docs/KNOWN-ISSUES.md`: one current list of known issues with workarounds; resolved ones marked.

### Known limitations

- Changing the LLM leaves older turns on the previous model's facts until **Extract all history**; a
  better model improves them only then. A chat served by several models shows which in the Inspector.
- A fact read at 10,000 messages takes ≈70 ms (was ≈50 ms without the stalls), measured with one
  assertion per turn (`docs/perf/scale.md`).
- Otherwise unchanged from 0.1.0-beta.10; the full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.10

Long chats get memory again, and faster. Schema: migration 0013 (applied at startup). Upgrade both parts: `docker compose pull && docker
compose up -d`, then replace the plugin file and reload PocketRisu.

- **Default deadline 3 s (was 800 ms).** On PocketRisu v1.12.0 long chats need more time on the host
  side (below); with 800 ms, chats of about 5,000 messages and more never got memory. The deadline is
  a cap, so short chats are as fast as before. **제한 시간(ms) / Deadline (ms)** in the panel's
  Settings tab now accepts 200–30,000 ms and explains the trade-off, and the Status tab says what to
  change when a request ran out of time. If you set `deadline_ms` yourself, your value is kept.
- **Faster sync for long chats.** When a generation only adds messages (the usual case), the sidecar
  proves it from the request (prefix manifest hash, no repeated or already-present IDs, no new
  `allBefore` cut) and reconciles from the end of the chat instead of the whole chat. Warm append at
  10,000 messages: 715 → 156 ms (p50) on the measured machine. Edits, deletes, swipes, rerolls and
  anything unproven take the unchanged full path (ADR 0010). `NMOS_APPEND_FAST_PATH=0` turns it off.
- **Faster manifest in the plugin.** Only new or changed messages are hashed; bodies are built only
  when the sidecar asks. 10,000 messages: 175 → 17 ms after an append.
- Appends are stored as rows of their own (`worldline_append`) instead of rewriting the head commit's
  delta each time; `nmos-rebuild` and the Inspector's commit list read both.
- **An item has one current holder.** When an item changes hands (A → B → C), only C is shown as its
  holder now; A and B stay in the fact history. Applies to already extracted facts at once, with no
  re-extraction (ADR 0011).
- **Broad searches stop early.** A question whose words occur in more than 200 messages (a
  character's name alone) no longer scores most of the chat: lexical recall skips it (Inspector trace
  `too_broad`), and vectors, state and facts still answer. 10,000 messages: 852 → 45 ms.
- The Inspector no longer fails (HTTP 500) on a conversation whose extraction coverage has nothing to
  count yet, e.g. a chat with only an unanswered message; it shows "—" (#30).
- **Memory evaluation baseline.** A deterministic evaluation (synthetic cases, stub extractor) checks
  every build for stale, deleted, rerolled or other-branch memory reaching the model, and compares
  recent-context-only, lexical, hybrid and full memory (`docs/perf/eval-baseline.md`).

### Known limitations

- Measured on PocketRisu v1.12.0 (desktop Chromium): a generation in a long chat waits ≈1.5 s at
  5,000 messages, ≈2.7 s at 10,000 and ≈4.1 s at 15,000 before the reply starts, mostly because the
  host pauses after handing the plugin a copy of the whole chat. The 3 s default covers up to about
  10,000 messages; beyond that, raise the deadline (≈5,000 ms at 15,000) or those requests go without
  memory. Phones were not measured (`docs/perf/scale.md`).
- An item that is lost or destroyed without a new holder still shows its last holder, and item names
  are free text ("지도" and "해안 지도" are different items).

## 0.1.0-beta.9

Conversations can be deleted from NMOS (ADR 0009). Schema: migration 0012. Upgrade both parts:
`docker compose pull && docker compose up -d` (the sidecar applies the migration at startup), then
replace the plugin file and reload PocketRisu.

- **대화 삭제 / Delete conversation.** On a conversation page in the panel's Inspector tab (two
  clicks). It deletes everything NMOS stored for that chat, raw messages included, and cannot be
  undone. The chat in PocketRisu is not touched. If you generate in it again, NMOS records it as a new
  conversation (recent turns only; use "extract all history" for the rest). API:
  `POST /v1/conversations/{id}/delete`.
- Invariant 1 now reads: NMOS itself never destroys raw evidence; only the owner can delete a whole
  conversation. The database still refuses every other delete of raw revisions.
- Indexes on foreign-key columns keep a delete linear in chat size: 25,000 messages in about 2 s
  (`docs/perf/scale.md`).
- The plugin drops its cached memory packets after a panel action that changes data (delete, rebuild,
  settings save). A reroll right after such an action no longer reuses a packet built before it.

### Known limitations

- A delete cannot be undone, and NMOS does not notice when a chat is deleted in PocketRisu (no host
  hook, H10). Delete it in the panel yourself.
- Migration 0012 builds seven indexes at startup. On a large database the first start after the
  upgrade takes a little longer.
- Otherwise unchanged from 0.1.0-beta.8.

## 0.1.0-beta.8

Memory is extracted per **turn** (your message plus the reply) instead of per message, and each chat
gets "extract all history" and "rebuild memory" in the Inspector (ADR 0008). Schema: migration 0011.
Upgrade both parts: `docker compose pull && docker compose up -d` (the sidecar applies the migration
and writes turn data at startup), then replace the plugin file and reload PocketRisu.

- **One extraction per turn.** A turn is extracted once, after you continue from its reply, with the
  previous 3 turns as context (`NMOS_EXTRACT_TURNS`). The model sees your message and the reply
  together, and the reply decides what happened. An action the story refuses (a locked drawer, a
  blocked attack) no longer becomes a fact from your message alone. On a test chat: 41 % fewer
  calls, 37 % fewer prompt tokens (`docs/perf/turn-extraction.md`).
- **Backfill counts turns.** `NMOS_EXTRACT_BACKFILL` / the panel's "처음 연결 시 추출할 턴 수" is in
  turns (default 100 ≈ 200 messages, same number of calls). Changing it in the panel queues the
  missing turns at once; no restart.
- **Per-chat actions.** On a conversation in the panel's Inspector tab: **과거 전체 추출 / Extract all
  history** extracts and embeds the older turns the first sync skipped, and retries turns whose
  extraction failed. **기억 재구축 / Rebuild
  memory** (two clicks) discards that chat's facts (kept for audit) and extracts every turn again.
  Raw messages are never touched. API: `POST /v1/conversations/{id}/extract-history` and
  `/rebuild`.
- **Bulk deletion is visible.** The Inspector lists each commit's changes by kind and count (e.g.
  `delete ×12`). Deleting "this and following messages" already removed those facts at the next
  request; a restored range reuses its extractions without model calls.
- The Inspector's message table shows position (#) and turn; facts and `<Fact turn="…">` use the
  turn number.
- NMOS reads only chats you generate in with the plugin on. It never scans other chats by itself
  (documented, D22).

### Known limitations

- **Upgrading re-extracts facts once.** Extraction became a new generation (`extract-v4`), so with an
  LLM configured, previously covered history is extracted again (recent turns first, one call per
  turn). Until that finishes, a chat shows partial fact coverage and facts from older turns may be
  missing. With extraction switched off, the previous generation's facts stay in use.
- On a reasoning model, per-turn calls produce more completion tokens than per-message calls did
  (+19 % on the test chat; −9 % tokens overall).
- `possesses` is multi-valued: giving an item away does not end the previous holder's fact
  (unchanged, seen in both extraction modes).
- Otherwise unchanged from 0.1.0-beta.7.

## 0.1.0-beta.7

Plugin fix on top of 0.1.0-beta.6: no schema change (migrations stay at 0010), no sidecar change.
Upgrading is replacing the plugin file (or PocketRisu's plugin update) and reloading PocketRisu; the
image is rebuilt only to keep versions in step.

- **Memory works with presets that add instructions after the user's turn.** The plugin used to
  treat a request as the main chat request only if the prompt's **last** user message was the
  user's input. Presets that wrap the input (e.g. `<Current Input>`) and add instruction blocks
  after it therefore got no memory at all: no sync, no recall, and no hint why. Now the input is
  searched in every non-assistant message, whatever the preset layout, and the memory block goes in
  front of the input block instead of inside it (ADR 0001 amendment 2).
- The Inspector tab shows the "open in a browser" address only when the browser can reach the
  sidecar itself; a sidecar reached through the PocketRisu server (Docker name, LAN address behind
  HTTPS) is only reachable from that server.

### Known limitations

- Memory is injected only for content that has left the prompt; early in a chat, when everything
  is still in context, nothing is injected (by design).
- A `model`-mode auxiliary call whose prompt contains the latest user input is treated as a main
  generation and may receive a packet (ADR 0001).
- Otherwise unchanged from 0.1.0-beta.6.

## 0.1.0-beta.6

Fix release on top of 0.1.0-beta.5: no schema change (migrations stay at 0010), no change to memory
behavior. Upgrade both parts: `docker compose pull && docker compose up -d` for the sidecar (the
panel's Inspector tab needs the new `/v1/inspector` endpoints), then replace the plugin file and
reload PocketRisu.

- **The Inspector opens inside the NMOS panel.** The "Open inspector" link did nothing: PocketRisu runs
  plugins in a frame sandboxed without `allow-popups`, so the browser blocks every new tab (ARCHITECTURE
  H15). The panel now has **Status | Inspector | Settings** tabs; the Inspector tab shows the sidecar's
  own inspector pages (new `GET /v1/inspector`, `GET /v1/inspector/c/{id}`, same auth as the rest of
  the API) and follows links in place. It works over `route=server` too. `/inspector` still serves
  the pages for a browser tab.
- PocketRisu settings list one **NMOS 기억 / NMOS memory** entry instead of separate status and
  settings entries.

### Known limitations

- A beta.6 plugin against a beta.5 sidecar shows an error in the Inspector tab (HTTP 404) until the
  sidecar is updated; memory injection is unaffected.
- Otherwise unchanged from 0.1.0-beta.4 (see below).

## 0.1.0-beta.5

Packaging release on top of 0.1.0-beta.4: no schema change (migrations stay at 0010), no change to
memory behavior. Upgrading is a plain `docker compose pull` and replacing the plugin file.

- The Inspector list shows "—" instead of "partial 0 %" for a feature that was never switched on
  (e.g. fact coverage with no LLM configured).
- README and the Korean guide show the panel and the Inspector.
- The release image is now multi-arch (`linux/amd64`, `linux/arm64`); a single `docker compose pull`
  now works on Raspberry Pi / Apple Silicon / other arm64 hosts without a rebuild.
- Every tagged release also pushes `ghcr.io/sallos725/nmos-sidecar:latest`, so `docker pull
  ghcr.io/sallos725/nmos-sidecar:latest` always gets the newest published build (beta or stable).
  `beta` still tracks prereleases, and the release compose file still defaults to `beta`.

### Known limitations

- Unchanged from 0.1.0-beta.4 (see below).

## 0.1.0-beta.4

Stabilization release (issues #6–#19) and a UI review. Correctness before new features. Upgrading applies migrations 0007–0010. At startup the sidecar
backfills normalized text and re-queues fact extraction and embeddings under the new generations,
recent messages first. **Facts extracted by beta.3 are not injected until the worker has re-extracted
them with the configured LLM, and beta.3 embeddings are not searched until the worker has re-embedded
them** (both stay stored for audit). beta.3 did not record which endpoint produced a vector, so it
cannot be proven to match the configured one (#17). Until the worker catches up, recall is lexical
for the affected messages and the Inspector shows coverage as *partial*. Embedding is fast next to
extraction (a local Ollama embeds a message in tens of milliseconds). Verified by upgrading a
database written by beta.3.

- **Model/endpoint changes re-derive memory** (#6, #7). Extraction and embeddings are bound to a
  generation key: compiler, prompt, predicate registry, normalizer, endpoint, model and settings;
  credentials excluded. Changing the LLM or embedding model or endpoint re-extracts or re-embeds.
  Changing only an API key does not. A worker never runs a new model's jobs with the old model during
  its 30 s settings reload. Vectors from different endpoints or models are never compared.
- **Upgrades keep fact coverage** (#8). A new generation rebuilds the recent window first, then every
  older message the previous generation covered, in the background. Coverage per chat is shown in the
  Inspector and at `GET /v1/conversations/{id}/coverage`. Old generations stay for audit.
- **Turning a provider off stops its queued work at once** (#18). Switching LLM extraction or
  embeddings off in the settings makes their queued jobs obsolete in the same save, so a paid API is
  not called for jobs that were waiting (previously up to the worker's 30 s reload). A request already
  running finishes and is not retried. Turning it back on, or switching back to an earlier model,
  queues what is missing again (previously work made obsolete by a switch was not re-queued).
- **Settings API checks types** (#19). `PUT /v1/config` rejects values of the wrong JSON type with a
  422 instead of converting them: `"false"` is no longer read as true, `3.5` is not truncated to 3,
  and numbers are not accepted where text is expected. The settings panel already sends the right
  types. `null` still resets a value to the environment default.
- **One NMOS panel, reachable from the chat** (UI review). The ☰ menu left of the chat input now has
  **NMOS 기억 / NMOS memory**; it and the two settings entries open one full-screen panel with a
  **Status** tab (connection, features, last injection, Inspector link) and a **Settings** tab. The
  status used to be a plain host alert. The panel is opaque (the host settings page no longer shows
  through), has a Korean/English picker (Korean by default, new plugin arg `language`), and saves every
  changed section with one **Save** button: unsaved changes are listed, and closing asks first. Server
  settings from several sections are validated and saved in one request.
- **Inspector names conversations** (UI review). Conversations show as *bot name · chat name* as
  PocketRisu last reported them, with the chat id underneath (migration 0010). The plugin reads the bot
  name in the background, so it appears from the second message after an upgrade. The Inspector is
  Korean by default, with an English switch that the panel's language also selects.
- **Recall ignores reasoning blocks** (#9). Lexical search, embeddings, extraction and excerpts share
  one versioned normalized text. Words that only appear inside `<Thoughts>`/`<think>`/style blocks no
  longer produce hits, in the corpus or in the query.
- **Character knowledge: public / limited / unknown** (#10). "Not listed" now means unknown, not
  "does not know". Existing marks migrate (names → limited, empty → unknown). The extraction compiler
  is now `extract-v3`.
- **Settings save from a localhost sidecar** (#11). CORS allows `PUT`.
- **Large chats** (#12). Manifests up to 30,000 messages are accepted (was 20,000), with measurements
  for 1k/5k/10k/25k in `docs/perf/scale.md`. Lexical recall now reliably uses the trigram index:
  10k messages went from ≈0.8 s to ≈10 ms per query. Lexical recall has a time budget
  (`NMOS_LEXICAL_TIMEOUT_MS`, default 300); a query that exceeds it contributes no lexical candidates
  for that request instead of holding a database connection for seconds.
- **Long messages** (#13). Per message, the Inspector shows how much was embedded (8 × 700 chars) and
  seen by extraction (6,000 chars), and flags partial processing.
- Release workflow runs the full CI suite first and checks that tag, versions, changelog, status and
  migration list agree (#14). `docs/phases/PHASE-4.md` records the soft-knowledge subset.

### Known limitations

- Warm per-message sync cost grows linearly with chat length (full-manifest design). With the default
  800 ms deadline, memory is injected reliably up to ≈5,000 messages on the measured machine. At
  10,000+ messages requests fail open (no memory) unless `deadline_ms` is raised; see
  `docs/perf/scale.md`.
- A query whose words appear in nearly every message (a character's name alone, a phrase repeated in
  every reply) makes lexical recall score every message. With long chats this exceeds its 300 ms
  budget, so such a message gets no lexical excerpts; vectors, state and facts still apply.
- Changing the extraction model re-extracts all previously covered history with that model (cost).
- Knowledge names are free text; hard character-POV isolation is not implemented.
- Messages longer than 5,600 normalized chars are only partially embedded; extraction reads the
  first 6,000 chars of a target message.
- The Inspector shows a conversation's bot name from the second message after upgrading (the plugin
  reads it in the background). Plugin menu names switch language after a page reload.
- Tested on PocketRisu `a14c911` only. PocketRisu is a fork of RisuAI and NMOS uses the RisuAI-family
  V3 plugin API, but upstream RisuAI has not been tested.

## 0.1.0-beta.3

- Embeddings use their own first-sight backfill (`NMOS_EMBED_BACKFILL`, default 2000) instead of the
  LLM extraction limit (100), so semantic recall covers early turns of long chats. Found in a
  fresh-install walkthrough.

## 0.1.0-beta.2

- **Settings panel in the plugin** (PocketRisu → Settings → "NMOS 설정"): LLM and embedding providers
  (Ollama / OpenRouter / OpenAI / Gemini / custom), model list, connection tests, recall tuning,
  status-window rules. `.env` is optional; saving applies immediately and backfills existing chats.
- **Sim bots**: per-character state (`하나.HP`), markup/`<Thoughts>` stripped from recall,
  robust matching when scripts reshape messages, knowledge marks `known_by` / `hidden_from`.
- "NMOS 상태 / Status" menu; default sidecar URL; non-local sidecars reached through the PocketRisu
  server (works for phones/Remote Access and Docker service names).
- Auth token optional (off by default). Worker prunes old jobs/traces; embedding contention fixed.

## 0.1.0-beta.1

First public beta. Tested against PocketRisu `a14c911` (v1.12.0) with real UI runs.

- **Memory packet** injected before each main generation, within `reserved_memory_tokens`:
  out-of-context excerpts, parsed state, and extracted facts. Aux requests (summaries, suggestions,
  translations) never get one; retries inject exactly once.
- **Faithful history**: immutable ledger follows sends, rerolls, swipes, Continue, edits, deletes,
  hide / "Cut Messages for AI", branches and imports. Nothing deleted, edited away, rerolled away or
  hidden is ever recalled.
- **Hybrid recall**: trigram (works for Korean) + optional embeddings (any OpenAI-compatible
  `/embeddings`, e.g. Ollama `qwen3-embedding`), reciprocal-rank fusion, abstention thresholds.
- **State parsers** (optional): JSON rules turn status windows into current state.
- **Fact extraction** (optional): background worker with any OpenAI-compatible chat model; closed
  predicate registry, bounded context, fact versions with history and provenance.
- **Inspector** at `/inspector`: conversations, state, facts, retrievals, commits, queue health.
- **Fail open**: sidecar down or slow (> 800 ms) → chat continues without memory.
- Deploy with `nmos-docker-compose.yml` (GHCR image `ghcr.io/sallos725/nmos-sidecar`) and import
  `nmos-pocketrisu.js`. Reload PocketRisu after installing or updating the plugin.

Known limits: PocketRisu must be opened via localhost or HTTPS; no group chats; no character-POV
knowledge isolation yet; thresholds tuned on limited data.
