# Changelog

Each release's "Known limitations" describe that release. The current list, with what was resolved
later, is `docs/KNOWN-ISSUES.md`.

## Unreleased

- **Phase 22 complete: a re-extraction that keeps what it found** (ADR 0057 and its amendment 1, ADR 0044 amendment 3, D66,
  `docs/perf/reextract-loss.md`; AGE-25). **"Extract all history" no longer extracts again** a turn that was extracted
  before an earlier turn's secret (K29): it keeps the turn's facts and asks one short model call whether a character
  found the secret out there. On the owner's M0 chat the 68 turns one press re-extracted cost 727k input and 85k output
  tokens and dropped the answer to "what does A do?"; their checks took 324k and 1.5k, discarded nothing, and the
  answer stayed. **Facts a re-extraction dropped** (the same model, extracting a turn again, did not state them again
  and the chat holds them nowhere else) are listed under "Needs attention" with **Restore**, and counted on the
  panel's chat card; Restore puts the fact back as yours at its turn, Undo takes it back. Nothing is restored on its
  own. New API: `GET /v1/conversations/{id}/dropped`, repair kind `fact_restore`. Migration 0028; a new plugin build.

- **An owner's repair survives a new extractor generation** (ADR 0044 amendment 2, `docs/perf/repair.md`). A repair now
  also stores its item's quote of the chat, and finds a re-extracted item by that quote when the new generation words
  it differently or states it at another turn. On a copy of the owner's chats re-extracted with `extract-v14`, 40 of
  68 repairs made on `extract-v13` found their item again (29 before); none whose item the new generation still quotes
  was lost. Repairs made before this change have no quote and match as before; one that matches nothing is still
  listed under "Needs attention".
- **Phase 20 complete: a name join shown before it is made** (ADR 0055, D65, `docs/perf/join-preview.md`). Joining
  two names, splitting them, or undoing either now shows first what changes in the chat's memory: which current
  fact replaces which (the story's order decides), facts that merge, a relationship, promise or thread of a character
  with themself, a secret kept from someone who holds it, repairs whose match changes, conflicts, the persona and
  canon names; "nothing changes" when nothing does. The action is made from the preview and refused (a fresh preview)
  when memory changed since. Undoing a join offers to re-extract the turns extracted while it held, off by default,
  one extraction call a turn. Also fixed: a rebuild's or re-extraction's job that the model was still answering no
  longer stores its old result. New API: `…/entity-links/preview`, `…/entity-links/{id}/remove/preview`,
  `…/entity-links/{id}/reextract`, `…/repairs/preview`, `…/repairs/{id}/remove/preview`, and `expect` on the join,
  a split and both removes. A new plugin build.
- **Phase 19 complete: `extract-v14`** (ADR 0054, D64, `docs/perf/extract-v14.md`), a new extractor generation. The
  model sees each previous turn's messages up to 1,000 characters instead of 2,000, so an extraction reads about a sixth
  fewer input tokens; on sampled turns it found more of a synthetic chat's facts (115 against 106–109 of 167). The
  prompt's examples are synthetic. A fact whose quoted evidence (12 characters or more) is not in its own turn is kept
  as pending, "evidence not in the turn", and never injected (0.2 % of `deepseek-v4.1-flash`'s facts and 2.7 % of
  `gemma4:31b`'s when the evaluation chats were extracted again). **Upgrading re-extracts** each chat's recent turns
  (`NMOS_EXTRACT_BACKFILL`, default 100) once at your provider's cost, and reads each chat's canon sources once more;
  older turns keep their facts until **Extract all history**. Known issue K41: re-extracted with `deepseek-v4.1-flash`,
  the owner's evaluation chats passed two fewer memory cases on three of four runs (`gemma4:31b` within one).
  `tools/eval_extract_sample.py` compares extractor prompts on sampled turns.
- **Phase 18 complete** (`docs/perf/lexical-recall.md` "Step 5"). Replayed on the owner's recorded requests (read-only,
  counts only), `packet-v10` with keywords placed excerpts in 10 of 34 requests that had none without vectors, and no
  secret or thread that `packet-v9` would not. Known issues K39 (a grown excerpt can carry a value the story has since
  replaced) and K40 (a keyword of two or three syllables is not found where a particle is attached to it).
- **Phase 18 step 4: `packet-v10`, excerpts that grow** (ADR 0053, D63), the new default. An excerpt starts from the
  sentence holding most of your message's keywords and adds its neighbouring sentences, after then before, up to four
  and within the length the memory budget gives it; before, it was always two sentences (about 70 characters) whatever
  the budget. On the owner's chats without vectors it answered 6 more questions needing memory, and with vectors placed
  2 forbidden phrases instead of 6. On the synthetic chat, whose facts change often, it places values the story has
  since replaced more often than `packet-v9` (17 against 12 with vectors, 12 against 5 without; none a secret), though
  far less often than growing to the whole length (29). Requests recorded before replay with `packet-v9`.
- **Phase 18 step 3: keyword lexical recall** (ADR 0052, D62). Lexical recall also looks up the message's keywords one
  by one (up to four; Korean particles and question endings taken off, names kept whole, question and stop words
  left out), so a natural question finds the message that says what it names even when the question as a whole is
  too unlike it, and without vectors. A keyword in most of the chat is ignored. An excerpt only this route found is
  left out when it repeats a secret still kept from someone (owner, 2026-09-30). Requests recorded before this version
  replay without it. The trace shows `keyword_mode`, each candidate's `keyword_score` and `keyword_withheld`.
- **Phase 17 (what NMOS's own model calls cost, and fallbacks told from failures) is complete**
  (`docs/phases/PHASE-17.md`, `docs/perf/model-usage.md`): the recorded tokens equal the provider's on a hosted model
  and on local chat and embedding models; generation latency is unchanged; archives from before carry over, their
  usage "not recorded".
- **Phase 18 step 2: recall measured by what lexical recall finds and how long excerpts are**
  (`docs/perf/lexical-recall.md`). The evaluation tool says per case whether lexical recall found anything and how long
  each excerpt was, and marks runs without vectors. Fixed in the tool: an older request's prompt window read empty once
  the chat had moved on (so answers the prompt already held counted as memory's), and a probe could not replay after
  the request's own message was deleted. Nothing changes in what a request recalls.
- **Phase 17 step 4: the progress display says how memory was served and what background work made.** "✓ Memory
  injected (… chars) · lexical only" when recall had to go without vectors (the embedding model did not answer in
  time, K34), "· reused" when a reroll reused the packet already built; neither is shown as a warning. When
  background work finishes it says what it added ("✓ facts +3 · summaries +1"), or "✓ Processing done" as before. A
  new plugin build.
- **Phase 17 step 3: what a chat's memory cost, shown.** A conversation's Inspector page has a **Model usage**
  section: per generation (fact extraction, canon reads, summaries, embeddings) the model calls NMOS made and the
  input, output and cached input tokens the provider reported, with how many calls reported them. The panel's
  "This chat" card says the chat's totals in one line. No prices. A new plugin build.
- **Phase 17 step 2: what NMOS's own model calls used** (ADR 0051, D61, migration 0027). Each extraction, canon read,
  summary and embedded chunk now keeps the tokens its model call used, exactly as the provider reported them (input,
  output, cached input and reasoning tokens, when reported), with the call's duration and model. Nothing is estimated:
  a provider that reports nothing is recorded as such. Rows from before this version show nothing. Shown in the
  Inspector and the Status tab in a later step.
- **Fixed: a reroll could reuse a packet built for another sidecar or with old canon** (Codex security review of
  Phase 16 step 3). The plugin keeps a packet for 10 minutes for the same chat state; it was reused after
  `sidecar_url`, the route, the token or the memory budget changed (the new sidecar was never asked), after a lorebook
  entry, the card, the persona or the author's note changed or the chat was bound to another persona without a new
  message, and for a prompt of the same length holding other messages. These are now part of the key (the token
  hashed), and a packet built with other canon (its manifest or what the prompt held) is not reused. A panel action (a
  delete, a repair, a settings save) now empties the cache also when its answer failed or came late, since the sidecar
  may have applied it, and a request that was fetching memory meanwhile goes without it rather than cache or inject a
  packet from before. A new plugin build; nothing changes in the sidecar.
- **Phase 16 (Stage 6, part 3: export and restore) is complete** (`docs/phases/PHASE-16.md`, `docs/perf/archive.md`):
  on copies of the owner's two measured chats an archive restored into a fresh database (migrating it one level on
  the way) held every table the same, compiled every recorded request the same, and gave the same M0 and secret-gate
  results and the same rebuild. A production-sized install exports in about 3 s (15 MB with embeddings, 2 MB without)
  and restores in about 3 s. Both Export buttons were smoke-tested on PocketRisu v1.13.0. On an iPhone, **Export everything** saved its file,
  but PocketRisu may then show its own "server has been updated" alert, which is safe to dismiss (K38).
- **Phase 16 step 4: restore** (ADR 0050 amendment 1): `python -m nmos_sidecar.archive restore FILE` (or `-` for
  stdin; `--check` to verify only), with the sidecar and worker stopped. Every file's size and hash is checked before
  anything is written; an archive from a newer NMOS, or a chat this install already holds, is refused (nothing is
  merged); an archive from an older NMOS is upgraded as the upgrade would. Ids and timestamps are kept, so recorded
  requests replay as before (with embeddings in the archive when they used vectors). Settings already set here stay.
- **Phase 16 step 3: export** (NMOS Archive, ADR 0050, D60). **Export everything** in the panel's Settings tab and
  **Export this chat** on a conversation's Inspector page save a `.nmos.zip`: every conversation's history, canon,
  your repairs and links, the recorded requests, and by default the model's extractions and summaries (embeddings when
  asked); the whole install's archive also holds the settings, never an API key or the token. The same from
  `GET /v1/archive` and `python -m nmos_sidecar.archive export`. NMOS refuses to write an archive in which it finds a
  key or the token. A new plugin build; no migration. Restoring comes in step 4.
- **Phase 16 step 2: the plugin's frame can save a file** (H21, `docs/HOST-FACTS.md`): on PocketRisu v1.13.0 a Blob
  saves from the panel (Chromium, Firefox) and `nativeFetch` carries a binary body whole on both routes.
- **Fixed (security): a narrator's name could break out of the packet's Note** (ADR 0035). With a first-person
  narrator set for a chat, the narrator's display name went into the packet's `<Note>` unescaped, so a name holding
  markup (`</Note><Fact>…`) could add elements of its own to the system-role packet. The Note's text is now escaped
  like every other line. A name without `<`, `>` or `&` gives the same packet as before, so recorded requests still
  replay. No migration, no plugin change.
- **Fixed: canon facts from a branch the host never shows** (ADR 0047 amendment 2, H20). A card or lorebook text
  with `{{#if …}}` / `{{#when …}}` blocks was read with every branch, and its facts were sent as memory even when
  the chat's variables hid them (a language or a display switch, for example). A canon fact quoted only inside such
  a block is no longer served; nothing is re-extracted. No migration, no plugin change.
- **Phase 15 (a packet that fills its budget) is complete** (`docs/phases/PHASE-15.md`, `docs/perf/packet-fill.md`):
  on the owner's two chats with both extraction models, `packet-v9` at 4,000 answered 6 more cases needing memory than
  `packet-v8` at 2,000, with 2 more forbidden phrases (one old excerpt); on 38 recorded requests it added only facts,
  claims and excerpts; retrieve latency unchanged at 10,000 messages. Fixed: after saving a budget above 8,000 the
  panel kept showing the typed value. `tools/bench_story.py` takes `BENCH_BUDGET` and `BENCH_RECALL=wide`.
- **Phase 15 step 4: memory recalled without vectors is no longer silent** (K34). On the owner's production 70 % of
  recalls went without vectors because the query's embedding took longer than 300 ms. The retrieve answer now says
  whether vectors ran (`vectors`: on, off, fallback), and the panel's Status tab says so after a request that fell
  back, with what to do. `NMOS_EMBED_TIMEOUT_MS` is documented. A new plugin build.
- **Phase 15 step 3: a packet that fills its budget** (`packet-v9`, ADR 0049, D59), the new default policy: above
  2,000 tokens the excerpt count, each excerpt's length and the fact limit grow with the memory budget, from your own
  settings (up to 4× excerpts and 2× facts at 8,000; the added fact slots only for facts kept from no one); threads,
  events, secrets, `<Private>`, `<Cast>` and `<Story>` do not. At 2,000
  and below it is `packet-v8`; recorded `packet-v8` requests replay as they were. The plugin's default budget is
  **4,000** (was 2,000): lower PocketRisu's max context by 2,000 more if you never set the budget. The panel saves up
  to 8,000 and the budget advice suggests up to 8,000; a larger stored budget still works and recalls as 8,000. A new plugin build; no migration, nothing re-extracted.
- **Phase 15 step 2: evaluations that cannot drop vectors silently** (PHASE-15 Q6): `tools/eval_rp.py --projection`
  searches a named embedding projection (its recorded endpoint only when local, else `--embed-url`), warms the
  embedder, and reports per case whether vectors ran; a run that asked for vectors and lacked them exits with status 2.
  A replay (`/v1/trace/{id}/replay`, `audit.replay`) now says `vectors`: on, off or why it fell back. The `packet-v8`
  baseline with vectors is in `docs/perf/packet-fill.md`.
- **Phase 14 (Stage 6, part 2: canon sources) is complete** (`docs/phases/PHASE-14.md`, 2026-09-29):
  - On both measured chats with their canon, M0 and the secret gate are unchanged case by case, and canon took 12 and
    66 model calls (26 on the owner's production chat), as the inventory predicted (`docs/perf/canon.md`).
  - **Only relationships are listed as conflicts with canon** (ADR 0047 amendment 1, owner decision): on real chats
    the listed identities were the same one in English and Korean, or two true descriptions. A story's identity
    supersedes canon's quietly; the owner can still lock a canon fact from its line.
  - The canon-facts query is prepared once per connection. Latency with a 200-entry lorebook read whole misses the
    +5 ms criterion; the owner accepted it (K36).
  - Fixed: the Inspector marked every canon fact "older generation".
  - Tools: `tools/eval_rp.py` and `tools/eval_secret_gate.py` take `--canon`, `tools/bench_story.py` `BENCH_CANON=N`;
    an upgrade fixture from Phase 13 `main`. No migration, no plugin change.
- **NMOS off for one chat** (ADR 0048, D58): the panel's Status tab starts with a **This chat** card that turns NMOS
  off or back on for the chat open now, and the chat input's ☰ menu has **NMOS: this chat off/on**. A chat that is
  off sends nothing to the sidecar and gets no memory; what NMOS keeps of it stays. The list is the new plugin arg
  `disabled_chats`. The panel also opens from NMOS's icon in the sidebar's ☰ menu. A new plugin build; no migration.
- **A new icon**: the 🧠 emoji is replaced by NMOS's own line icon (an N with a memory node) in Settings, the chat
  input's ☰ menu and the sidebar's ☰ menu. It takes the host's text colour. In the sidebar, which shows no name, the
  icon carries it for screen readers and as a hover tooltip. The progress display shows it before
  "Recalling memory…" only. A new plugin build.

## 0.2.0

The first milestone release (`docs/ROADMAP-1.0.md`): **Stage 4, knowledge and secrets** (Phase 10) is complete, and
`main` has since added **Stage 5, the narrative engine** (Phases 11–12), and most of **Stage 6, verification and
repair** (Phase 13 and Phase 14 steps 1–5). The owner asked for this release on 2026-09-28. On the owner's real scenes,
48 replies of Opus 5.5 and Gemini 3.1 Pro with the new memory voiced no secret to a character it is kept from, and the
holders remembered it (`docs/perf/secrets-eval.md`).

What changes, in short:
- **Secrets:** what is kept from whom, who found it out and when; a Private section; strict and first-person
  narrator modes per chat.
- **Open business and causes:** promises, goals, questions, threats and debts are open until the story ends them;
  the stated cause of a feeling or an event.
- **Relationships:** a relationship is one pair, both ways.
- **Summaries:** scenes and the story so far are summarized in `<Story>`; each scene character's state goes in
  `<Cast>`.
- **The owner repairs memory:** close or reopen a thread, retract or correct a fact, mark a secret found out, split
  two names, lock a fact; each with undo.
- **Canon:** the card, the lorebooks, the persona and the author's note become sources of each chat. Lorebook keys
  give given names; the extraction model reads canon facts, which the story supersedes.

It also has the fixes of the 2026-09-26 and 2026-09-27 audits and a new text normalizer. The generations and schema
that change are:
- extractor generations `extract-v11` to `extract-v13`;
- the text normalizer `clean-v3`;
- the default packet policy `packet-v8`;
- migrations 0021–0026.

The Phase 14 evaluation of canon facts on the measured chats (their model calls, M0, the secret gate, latency with a
large lorebook) and its real-host smoke were still to come (step 6; done after this release, see Unreleased).

- **Fixes from the 2026-09-27 audit** (`docs/proposals/ORIGINAL-VISION-TO-STABLE-2026-09-27.md`, ADR 0033
  amendment 2):
  - A reveal no longer carries over to a different secret after the secret's turn is edited (G1). A character
    who found out one plan counted as knowing whatever plan that turn was edited into. A reveal now links by turn
    only while that turn reads as it did; otherwise it must match by content, or it is shown as unrevealed.
  - "Extract all history" now recovers a reveal missed when a chat was first connected (K29, G2): it extracts
    again the turns extracted before an earlier turn's secret, oldest first. Before, it skipped them.
  - A model answer without an `assertions` list fails the job (retried, then counted failed) instead of
    counting as a turn with nothing to extract (G3; in every release since `v0.1.0-beta.1`).
- **Phase 12 (Stage 5, part 2) is complete** (`docs/phases/PHASE-12.md`, 2026-09-28):
  - M0 has 12 more owner-confirmed cases whose answers lie outside the prompt's own messages: 2 of 12 on Phase 11.
  - **Scene summaries and the story so far** (ADR 0042, migration 0023), written in the background by the extraction
    model for every 8-turn window and kept current through edits, deletes and swipes; the Inspector shows them. The
    prompt lists the secrets still kept from someone and says to leave them out; a summary that repeats one is held
    back when it is read.
  - **`packet-v8` (new default): `<Story>` and `<Cast>`** (ADR 0043). The story so far and the scene the message is
    about, in at most 30 % of the budget (none for a first-person narrator); each scene character's place, condition,
    feeling toward the persona, what they carry and, when the message names them, open goals. On the owner's chat
    (restored copy) 5 of 12 answers outside the prompt window reach the packet, 2 before. A summary written before a
    secret it should keep is held and written again (ADR 0042 amendment 2); in front of a character a secret is kept
    from, a summary that comes near it is held too (amendment 3); a reworded secret can still pass (K30).
  - **Summaries are on by default** where extraction is on (`NMOS_SUMMARIES=0` or the panel turns them off). On the
    first start every chat's due windows are summarized in the background: for the owner's chats, about 11 scene and
    2 story calls.
  - **The Inspector shows why a summary is or is not used**: the summary generation, each scene's state (current,
    held back for a secret with the secret named, not used while a character it is kept from is in the scene,
    changed and written again, queued, failed with its error), and a note when summaries are off or a chat has a
    narrator. A character's page starts with **Current state**, the lines `<Cast>` gives them and their open goals.
  - **A long append no longer leaves scenes unsummarized** (ADR 0042 amendment 4). A sync that made two or more
    windows due at once queued only the newest, and the story so far, which waits for every window, was never
    written. In play a sync adds one turn; it took a chat continued while the sidecar was down or the plugin off.
  - **`<Story>` in a long chat costs a request about 10 ms instead of 180 ms** (10,000 messages, 624 scenes). A
    request read every story the chat ever had and checked every scene against every secret; it now finds the
    current scenes and one story in one query and checks only what it would offer. The choice is the same.
  - Fixes from the review of #137 and #139: the Inspector shows the job that would replace a summary still in use
    (queued, writing, or failed with its error), such as a story behind the newest scene; and a request keeps the
    scene trigrams it read, so another request clearing the shared cache cannot drop a scene from its choice.
  - From the first cross-model review (Codex, AGENTS.md §14): after the turns of a whole window were deleted, a later
    scene summary, current now for an earlier window, was judged older than the prompt by the turns it was written
    at, so a scene the prompt no longer held could be left out. The request now uses the window it is current for,
    as before the step 7 rewrite.
- **Phase 14 (Stage 6, part 2): canon sources** (`docs/phases/PHASE-14.md`, approved 2026-09-28; steps 1–5): the card,
  the lorebooks, the persona and the author's note as sources of each chat, host evidence first. Export and restore
  are Phase 15.
  - Step 2: canon host evidence on PocketRisu v1.13.0 (`docs/HOST-FACTS.md`, H19) and a count-only inventory of the
    two measured chats' canon (`docs/perf/canon.md`).
  - Step 3 (ADR 0045, migration 0025; new plugin build): each chat's canon is kept as the host shows it, with every
    version. The Inspector lists it in a "Canon" section, with how often a request's prompt held each text. The
    plugin sends it in the background when it changes and reads the card off the request path. Canon changes no
    packet yet.
  - Step 4 (ADR 0046): a lorebook entry's keys count as names of the one character they name. So a character called by
    a given name the lorebook lists is a mention (K31). On sample 2 the given-name probes found their fact 2 of 3,
    against 0 before.
  - Step 5 (ADR 0047, migration 0026; new plugin build): **facts from canon.** The extraction model reads the card,
    the persona, the author's note, and each lorebook entry once a prompt held it, in the background, each text once
    (`NMOS_CANON_FACTS=0` or the panel's new switch turns it off). Canon facts are how things stand before turn 0: the
    story supersedes them from the turn it says something new. When the story changes who someone is or how two
    characters stand, "Needs attention" lists it with the choices: keep canon's (a **lock**, a new owner repair that
    keeps a canon fact or a correction current against later statements, with undo), keep the story's, or leave it.
    A canon fact whose text the prompt already holds is not sent again; a locked one is, when the story contradicts
    it. The plugin now recognises a card that uses `{{char}}` in the prompt, so it no longer reads the card again on
    every request.
- **Phase 13 (Stage 6, part 1): the owner repairs memory** (`docs/phases/PHASE-13.md`, approved and complete 2026-09-28).
  - Step 2: the owner confirmed NMOS's lists for the longest chat (50 of 59 open threads ended, 6 secrets found out);
    on the previous `main` every M0 packet carried a thread the owner closed (`docs/perf/repair.md`).
  - Step 3 (ADR 0044, migration 0024): the owner can close a thread with an outcome or reopen one the story closed,
    and mark a secret found out by a character or keep one the story ended by mistake, through
    `POST /v1/conversations/{id}/repairs`. A repair is owner input: it survives
    rebuilds and new extractor generations, finds its target by what it says, and is listed in the Inspector, with
    undo. A repair whose target's turn was edited matches nothing and says so.
  - Step 4: the owner can retract a fact (the version before it is current again), correct one (a new object or value,
    at its own turn or from a later one, until the story says otherwise), and split two names the story joined (K8),
    with the names that still join them when a split cannot separate them.
  - Step 5 (new plugin build): the repairs are buttons in the panel's Inspector, on the line they fix: close a thread
    with an outcome (or tick several and close them together), reopen, mark a secret found out or still kept per
    character, retract or correct a fact (its object or its value, from its own turn or a later one), undo; split
    two names on an entity's page. Each chat's page starts with
    "Needs attention": threads open for 30 turns without a restatement, ends that matched no thread, disputed
    whereabouts, repairs that match nothing now, splits still joined through another name, ambiguous names.
  - Step 6 (`docs/perf/repair.md`): with the owner's decisions made as repairs, no closed thread reaches a packet on
    either measured chat, M0 gains a case and loses none, and `<Story>` is back in every secret-gate scene. A memory
    read with many fact repairs no longer searches every assertion for each (it cost +66 ms at 10,000 messages with
    100 repairs; now +7.0 ms over Phase 12, +1.7 ms with none; accepted by the owner). A thread with no counterpart
    reads "하나: …" in the Inspector, not "하나 → ?: …". `tools/eval_secret_gate.py` takes a case's words by secret.
- **Cross-model review** (`.ai/`, AGENTS.md §14; #138): fixed after its review, the script refuses every `.env*` name
  (`.envrc` passed before) and gives the reviewer CLI only the system basics of the environment and its own login
  variables, never `NMOS_*`, `DATABASE_URL` or `PG*` (it passed the whole environment).
  - **The default memory budget is 2,000 tokens** (was 800); a value saved in the plugin stays. Lower PocketRisu's max
    context accordingly.
- **Phase 11 (Stage 5, part 1) is complete** (`docs/phases/PHASE-11.md`, 2026-09-28):
  - M0, an evaluation on a restored copy of the owner's chats (`tools/eval_rp.py`, numbers only in
    `docs/perf/m0-baseline.md`): 13 of 28 owner-confirmed cases on the Phase 10 code, 15 after step 3.
  - **A relationship has one history per pair** (ADR 0038, K24). A change the extraction records in the other
    direction ("카이토 → 유이: 연인" after "유이 → 카이토: 같은 반 친구") replaces the old one when either is symmetric
    (friends, lovers, classmates…); a directed pair ("엄마", "자녀") keeps both. Feelings and speech levels stay per
    direction.
  - **The persona's full name is the persona** (`resolve-v5`): "아오키 타쿠미" for the persona "타쿠미". One chat was two
    people, so old speech levels stayed current and promises made to both never closed.
  - **`packet-v5` (new default) names what a relationship, feeling or speech level replaced**, with its turn
    ("…: 연인; before, turn 1: …: 같은 반 친구"), and how it started when that differs, so "how did they stand before"
    has an answer. `NMOS_PACKET_POLICY`
    keeps the earlier policies.
  - **`extract-v13`: goals, questions, threats and debts end** (ADR 0039, migration 0022). They are threads like
    promises; the prompt lists the open ones and `resolved` ends one (achieved, abandoned, failed, answered, averted,
    paid). A craving or the next thing someone is about to do is not a goal. A cause the story states is kept
    (`because`). Re-extracts each chat's recent window. A promise or goal kept from someone who then finds it out is
    no longer shown hidden from them as a thread. A goal the story never mentions again stays open (K23): on the
    owner's longest chat 9 of 48 goals ended and 37 stayed open.
  - **`packet-v6` (new default): the cause the story states** ("…: 화남; because: 약속을 잊어서"), on facts and claims,
    and facts with a cause come first when the message asks why (ADR 0040). The Inspector shows each cause and the
    event it names when one nearby clearly matches.
  - M0 counts answers the prompt's own last messages hold: of 28 cases, 9 need memory; 5 of them before Phase 11, 7 now.
  - Inspector: a **Relationships** section with each pair on one row (relationship, each direction's feeling and
    speech level, with cause, what it replaced and how it started), on the chat and character pages; open threads
    counted by kind.
  - **`packet-v7` (new default): one numbering for `turn`** (ADR 0041). A fact, claim or thread says the
    turn index, but an excerpt's `turn` and a state item's `as_of_turn` said the message's position, so one packet
    could show a goal at "turn 26" next to an excerpt of the next message at "turn 56". Under `packet-v7` they carry
    the turn of their message; excerpts stay in story order. Same outcomes on the memory evaluation and on M0
    (26 of 28). The Inspector's state table ("As of turn") now shows the turn index; it showed the position.
- **The compose files no longer pin a packet policy.** Both passed `NMOS_PACKET_POLICY=packet-v4` unless `.env` set
  it, so a stack started from them on `main` kept `packet-v4` after `packet-v5` and `packet-v6` became the default.
  They now pass it empty, which means the sidecar's own default. No release was affected (`v0.1.0-beta.21` pins
  `packet-v1`, its default).
- **A saved API key is sent only to the host it was saved for** (review of an external analysis, 2026-09-27).
  `/v1/config/test` and `/v1/config/models` sent the saved key to whatever URL the request named, and saving an
  endpoint on another host kept the key for it, so anyone who could reach the settings API could have the key sent
  to their own server. Now a test or model list for another host goes without the saved key (its error says why),
  and saving an endpoint on another host drops the saved key: enter it again. A key from `.env` applies again
  when the endpoint is back on the `.env` host.
- **The plugin's host reads count against the request deadline.** Only the sidecar calls had a hard deadline: a
  settings or chat read the host never answered held the generation. The memory budget and deadline set in
  PocketRisu's own plugin argument fields are capped like the panel's; a budget over 20,000 tokens, which the
  sidecar refuses, made every request go without memory (the panel did not cap the budget either).
- **The worker waits for the sidecar's migrations.** Compose starts both at once, and a worker that claimed jobs
  against the previous schema failed them and used up their attempts.
- **A recall reads the chat as its request had it.** A sync of the same chat from another tab or device (K28)
  that landed during a recall added its messages to what the recall read and recorded.
- Tests: the plugin's DOM code (the Inspector sanitizer's tree walk, the settings panel) runs under `happy-dom`,
  a new dev dependency (owner approval 2026-09-27).
- **The sidecar's access log no longer shows the auth token** (audit A-11). The Inspector opened in a browser
  tab passes the token as `?token=` on every link, and uvicorn logged each request line with it. The log now
  shows `token=***`. The token still stays in that browser's history (K21); the panel's Inspector tab sends
  it in a header.
- Known issues: K28, two tabs or devices taking turns in one chat (audit A-13); K21 now covers the token in
  Inspector links and the plugin's "full database" permission (audit A-18).
- Known issues: K3 measured on the real host. A reroll or a swipe change of the last reply never takes the
  slow sync path, because the reply it replaces was never synced. An edit of an older message does: 3.6–3.8 s
  at 10,000 messages, over the 3 s default (`docs/perf/scale.md`).
- **Knowledge marks given as objects are names again** (ADR 0007). The extraction model sometimes lists
  `known_by` / `hidden_from` entries as `{"name": "타쿠미", "type": "character"}`, the participants shape;
  validation stored the object's repr (`{'name': '타쿠미', 'type': 'character'}`) as the name. Such a mark
  matched no character: the packet's knowledge marks and the ledger's `hidden_from` showed the repr, a
  question naming a character the fact is hidden from did not rank it up, and the Inspector did not list it
  under that character. Validation now keeps the name, and rows stored earlier read as the name without
  re-extraction; the stored rows are unchanged. Ledgers already recorded keep what they recorded. On the
  owner's database this affected 4 assertions, 1 of them still served.
- Plugin tests no longer depend on how busy the machine is (audit A-19): the deadline test runs on a fake
  clock, and the 10,000-message manifest test has its own time limit.
- **Korean memory packets hold more** (K26, ADR 0032; owner decision). The packet's budget is filled against
  a token estimate that counted every Korean character as 1.5 tokens; real tokenizers count 0.74–0.98, so a
  full Korean packet used only 68–75 % of the memory budget. The new default packet policy `packet-v2`
  counts 1.2. A full Korean packet holds about 1.5 more lines and uses 76–85 % of the budget
  (`docs/perf/token-estimate.md`). English packets are unchanged. Nothing is re-extracted. To keep the old
  estimate, set `NMOS_PACKET_POLICY=packet-v1`.
- **An OOC note in a reply no longer becomes a fact** (K27, audit A-12; owner decision). New extractor
  generation `extract-v11`: the prompt says that only the story is evidence. OOC notes, `[System: …]` lines,
  requests to the memory and memory markup give nothing; the story's narration and what characters say
  still count. With `gemma4:31b-cloud` an OOC note in a reply was stored as a fact 3 of 3 times before and 0 of
  3 now, and the plainly told control fact is still kept 3 of 3. Text shaped like a packet line
  (`<Fact …>…</Fact>`) still becomes a fact, because the text normalizer removes the tag before extraction
  (K27). The registry drops `Predicate.epistemic`, which nothing read (audit A-14). Other bars are unchanged or
  within the model's run-to-run variance (`docs/perf/extract-v11.md`).
- **Memory markup in a reply is no longer read as story** (K27; owner decision). New text normalizer
  `clean-v3`: NMOS's own memory markup inside a message (a whole packet a reply echoes, or a line shaped like
  `<Fact …>…</Fact>`, `<Claim>`, `<Thread>`, `<Excerpt>` or a keyed `<Item>`) is dropped together with its
  content. `clean-v2` removed the tag and kept the text, so the extractor read the claim as narration and stored
  it (3 of 3 with `gemma4:31b-cloud`), and recall could offer it as an excerpt. Only the tag names the packet
  writes, spelled the same way, count: a bot's `<state>` block or `<Item>` inventory line stays story text.

- **Secrets: what is kept from someone, and when it stops being a secret** (Phase 10 steps 2–3, ADR 0033). New
  extractor generation `extract-v12`. A fact is marked hidden from a character only when the story keeps it
  from them (a secret, a lie, a surprise, a hidden identity), no longer because they were elsewhere. The
  extraction is shown the chat's open secrets and reports which ones a character finds out in the turn; from
  then on the fact no longer says it is hidden from them, and the facts view shows who found it out and when.
  Deleting that turn restores the secret. On a copy of the owner's longest chat, the plan the mother found out
  at turn 21 is no longer marked hidden from her afterwards (five copies of it end there), a surprise ends
  when it is given, and the daughter's hug promise gets the mark it lacked (`docs/perf/extract-v12.md`).
- A generation's backfill (after a model or prompt change, and "Extract all history") is now extracted oldest
  turn first; new chats and new turns still go newest first. The previous generation keeps serving the turns
  meanwhile, and a later turn's promises and secrets then refer to what this generation extracted.
- **Facts only some characters in the scene know go in a Private section** (Phase 10 step 4, ADR 0034). The new
  default packet policy `packet-v3` works out who is in the scene (characters of the last two turns, anyone
  named now, the user's character) and moves facts and promises that someone present is not shown to know into
  `<Private>`, with a rule: only the holders know it, others must not act on it, and the holders keep it from
  those it is hidden from. A fact hidden from someone in the scene also ranks a little higher. The rule costs
  about 47 tokens of the memory budget when the section opens; with the default 600 a fact line can drop out,
  so raise **기억 예산(토큰) / Memory budget (tokens)** for chats with many secrets (`docs/perf/packet-v3.md`).
  `NMOS_PACKET_POLICY=packet-v2` keeps the previous layout; both compose files now default to `packet-v3`.
- **Per-chat memory mode** (Phase 10 step 5, ADR 0035). A chat's page in the Inspector has a **기억 모드 / Memory
  mode** card. **Strict** gives the model only what everyone in the scene knows: a fact only some of them know
  becomes "something known to A, not known to B", its content withheld (fewer leaks, but the holder forgets it
  too). **First-person narrator** (none, your character, or a character of the chat) leaves out what the
  narrator is not shown to know. Excerpts of the chat that say what the mode left out are left out too. Both
  are off by default, and each request records the mode it used.
- A character's claim that only some of the scene know now goes to the Private section like a fact, with who
  knows it; before, strict mode could still carry a secret word for word as a `<Claim>` (ADR 0035).
- **The default memory budget is 800 tokens** (was 600; owner decision). On the owner's recorded requests a
  600-token packet placed 66% of the memory lines retrieval found, 800 places 89%, and 1000 all of them
  (`docs/perf/memory-mode.md`). If you left **기억 예산(토큰) / Memory budget (tokens)** empty, lower PocketRisu's
  max context by 200 more.
- **The promise your message is about is remembered first** (ADR 0019 amendment 1). Promises were chosen by who
  is named, newest first, three at most, so newer promises could push out the one the scene is about (asking a
  child to go and hug her mother dropped her old promise to do just that). Under the default `packet-v4` a
  promise whose words your message repeats now comes first.
- **A character who found out a secret now counts as knowing it** (ADR 0033 amendment 1). Before, with them in
  the scene the fact still went to the Private section with its rule telling them not to act on it, strict
  mode withheld it from them, and as a first-person narrator they were not given it. Found by the Phase 10
  evaluation, which adds seven synthetic secret cases to CI (`docs/perf/eval-baseline.md`).
- CI also upgrades a database that 0.1.0-beta.21 wrote, and checks that an upgraded chat has the default
  memory mode.
- Known issues: K29, a reveal among the turns first extracted together (connecting an existing chat) can be
  missed; run **Extract all history** once after connecting a chat with secrets.
- **The sidecar says whether your plugin is the right one** (ADR 0037, K19). The plugin sends its build id with
  every sync, and the sidecar compares it with the plugin file of its own version. The Inspector's first page
  says "the sidecar's build", or warns that the plugin in use differs (an older plugin shows as "no build id"),
  or that another tab or device still runs an older one and needs a reload. It links the matching plugin file,
  which the sidecar serves at `/v1/plugin/nmos-pocketrisu.js`. The Status tab of a plugin with the check says
  the same. `/v1/health` reports it too.
- **The Inspector shows a chat's secrets** (Phase 10 step 6). A chat's page has a **비밀 / Secrets** section: each
  fact kept from someone, who knows it, whom it is kept from, the turn, and for each of them whether and when
  they found out. Reports of someone finding out that matched no secret are listed apart, and a character's
  page lists the secrets they found out. The last packet's section names the scene's characters and the
  memory mode the request used. Sidecar only.
- **The Status tab says when memory did not fit** (ADR 0036). When the last reply's memory budget left memory
  out, a card says how many lines of how many, and the budget that holds them all (in steps of 100, up to 2000),
  with a button that sets it. Lower PocketRisu's max context by the same amount. Inspector → Retrievals shows it
  too ("all at N"). With the facts `extract-v12` writes, the owner's chat needs 1000–1100 (`docs/perf/budget.md`).
- **A line that says an earlier line again is left out** (ADR 0036). The new default packet policy `packet-v4`
  keeps one of two lines with the same subject, relation and content (a fact extracted twice, a character's
  claim of what the narration already says), which frees room for others. `NMOS_PACKET_POLICY=packet-v3` keeps
  the previous layout; both compose files now default to `packet-v4`.

### Upgrading from 0.1.0-beta.21

Back up the database first (README, "Upgrade, backup and rollback"): migrations 0021–0026 run when the new sidecar
starts, and a rollback needs the backup.

1. **Pull the new image and restart the sidecar and the worker.** At startup:
   - the normalized text is rewritten (`clean-v3`);
   - migrations 0021–0026 add memory modes, thread outcomes and causes, summaries, owner repairs and canon.
2. **Model calls at the provider's cost** (with an LLM configured):
   - `extract-v13` becomes active, and each chat's latest `NMOS_EXTRACT_BACKFILL` turns (default 100) are extracted
     again once. Older turns keep their earlier facts until **Extract all history**, which also finds reveals a first
     extraction missed (K29).
   - Scenes are summarized (one call per 8 turns and a story call; `NMOS_SUMMARIES=0` or the panel turns this off).
   - Canon facts are read once the new plugin sends a chat's canon: the card, the persona and the note at once, and
     each lorebook entry once a prompt has held it (`NMOS_CANON_FACTS=0` or the panel turns this off).
   - With embeddings on, every message is embedded again.
3. **Replace the plugin file** (the host offers the update: `//@version 0.2.0`) and reload PocketRisu. The sidecar
   serves it at `/v1/plugin/nmos-pocketrisu.js`, and the Inspector says whether the plugin in use matches (ADR 0037).
   - The new plugin brings the memory mode, the repair buttons, the canon sync, the switches and the default budget
     of 2,000 tokens.
   - With the old plugin memory still works, but without canon, repairs or the new default budget.

### Known limitations

- **Canon facts are not yet measured** on the owner's chats (Phase 14 step 6), and neither are their model calls or
  the latency with a large lorebook. A story that changes who someone is, or how two characters stand, is listed in
  "Needs attention" against canon until the owner chooses.
- **Secrets:** a secret is kept by instruction, not isolation (K11). A summary can say a secret in other words (K30).
- **Threads** stay open until the story ends them in words extraction recognizes, or the owner closes them (K23).
- **Names:** a given name alone is a mention only when the lorebook lists it (K31). A persona narrated in the third
  person does not bring its own facts (K32).
- **Long chats:** beyond about 10,000 messages memory needs a higher deadline (K1).
- The full list is `docs/KNOWN-ISSUES.md`.

## 0.1.0-beta.21

The rest of the 2026-09-26 audit (`docs/audits/NMOS-AUDIT-2026-09-26.md` and its review): the owner's
decisions and the remaining fixes. No schema change and no new extractor or embedding generation: nothing
is re-extracted or re-embedded (the generation keys are the same as in 0.1.0-beta.20). The plugin warns
when memory runs out of time; the sidecar checks host names when it has no token.

- **The plugin warns when memory runs out of time** (owner decision on audit A-09, plugin). A long chat that
  needs more than the deadline (3 s by default) used to go without memory silently. Now:
  - the NMOS panel's Status tab opens with a card when the last request missed the deadline, or used 80 %
    of it or more. The card says how long it took and the value to set, with a button to the Settings tab;
  - after a reply that went without memory for the deadline, PocketRisu shows one notice saying the same,
    once per page;
  - the progress display says "over the N s deadline · tap to raise".

  The default deadline stays 3 s. Checked on an isolated PocketRisu v1.12.0.
- **Without a token, the sidecar answers only to known host names** (audit A-05, ADR 0030; owner decision).
  A web page can use DNS rebinding to reach a sidecar on `127.0.0.1` or the LAN from your own browser,
  and without a token it could read chats and settings. The sidecar now accepts requests addressed to an
  IP address, `localhost` or a single-label name (`nmos`, `sidecar`), and refuses other names with HTTP 400.
  If you reach the sidecar by a domain name (a reverse proxy, a tailnet name), add it to
  `NMOS_ALLOWED_HOSTS` in `.env` (for example `risu.example.com,*.ts.net`) or set a token. With a token
  nothing changes.
- **Google Vertex AI is verified against the real service** (audit A-10; owner decision). A key's token
  exchange, the connection test, extraction and recall work with `google/gemini-3.8-flash` (ADR 0022).
  One pitfall showed up: a key whose service account lacks the **Vertex AI User** role
  (`roles/aiplatform.user`) gets HTTP 403, even with the APIs enabled. The connection test now says which
  role to grant.
- **A restart during a long startup backfill resumes it** (audit A-08). The sidecar's startup work
  (normalized text after a normalizer change, turn data, parser state, missing jobs) ran as one
  transaction. A restart before it finished discarded every batch already written, and the next start
  began again. Each step now commits on its own, the batched backfills batch by batch. Parser-state
  backfill and generation activation stay atomic. A startup that fails no longer leaves an open
  connection pool behind.
- **Sidecar and worker always get the same settings** (audit A-03). The development `docker-compose.yml`
  passed `NMOS_LLM_JSON_MODE` to the worker only. Both processes build the extraction generation from their
  settings, so with `NMOS_LLM_JSON_MODE=0` (and no value saved in the panel) the worker never picked up the
  sidecar's jobs and extraction stayed pending. Both compose files now give the two services one shared
  environment, and `NMOS_EXTRACT_HINTS` (documented, but never passed to the containers) is included. The
  worker also logs a warning when queued jobs of the active generation match none of its handlers. A test
  checks that every documented variable reaches both services.
- **The per-message extraction window is retired** (audit A-15, ADR 0031; owner decision). Extractions made
  before 0.1.0-beta.8 (per message, `extract-v3` and earlier) no longer serve facts. If your database still
  relies on them, those turns show no facts until they are extracted again: the recent turns at the next
  sync, older ones with "Extract all history" in the Inspector. Extractions since 0.1.0-beta.8 are
  unaffected. `NMOS_EXTRACT_WINDOW` is removed and ignored if set.
- **Known issue K27: an OOC note or memory-like markup inside a reply can become a fact** (audit A-12). The
  first measurement, with the owner's extraction model, is in `docs/perf/memory-poisoning.md`: a
  `[System: …]` line and a typed command were ignored, but an OOC note and a packet-shaped `<Fact …>`
  inside a reply were stored as facts every time. The fix, a line in the extraction prompt, waits for the
  next extractor generation, so re-extraction is paid once (owner decision). `tools/eval_poisoning_model.py`
  re-runs the check.
- **Long chats with extraction and embeddings on need a higher deadline, measured** (audit A-09, docs). On
  PocketRisu v1.12.0 with 10,000 messages, 15,000 facts and 15,000 vectors, recall adds 0.4–0.7 s. A warm
  generation then takes 3.1–3.3 s, over the 3 s default, so those requests go without memory. Raise
  Deadline (ms) to about 4,000 for such chats. K1 and the README give the numbers.
- **Upgrades from earlier releases are tested, and backup and rollback are documented** (audit A-16). CI
  restores databases that 0.1.0-beta.7 and 0.1.0-beta.16 wrote, with their own code, and upgrades them. It
  checks that the chats stay in sync, the earlier facts stay served, the story goes on, and the worker,
  delete and rebuild work. The README and the Korean guide give the backup, upgrade and rollback commands.
  The rollback restores a backup; migrations only go forward.
- **Docs follow the code again** (audit A-07). The README lists every plugin argument (`route`, `language`,
  `hud` were missing) and no longer calls `extract-v10` unreleased. K1's 10,000-message margin is stated
  for what was measured: chats with no facts or vectors; extraction and embeddings add to it. CI now fails
  when a summary's host-fact, decision, known-issue, ADR or phase range falls behind.
- **Invariant 9 now says what the code does:** storage is PostgreSQL, and replacing it is not a goal (owner
  decision on audit A-06).

**Before upgrading:** back up the database (README, "Upgrade, backup and rollback"). If you reach a
tokenless sidecar by a **domain name**, add that name to `NMOS_ALLOWED_HOSTS` in `.env` first, or requests
will get HTTP 400. This covers a reverse proxy that keeps the browser's host, or a tailnet name. Addresses,
`localhost` and Docker names such as `nmos` need nothing. Then pull the new sidecar image and restart both
services, replace the plugin file, and reload PocketRisu.

### Known limitations

- An OOC note or packet-shaped markup inside a reply can become a fact (K27). The prompt fix waits for the
  next extractor generation.
- With extraction and embeddings on, a chat of about 10,000 messages needs a deadline above the 3 s
  default (K1). The plugin now says so and suggests a value.
- A bot whose Lua `request` trigger rewrites the injected system message into another role can get the
  memory twice when the host retries a failed request (H2, H3).
- Databases from before 0.1.0-beta.8 lose their per-message facts until those turns are extracted again
  (ADR 0031).
- Otherwise unchanged from 0.1.0-beta.20; the full list is `docs/KNOWN-ISSUES.md`.

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
  the order, so trivia (a character's `knows` facts) took the few slots a 600-token packet has. A character's
  agreement to speak 반말 ranked 23rd and was forgotten. Now, among facts of equal mention, how two
  characters stand (`relationship`, `feels_toward`) comes first, then major events, and standing facts
  get the budget before promise threads. A name in a fact's "known by" list no longer ranks it.
- **Speech level and forms of address are remembered** (ADR 0028). New extractor generation `extract-v10`
  with the fact `addresses`: how one character speaks to and calls another, one per direction, e.g.
  "하나 addresses {{user}}: 반말, '타쿠미'라고 부름". It is recorded when the story settles it (an
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
  and by its name (e.g. 타쿠미), and NMOS kept them as two characters: two current locations, split
  promises, and every fact naming 타쿠미 counted as mentioned in every message you narrate by name.
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
  name it typed elsewhere (one character — relationship — another, while that other name is a `character` two
  lines up), and validation parked the fact as pending. When the same reply or the known-entity list gives that
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
