# Changelog

Each release's "Known limitations" describe that release. The current list, with what was resolved
later, is `docs/KNOWN-ISSUES.md`.

## Unreleased

Phase 5 (entity identity and semantic assertions, `docs/phases/PHASE-5.md`), steps 2–3. Schema:
migration 0014. With an LLM configured, extraction becomes `extract-v5`: each chat re-extracts its
latest `NMOS_EXTRACT_BACKFILL` turns (default 100) once; older turns keep their `extract-v4` facts until
**Extract all history** (ADR 0014).

- **Negation** (ADR 0013). "Hana lost the map" or "Alice did not enter the hall" is stored as a
  negative assertion. It ends the current fact it denies (the same holder of an item, the same place)
  and shows as `negated="true"`; a negation of something else ("not at the station" while at home)
  stands as its own negative fact and leaves the current one alone.
- **Claims are not facts.** What a character says in dialogue is a claim (`asserted_by`). It never
  replaces narrated state, even when newer, and reaches the packet only as `<Claim by="…">` after the
  facts, when relevant. A lie no longer overwrites the story.
- **Plans, conditions and dreams are labeled, not facts.** They are stored with their modality
  (`hypothetical`, `dreamed`, `unknown`) and listed in the Inspector, never injected. A missing
  modality counts as unknown, not actual.
- **`also_called`** records another name for an entity, only when the turn itself gives both names
  (e.g. "하나(Hana)"); otherwise it stays pending. Linking names into one entity comes with Phase 5
  step 4.
- The packet Note explains `negated` and `Claim` only in packets that use them.
- Inspector: facts marked *negated* or *legacy* (`extract-v4` and older), a list of claims, and a list
  of non-actual assertions.
- **Inline images are no longer read as story** (normalizer `clean-v2`). Image plugins write markup
  into the message itself; an illustration insert (`<div><span style="…"><img src="{{raw::…}}">`)
  outgrew the old 500-character tag limit, so the whole `<img …>` tag reached embeddings, extraction
  and excerpts on every illustrated turn. `clean-v2` also drops RisuAI inlay/asset tokens
  (`{{inlay::…}}`, `{{raw::…}}`, …), markdown images and `data:` URIs, lets HTML tags span lines with
  attributes of any length, and no longer eats prose such as `HP < 30 … 3 > 2` as a tag. Upgrading
  re-embeds every revision once and folds into the same one-time re-extraction as `extract-v5`.

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
