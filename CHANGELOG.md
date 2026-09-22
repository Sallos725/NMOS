# Changelog

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
