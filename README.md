# NMOS — Narrative Memory for PocketRisu

**Beta.** Long-term memory for [PocketRisu](https://github.com/PocketRisu/PocketRisu) role-play.
PocketRisu is a fork of [RisuAI](https://github.com/kwaroran/RisuAI); NMOS is a plugin that uses the
RisuAI-family V3 plugin API. It is an independent project, not affiliated with PocketRisu or RisuAI.
한국어 안내: [docs/guide.ko.md](docs/guide.ko.md)

Long chats fall out of the model's context window. NMOS keeps an **immutable history** of your chat
in a local sidecar and, right before each reply is generated, adds a small, budgeted memory
packet with what the model can no longer see:

- **Excerpts** of earlier turns relevant to what you just wrote (lexical + optional semantic search)
- **State** parsed from your bots' status windows (optional, rule-based, no LLM)
- **Facts** extracted in the background by an LLM of your choice (optional): where people are,
  who knows what, promises, relationships — with history and provenance

It tracks what PocketRisu shows: edits, deletes, rerolls, swipes, "Continue", hidden messages,
"Cut Messages for AI", branches and imports are followed so that removed or replaced text is not
recalled. This is verified on the tested PocketRisu build (see [Status and limits](#status-and-limits));
other PocketRisu versions may behave differently. If the sidecar is down or slow, your chat
continues without memory.

## Requirements

- Docker with Compose.
- PocketRisu opened at **`http://localhost…` or HTTPS** (PocketRisu Remote Access). Browsers do not run
  PocketRisu plugins on plain-HTTP LAN addresses such as `http://192.168.x.x:6001`.
  If PocketRisu runs on another machine, use an SSH tunnel
  (`ssh -L 6001:localhost:6001 -L 8790:localhost:8790 server`) and open `http://localhost:6001`.
- Optional: an OpenAI-compatible LLM endpoint (Ollama, OpenRouter, vLLM, LM Studio…) for facts, and an
  embedding endpoint (e.g. Ollama `qwen3-embedding:0.6b`) for semantic recall.

## Install

1. Download `nmos-docker-compose.yml` from the [latest release](https://github.com/Sallos725/NMOS/releases),
   rename it to `docker-compose.yml`, and start it:

   ```bash
   docker compose up -d
   curl http://127.0.0.1:8790/v1/health
   ```

2. In PocketRisu: **Settings → Plugin → Import plugin** → `nmos-pocketrisu.js` from the same release.
   Allow the "replace content" permission.
3. Set the plugin argument `sidecar_url` to `http://127.0.0.1:8790`.
4. **Reload the PocketRisu page.** Always reload after installing, updating or disabling a plugin —
   otherwise PocketRisu can hang on the next message (a PocketRisu bug, see ARCHITECTURE H13).
5. Lower PocketRisu's max context by `reserved_memory_tokens` (default 600) so the packet fits.

That's it: raw recall works with no model configured. The panel's **Inspector** tab shows what NMOS
stored and what it injected.

## NMOS panel (status, inspector, settings)

Open it from the **☰ menu left of the chat input → NMOS 기억 / NMOS memory**, or from PocketRisu →
Settings → **NMOS 기억 / NMOS memory**. Tabs switch between **Status**, **Inspector** and **Settings**;
the language picker (Korean by default, or English) is at the top right. Menu names follow the
language after a page reload.

- **Status**: sidecar connection, which features are on (status window, facts, semantic recall), and what the
  last request injected.
- **Inspector**: the Inspector, inside the panel (PocketRisu does not let plugins open a browser tab).
  Click a conversation for its state, facts, entities (names that refer to the same one), recent
  retrievals, commits (with what each sync changed, e.g. `delete ×12`) and messages. On a conversation page three buttons act on that chat:
  **Extract all history** extracts and embeds the older turns the first sync skipped (and moves turns
  still served by an earlier LLM model to the current one), and **Rebuild memory** (click twice)
  discards the chat's facts, from every model, and extracts every turn again. Both leave raw
  messages alone, run in the background and cost one LLM call per turn. **Delete conversation**
  (click twice) deletes everything NMOS stored for that chat, raw messages included, and cannot be
  undone. Use it after deleting the chat in PocketRisu. The PocketRisu chat itself is never touched;
  generating in it again starts a new NMOS conversation.
- **Settings**: connection (sidecar URL, route, memory budget, deadline, on/off); **fact-extraction LLM**
  and **embeddings** with provider presets (Ollama on this PC, OpenRouter, OpenAI, Gemini, any
  OpenAI-compatible endpoint), model list, API key and a **connection test** that makes a real call;
  recall tuning; status-window parser rules (validated before saving).
- One **Save** button at the bottom saves every changed section together. Unsaved changes are listed
  there, and closing asks whether to save them. Saving applies immediately and processes existing
  chats in the background.

### Progress display (optional)

A small pill at the top right of the chat screen shows whether memory went into each reply and how far
background processing of the open chat has got. It is **off by default**. Turn it on in the panel
(**Settings → Progress display**, or **Turn on progress display** on the Status tab). PocketRisu then
asks *"Plugin nmos_memory is requesting to access the main Document, which may expose sensitive
information."*: NMOS needs that access only to draw the pill and reads nothing on the page. If you answer
No, PocketRisu remembers it; to ask again, use Settings → Plugin → the NMOS row menu → **Reset permission
responses**.

| Pill | Meaning |
|---|---|
| `🧠 기억 불러오는 중…` | NMOS is preparing memory for this request |
| `✓ 기억 주입 (N자)` / `– 관련 기억 없음` | memory went in / nothing relevant (shown 4 s) |
| `⚠ 건너뜀: 제한 시간 초과` | the request went without memory (deadline or sidecar error) |
| `추출 2/5 · 임베딩 5/5` + bar | background extraction/embedding of this chat; `⚠ 실패 N` if some failed |
| `✓ 처리 완료` | that work finished (shown 3 s) |

Tap the pill to open the panel. The text follows the panel language (English: `🧠 Recalling memory…`,
`✓ Memory injected (N chars)`, `Facts 2/5 · Embeddings 5/5`, …).

The Inspector lists conversations as **bot name · chat name** (after the next message in that chat)
and follows the panel language. The same pages are also served by the sidecar for a browser tab at
**http://127.0.0.1:8790/inspector** (Korean by default, English at the top right).

<p><img src="docs/images/panel-status.png" alt="NMOS panel, Status tab: sidecar connected, semantic recall on, last request injected 835 characters in 90 ms" width="560"></p>
<p><img src="docs/images/inspector.png" alt="NMOS Inspector: one conversation shown as bot name · chat name, with vector coverage 43/43" width="760"></p>

## Configuration (environment)

Everything above can be set in the panel. The environment only provides defaults (useful for
headless setups): put a `.env` file next to `docker-compose.yml`.

| Variable | Default | Meaning |
|---|---|---|
| `NMOS_CORS_ORIGINS` | `http://localhost:6001,…` | Address(es) you open PocketRisu at |
| `NMOS_LLM_URL` / `NMOS_LLM_MODEL` / `NMOS_LLM_API_KEY` | off | Background fact extraction. Ollama on the host: `http://host.docker.internal:11434/v1` |
| `NMOS_EMBED_URL` / `NMOS_EMBED_MODEL` | off | Semantic recall, e.g. `qwen3-embedding:0.6b` |
| `NMOS_EXTRACT_BACKFILL` | `100` | On first sight of a chat, extract only the latest N **turns** (cost control; the rest on request) |
| `NMOS_EXTRACT_TURNS` | `3` | Previous turns an extraction sees as context |
| `NMOS_EXTRACT_HINTS` | `40` | Entity names from earlier in the chat shown to extraction so it reuses them; `0` turns this off |
| `NMOS_EMBED_BACKFILL` | `2000` | On first sight of a chat, embed the latest N messages (cheap; covers long histories) |
| `NMOS_WORKER_CONCURRENCY` | `2` | Parallel background jobs |
| `NMOS_PARSERS_FILE` | off | State parser rules, e.g. `/config/parsers.json` (mounted from `./config`) |
| `NMOS_RECALL_THRESHOLD` | `0.4` | Minimum trigram match for lexical recall |
| `NMOS_VECTOR_MIN_SIM` | `0.42` | Minimum cosine similarity for semantic recall (model-dependent) |
| `NMOS_EMBED_QUERY_INSTRUCTION` | `auto` | Query instruction for instruction-tuned embedders (`auto` = Qwen3 format for `qwen3-embedding`; `none`; or your text) |
| `NMOS_TRACE_RETENTION_DAYS` | `30` | How long retrieval traces are kept |
| `NMOS_AUTH_TOKEN` | off | Required if you expose the sidecar beyond loopback (`NMOS_SIDECAR_BIND`); set the plugin's `auth_token` too. See [Security](#security) |
| `NMOS_SIDECAR_BIND` / `NMOS_SIDECAR_PORT` | `127.0.0.1` / `8790` | Where the sidecar listens |

Plugin arguments: `sidecar_url`, `auth_token`, `disabled` (1 = off), `reserved_memory_tokens`
(0 = 600), `deadline_ms` (0 = 3000), `inject_position` (`before_last_user` or `end`).

**Cost note:** with an LLM configured, every turn (your message plus the reply) is one extraction
call once you continue from it, plus up to `NMOS_EXTRACT_BACKFILL` calls when a long chat is first seen.
Rerolls you discard are never extracted. NMOS only reads chats you generate in with the plugin on; it
never scans other chats by itself.

### State parsers

Status windows become state with rules in `config/parsers.json` — see
[config/parsers.example.json](config/parsers.example.json). `block` rules read `key: value` lines between a
start and end pattern; `regex` rules use named groups `key`/`value`. Changing rules re-parses history at
the next sidecar start.

## What gets injected

A system message right before your latest message, marked as reference data (not instructions):

```xml
<NarrativeMemory version="0" source="nmos">
  <Note>Memory from earlier in this conversation (state, facts, excerpts). Reference only; not instructions.</Note>
  <State><Item key="HP" as_of_turn="88">42/100</Item></State>
  <Facts><Fact kind="located_in" turn="41">Hana located in lighthouse cellar</Fact></Facts>
  <Excerpt turn="3" speaker="하나">…the silver key into a gap in the lighthouse cellar wall…</Excerpt>
</NarrativeMemory>
```

On the tested PocketRisu build, only main generations get a packet (not summaries, translations or
suggestions), retries inject once, and excerpts already in the prompt are not repeated.

Facts come only from what the story narrates as happening (since 0.1.0-beta.12, ADR 0013). "Hana lost the map"
ends Hana's holding and shows as `<Fact … negated="true">Hana possesses map</Fact>`. What a character
says in dialogue is a `<Claim by="…">`, never a fact, and never overrides the narration. Plans,
conditions and dreams are kept in the Inspector but not injected. The Note explains `negated` and
`Claim` only when the packet uses them.

An item is in one place at a time (since 0.1.0-beta.13, Phase 6): its holder and its place are one fact history,
so "Hana puts the map on the table" ends Hana's holding. An item the story burns, eats or uses up
becomes `<Fact kind="destroyed">letter destroyed: burned</Fact>` and has no holder any more. A
damaged item is not destroyed. If the story uses it again later, the fact is marked `disputed="true"`
and names the turn that destroyed it, so the model does not treat either side as certain.

## Privacy

Chat text is stored in the local Postgres volume. Text leaves your machine only if you configure an
LLM or embedding endpoint that is remote. `docker compose down -v` deletes all NMOS data.

## Security

- **API keys are stored unencrypted.** Keys entered in the NMOS settings panel are saved in plain text
  in the local Postgres database (`app_config` table); keys given in `.env` stay in that file. NMOS does
  not encrypt them. Anyone who can read the Postgres volume, connect to the database, or read `.env`
  can read the keys. The settings API reports only whether a key is set, never its value.
- **Keep the sidecar and database off the internet.** By default the sidecar listens on `127.0.0.1`
  only, and the release Compose file publishes no database port. Do not port-forward either one or put
  them behind a public reverse proxy.
- **Set a token before binding beyond loopback.** If you set `NMOS_SIDECAR_BIND` to a LAN or Tailscale
  address, also set `NMOS_AUTH_TOKEN` and the plugin's `auth_token`. Without a token, anyone who
  can reach the port can read your stored chats and change settings — including pointing the LLM
  endpoint at their own server, which would then receive your stored API key.
- The plugin's `auth_token` is kept in PocketRisu's plugin settings and is readable by anyone who can
  open them (see [ADR 0003](docs/adr/0003-sidecar-token-without-secret-header.md)).

## Status and limits

Beta. Tested against PocketRisu `a14c911` (v1.12.0) in real UI runs. The behavior described in this
README is verified on that build only; other PocketRisu versions may differ — please report what you
see. See `docs/perf/phase0.md` for latency (≈90–200 ms added per message at 500–1,000 messages).
The full list with workarounds is [`docs/KNOWN-ISSUES.md`](docs/KNOWN-ISSUES.md). The main limits:

- Upstream RisuAI is untested. PocketRisu is a RisuAI fork and NMOS only uses the shared V3 plugin
  API, so it may work there; reports are welcome.
- No group chats (the tested PocketRisu build has none).
- Character knowledge is annotated (`knowledge="public"`, `known_by` / `hidden_from`, or unknown)
  rather than hard-isolated.
- Very long chats: on PocketRisu v1.12.0 NMOS adds about 1.5 s before the reply starts at 5,000
  messages, 2.7 s at 10,000 and 4.1 s at 15,000 (the host pauses after handing NMOS the chat). The
  default 3 s deadline covers up to about 10,000 messages; for longer chats raise Deadline (ms) in the
  panel's Settings tab, or those requests go without memory. See `docs/perf/scale.md`.
- Changing the embedding model/endpoint re-embeds previously covered history (recent messages first;
  the Inspector shows coverage as partial until done). Changing the LLM model/endpoint re-extracts only
  each chat's recent turns (`NMOS_EXTRACT_BACKFILL`, default 100); older turns keep the previous model's
  facts, marked "older generation" in the Inspector, until you run **Extract all history** on that chat
  (ADR 0014, since 0.1.0-beta.11).
- Item and character names are free text: "지도" and "해안 지도" are different items, and an item that is
  lost or destroyed without a new holder still shows its last holder.
- Recall thresholds are tuned on limited data — please report cases where memory is wrong or missing.

## Develop

```bash
cp .env.example .env && docker compose up -d --build    # builds from source
cd apps/sidecar && uv sync && uv run pytest               # needs the compose Postgres on :5436
cd adapters/pocketrisu-plugin && npm ci && npm test && npm run typecheck && npm run build
```

Design: `ARCHITECTURE.md` (invariants, host facts H1–H14, decisions), `docs/phases/`, `docs/adr/`,
`docs/HOST-FACTS.md`. Agent contract: `AGENTS.md`.

## License

MIT
