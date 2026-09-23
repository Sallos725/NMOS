# Changelog

## Unreleased

- **Memory works with presets that add instructions after the user's turn.** The plugin used to
  treat a request as the main chat request only if the prompt's **last** user message was the
  user's input. Presets that wrap the input (e.g. `<Current Input>`) and add instruction blocks
  after it therefore got no memory at all: no sync, no recall, and no hint why. Now the input is
  searched in every non-assistant message, whatever the preset layout, and the memory block goes in
  front of the input block instead of inside it (ADR 0001 amendment 2).
- The Inspector tab shows the "open in a browser" address only when the browser can reach the
  sidecar itself; a sidecar reached through the PocketRisu server (Docker name, LAN address behind
  HTTPS) is only reachable from that server.

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
