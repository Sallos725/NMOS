# NMOS — Narrative Memory OS for PocketRisu

External long-term memory for PocketRisu role-play. PocketRisu stays the host. A thin V3 plugin
syncs an immutable history of the chat to a sidecar. Before each main generation, it injects a small,
budgeted packet of relevant **earlier excerpts that are no longer in the prompt**.

Current state: **Phase 0 complete** (walking skeleton, no LLM calls). See `docs/STATUS.md`.

## Run it

Requirements: Docker, and PocketRisu opened from **`http://localhost…` or HTTPS** (PocketRisu Remote
Access). Over plain-HTTP LAN addresses PocketRisu does not load V3 plugins at all (ARCHITECTURE H8).

```bash
cp .env.example .env   # set NMOS_CORS_ORIGINS to the address you open PocketRisu at
docker compose up -d --build
```

```bash
curl http://127.0.0.1:8790/v1/health
```

In PocketRisu:

1. Settings → Plugin → Import plugin → `adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js`, allow
   the "replace content" permission.
2. Set the plugin argument `sidecar_url` (e.g. `http://127.0.0.1:8790`). `auth_token` is only needed
   if you set `NMOS_AUTH_TOKEN` (when exposing the sidecar beyond loopback).
3. Lower the host's max context by `reserved_memory_tokens` (default 600). The packet never exceeds it.
4. **Reload the page.** Required after every install, update or disable of any V3 plugin
   (ARCHITECTURE H13). Without it, generation hangs.

Plugin arguments: `disabled` (1 = pass-through), `reserved_memory_tokens` (0 = 600),
`deadline_ms` (0 = 800), `inject_position` (`before_last_user` default, or `end`).

Behavior: only main generations get a packet (ADR 0001). A sidecar that is down or slower than the
deadline never blocks the chat (fail open). Retries inject exactly once. Deleted, edited-away,
rerolled-away, disabled and "cut for AI" messages are never recalled.

Sidecar tools: `docker compose exec sidecar nmos-migrate`, `docker compose exec sidecar nmos-rebuild`,
`GET /v1/trace/{id}` for why a packet looked the way it did.

## Develop

```bash
cd apps/sidecar && uv sync && uv run pytest     # needs the compose postgres on 127.0.0.1:5436
cd adapters/pocketrisu-plugin && npm install && npm test && npm run typecheck && npm run build
```

## Read first

`AGENTS.md` (agent contract) → `ARCHITECTURE.md` → `docs/phases/PHASE-0.md` → `docs/HOST-FACTS.md`
→ `docs/adr/`. `docs/reference/` is non-normative design rationale.
