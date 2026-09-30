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
   Allow the "replace content" permission, and the "access the full database" one that follows: NMOS
   reads only your persona's name with it, so that `{{user}}` and the name are one person in memory
   (ADR 0023). Without it NMOS still works.
3. Set the plugin argument `sidecar_url` to `http://127.0.0.1:8790`.
4. **Reload the PocketRisu page.** Always reload after installing, updating or disabling a plugin —
   otherwise PocketRisu can hang on the next message (a PocketRisu bug, see ARCHITECTURE H13).
5. Lower PocketRisu's max context by `reserved_memory_tokens` (default 4000 since Phase 15; 2000 before) so the packet fits.

That's it: raw recall works with no model configured. The panel's **Inspector** tab shows what NMOS
stored and what it injected.

## Upgrade, backup and rollback

Back up before upgrading. Run these next to your `docker-compose.yml`:

```bash
docker compose exec -T postgres pg_dump -U nmos -d nmos -Fc > nmos-backup.dump
```

Upgrade: replace `docker-compose.yml` with the new release's `nmos-docker-compose.yml`, then run
`docker compose pull && docker compose up -d`. The sidecar applies database migrations when it starts.
Replace the plugin file too and reload PocketRisu: the Inspector's first page then says whether the plugin
in use is the sidecar's build, and links the matching file (`/v1/plugin/nmos-pocketrisu.js` on the sidecar;
ADR 0037). Each release's CHANGELOG entry says what the upgrade re-processes, for example a new extractor generation. CI restores databases written by earlier releases
(0.1.0-beta.7, 0.1.0-beta.16 and 0.1.0-beta.21) and upgrades them (`apps/sidecar/tests/test_upgrade.py`).

Rollback: migrations only go forward, and an older image on a newer database is not tested. To go back,
restore the backup you took before upgrading, then start the older release:

```bash
docker compose stop sidecar worker
docker compose exec -T postgres dropdb -U nmos nmos
docker compose exec -T postgres createdb -U nmos nmos
docker compose exec -T postgres pg_restore -U nmos -d nmos < nmos-backup.dump
NMOS_VERSION=0.1.0-beta.19 docker compose up -d   # the release you are going back to
```

Put the older plugin file back and reload PocketRisu. Your chats themselves live in PocketRisu. The next
generation in each chat syncs what changed since the backup, and the worker extracts it again at the
provider's cost.

### Export (NMOS Archive)

An archive (`.nmos.zip`, ADR 0050) holds what NMOS keeps in a form that does not depend on this schema: every
conversation's history, canon, your repairs and links, the recorded requests, and by default the model's extractions
and summaries, so moving it does not pay for extraction again. It never holds an API key or the auth token; the whole
install's archive also holds the settings without keys. It holds chat text: keep it as you keep the chat.

- In the panel: **Settings → Export → Export everything** (tick "Include embeddings" for a larger file that needs no
  re-embedding), or **Export this chat** on a conversation's Inspector page. The browser saves the file.
- From the shell: `docker compose exec -T sidecar python -m nmos_sidecar.archive export -o - > nmos.nmos.zip`
  (`--conversation <id>` for one chat, `--embeddings`, `--no-projections`).
- `GET /v1/archive` on the sidecar (the same parameters: `conversation`, `embeddings`, `projections`).

If NMOS finds a key or the token anywhere in what it would write (a key pasted into a chat), it refuses and says in
which table. `pg_dump` backups stay the way to roll back an upgrade.

Restore (a command; into a fresh install, or one that does not hold the archive's chats):

```bash
docker compose stop sidecar worker
docker compose run --rm -T sidecar python -m nmos_sidecar.archive restore - < nmos-all-20260929-181500.nmos.zip
docker compose up -d
```

It checks every file's size and hash before writing anything (`--check` only checks), refuses an archive from a newer
NMOS and a chat this install already holds (delete it there first; nothing is merged), and upgrades an archive from
an older NMOS as the upgrade would. Settings already set on this install stay. On start the sidecar writes what it
derives and queues what is missing: with extractions in the archive nothing is extracted again. Include embeddings if
you want the Inspector's replays of old requests that used vectors to stay exact.

## NMOS panel (status, inspector, settings)

Open it from the **☰ menu left of the chat input → NMOS 기억 / NMOS memory**, from the **NMOS icon (an N) in the
sidebar's ☰ menu**, or from PocketRisu → Settings → **NMOS 기억 / NMOS memory**. Tabs switch between **Status**, **Inspector** and **Settings**;
the language picker (Korean by default, or English) is at the top right. Menu names follow the
language after a page reload.

- **Status**: first, **This chat**: whether NMOS is on for the chat open now, and a button to turn it off or back on
  for that chat alone (ADR 0048). Off, nothing of the chat goes to the sidecar and no memory goes in; what NMOS
  already keeps of it stays, and turned back on, the next generation catches up. The same switch is in the ☰ menu
  left of the chat input (**NMOS: this chat off/on**), which says in a dialog which way it went. The switch, its
  menu entry and the sidebar icon are read from the PocketRisu v1.13.0 source and not yet checked in a real UI run. Then the
  sidecar connection, which features are on (status window, facts, semantic recall), and what the
  last request injected. **Show the injected memory** opens the exact text that went into that request
  (kept only until the page reloads). When memory did not fit the budget, a card says how much and offers the
  budget that holds it all; after raising it, lower PocketRisu's max context by as much.
- **Inspector**: the Inspector, inside the panel (PocketRisu does not let plugins open a browser tab).
  Click a conversation for its state, facts, entities (names that refer to the same one), recent
  retrievals, commits (with what each sync changed, e.g. `delete ×12`) and messages. On a conversation page three buttons act on that chat:
  **Extract all history** extracts and embeds the older turns the first sync skipped (and moves turns
  still served by an earlier LLM model to the current one, and turns that were extracted before an earlier
  turn's secret, K29), and **Rebuild memory** (click twice)
  discards the chat's facts, from every model, and extracts every turn again. Both leave raw
  messages alone, run in the background and cost one LLM call per turn. **Delete conversation**
  (click twice) deletes everything NMOS stored for that chat, raw messages included, and cannot be
  undone. Use it after deleting the chat in PocketRisu. The PocketRisu chat itself is never touched;
  generating in it again starts a new NMOS conversation. On an entity's page, **Same as another entity**
  joins it with another entity of the same type when the story never linked the two names (e.g. someone
  shown without a name and named later); **Undo** takes a join back. Joins survive a rebuild.
  The Inspector's lines carry the owner's **repairs** (ADR 0044): close a thread with an outcome (tick several to
  close them together) or reopen one, mark a secret found out or still kept by a character, retract or correct a
  fact, and on an entity's page split two names the story joined. A repair survives rebuilds and new extractor
  generations, is listed under **Repairs** with **Undo**, and each chat's page starts with **Needs attention** (old
  open threads, ends that matched no thread, disputed whereabouts, repairs that match nothing now, splits still
  joined through another name, ambiguous names).
  **Canon** (Phase 14, ADR 0045–0047): NMOS keeps each chat's card (its story fields and greeting), lorebook entries,
  persona and author's note as sources, a new revision on each edit, listed in the conversation page's **Canon**
  section. Lorebook keys give a character's other names. The extraction model reads the card, the persona and the note
  once, and a lorebook entry once a prompt held it, for facts from before the story, which the story supersedes; a
  fact whose text the host already sent is not sent again. A story line that changes a **relationship** canon states
  is listed in **Needs attention** with **Lock** (canon's stays, `locked="true"` in the packet) and **Retract** (the
  story's stays). On the owner's chats canon took 26–66 model calls at first; **Facts from canon** in Recall tuning
  turns it off. A chat whose large lorebook is read almost whole recalls more slowly (K36).
  A conversation page lists the chat's **Secrets** (who knows, kept from whom, who found out and when), and the
  last packet's section names the scene's characters and memory mode.
  A conversation page also has a **Memory mode** card for that chat (ADR 0035): **Strict** gives only what
  everyone in the scene knows (a secret becomes "something known to A, not known to B"; fewer leaks, but its
  holder forgets it too), and **First-person narrator** leaves out what the narrator is not shown to know.
  Both are off by default and apply from the next generation.
- **Settings**: connection (sidecar URL, route, memory budget, deadline, on/off); **fact-extraction LLM**
  and **embeddings** with provider presets (Ollama on this PC, OpenRouter, OpenAI, Gemini, Google Vertex AI, any
  OpenAI-compatible endpoint), model list, API key and a **connection test** that makes a real call;
  recall tuning; status-window parser rules (validated before saving).
  For **Google Vertex AI**, paste the whole service-account JSON key file into the LLM's API key field;
  the sidecar renews the access token itself (ADR 0022). Use a dedicated service account with only
  the Vertex AI User role (`roles/aiplatform.user`). Enabling the APIs is not enough: a key without the
  role gets HTTP 403 on `aiplatform.endpoints.predict`, and the connection test says so. Checked against
  real Vertex with `google/gemini-3.8-flash`.
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
| NMOS icon + `기억 불러오는 중…` | NMOS is preparing memory for this request |
| `✓ 기억 주입 (N자)` / `– 관련 기억 없음` | memory went in / nothing relevant (shown 4 s) |
| `⚠ 건너뜀: 제한 시간 초과` | the request went without memory (deadline or sidecar error) |
| `추출 2/5 · 임베딩 5/5` + bar | background extraction/embedding of this chat; `⚠ 실패 N` if some failed |
| `✓ 처리 완료` | that work finished (shown 3 s) |

Tap the pill to open the panel. The text follows the panel language (English: `Recalling memory…`,
`✓ Memory injected (N chars)`, `Facts 2/5 · Embeddings 5/5`, …).

The Inspector lists conversations as **bot name · chat name** (after the next message in that chat)
and follows the panel language. The same pages are also served by the sidecar for a browser tab at
**http://127.0.0.1:8790/inspector** (Korean by default, English at the top right).

A conversation's page starts with what matters now (state, conflicts, threads by kind, secrets, relationships
per pair, facts) and has a **Last
packet** section: every line the latest request offered its memory packet, where it came from, whether it
went in or why not (no budget, state cap), and, once the reply is in the chat, which lines the reply
reused. A hidden fact the reply repeated is marked (ADR 0027). **Relationships** shows each pair on one row: the
relationship, and each direction's feeling and speech level with its cause, what it replaced and how it started
(Phase 11); a fact's stated cause also shows under it in **Facts**, with the event it names when one nearby matches.
**Summaries** shows the summary generation, the story so far and each 8-turn scene with its state: current, held back
for a secret it repeats or was written before (with the secret), not used while a character it is kept from is in the
scene, changed by an edit and written again, queued, or failed with its error (Phase 12). A character's page starts
with **Current state**: what `<Cast>` says of them when they are in the scene (place, condition, feeling toward the
persona, what they carry) and their open goals.

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
| `NMOS_SUMMARIES` | `1` | The extraction model also summarizes each 8-turn scene and the story so far, in the background (ADR 0042); `packet-v8` puts them in `<Story>`. `0` turns this off (so does the panel) |
| `NMOS_CANON_FACTS` | `1` | The extraction model also reads the chat's canon for facts, in the background (ADR 0047): the card, the persona, the author's note, and each lorebook entry once a prompt held it. The story supersedes them. `0` turns this off (so does the panel) |
| `NMOS_EXTRACT_HINTS` | `40` | Entity names from earlier in the chat shown to extraction so it reuses them; `0` turns this off |
| `NMOS_EMBED_BACKFILL` | `2000` | On first sight of a chat, embed the latest N messages (cheap; covers long histories) |
| `NMOS_WORKER_CONCURRENCY` | `2` | Parallel background jobs |
| `NMOS_PARSERS_FILE` | off | State parser rules, e.g. `/config/parsers.json` (mounted from `./config`) |
| `NMOS_RECALL_THRESHOLD` | `0.4` | Minimum trigram match for lexical recall |
| `NMOS_VECTOR_MIN_SIM` | `0.42` | Minimum cosine similarity for semantic recall (model-dependent) |
| `NMOS_EMBED_TIMEOUT_MS` | `300` | How long a request waits for the query's embedding before recalling by shared words only (fail open, PHASE-3). The panel's Status tab says when a request went without vectors (K34). Raise it when the embedder is remote or slow (a request then waits longer for it; the value is per network phase, not a cap on the whole call); changing it re-embeds nothing. A fallback can also be an embedding error (address, key, server): check the embedding settings first |
| `NMOS_EMBED_QUERY_INSTRUCTION` | `auto` | Query instruction for instruction-tuned embedders (`auto` = Qwen3 format for `qwen3-embedding`; `none`; or your text) |
| `NMOS_TRACE_RETENTION_DAYS` | `30` | How long retrieval traces (with each packet's ledger) are kept |
| `NMOS_PACKET_POLICY` | `packet-v10` | Packet compiler (ADR 0027, 0032, 0034, 0036, 0038, 0040, 0041, 0043, 0049, 0053): `packet-v10` is `packet-v9` whose excerpts grow from the sentence holding most of the message's keywords by their neighbouring sentences, up to four and within the length the budget gives them; `packet-v9` is `packet-v8` whose excerpts (count and length) and facts grow with the memory budget above 2,000 tokens, up to 8,000; `packet-v8` adds `<Story>` (the story so far and the scene the message is about, at most 30 % of the budget) and `<Cast>` (each scene character's place, condition, feeling, what they carry and, when named, open goals); `packet-v7` numbers excerpts and state by the turn of their message, as facts are numbered; `packet-v6` numbers them by message position and also shows the cause the story states on a fact (`; because: …`); `packet-v5` names what a relationship, feeling or speech level replaced, with its turn; `packet-v4` leaves out lines that say an earlier line again (a fact extracted twice, a character's claim of what the narration states); `packet-v3` puts facts only some characters in the scene know in a `<Private>` section with a rule for them; `packet-v2` is the same without it (room kept for the best excerpt, Korean counted at 1.2 tokens a character); `packet-v1` counts 1.5, `packet-v0` the one before |
| `NMOS_AUTH_TOKEN` | off | Required if you expose the sidecar beyond loopback (`NMOS_SIDECAR_BIND`); set the plugin's `auth_token` too. See [Security](#security) |
| `NMOS_ALLOWED_HOSTS` | (empty) | Without a token, domain names the sidecar answers to besides IP addresses, `localhost` and single-label names such as `nmos`: e.g. `risu.example.com,*.ts.net`; `*` turns the check off. See [Security](#security) |
| `NMOS_SIDECAR_BIND` / `NMOS_SIDECAR_PORT` | `127.0.0.1` / `8790` | Where the sidecar listens |

Plugin arguments: `sidecar_url`, `auth_token`, `disabled` (1 = off), `reserved_memory_tokens`
(0 = 600), `deadline_ms` (0 = 3000), `inject_position` (`before_last_user` or `end`), `route` (`auto`,
`direct` or `server`: how the plugin reaches the sidecar), `language` (`ko` or `en`), `hud` (1 = progress
display on the chat screen).

**Cost note:** with an LLM configured, every turn (your message plus the reply) is one extraction
call once you continue from it, plus up to `NMOS_EXTRACT_BACKFILL` calls when a long chat is first seen.
Rerolls you discard are never extracted. NMOS only reads chats you generate in with the plugin on; it
never scans other chats by itself.

### State parsers

If a bot's reply ends with something like:

````
```status
HP: 80/100
MP: 30/30
Location: Cafe
```
````

rules in `config/parsers.json` turn that into current state — see
[config/parsers.example.json](config/parsers.example.json), whose `status-block` rule (`key: value` lines
between the start and end of a code block) and `hp` rule (a `HP: 80/100`-shaped regex) match this example.
The inspector's Current state section shows this same example while no state has been parsed yet.

`block` rules read `key: value` lines between a start and end pattern; `regex` rules use named groups
`key`/`value`. Changing rules re-parses history at the next sidecar start.

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

The memory budget buys memory (`packet-v9`, Phase 15, ADR 0049; `packet-v10`, Phase 18, ADR 0053): above 2,000 tokens,
the number of excerpts, each excerpt's length and the number of facts grow with it, from your own excerpt and fact settings, up to four times the
excerpts and twice the facts at 8,000. At 4,000 (the default) a packet holds up to 10 excerpts of up to 960
characters and 16 facts; since `packet-v10` an excerpt grows from the sentence holding most of the message's keywords
by its neighbouring sentences, up to four and within that length. Open threads, events, secrets, `<Cast>` and `<Story>` do not grow: growing them brought back
stale business. A budget above 8,000 is accepted and recalls as 8,000 does.

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

Promises are remembered until the story keeps or breaks them (since 0.1.0-beta.14, Phase 7). A promise a character makes,
in dialogue or narration, becomes an open thread, and it is injected whenever its maker or recipient
comes up again, however long ago it was made:
`<Thread kind="promise" by="Hana" to="{{user}}" turn="10">meet at the lighthouse</Thread>`. When the
story keeps it, breaks it or releases it, it leaves the packet (the Inspector keeps its history). Since
`extract-v13` (Phase 11, ADR 0039) goals, questions, threats and debts are threads too: an aim a character is set
on, something they want to know, a danger over them, or what they owe someone stays open until the story ends it
(achieved or given up, answered, averted, paid), and only open ones reach the packet
(`<Thread kind="goal" by="Hana" turn="26">…</Thread>`); a craving or the next thing someone is about to do is not a
goal. A cause the story states (why someone is angry) is kept with the fact. A
character's routine no longer fills the facts: a packet holds at most three events, important ones
("major": a confession, a betrayal, a death, a secret revealed) first, and a minor event only when
your message is about it. Since `extract-v9` an event is major by what it changes, also when it happens
only in words: an admission, a change from formal to informal speech or a new form of address, a
relationship someone allows, or an incident everyone must deal with. Someone shown without a name is
written as a `?` description (`?검은 망토의 남자`) and joined to their name when a later turn reveals it.

How characters speak to and call each other is remembered as its own fact (since 0.1.0-beta.19, `extract-v10`): an
agreement to drop formal speech, a form of address someone asks for, or a decided change back becomes
`<Fact kind="addresses">Hana addresses {{user}}: informal speech, calls them 'Takumi'</Fact>`, one per
direction; a newer one replaces the older. A reply that only slips into another speech level is not
recorded. How the characters in the scene stand with each other (relationship, feelings, speech) comes
before other facts and before promises. A relationship has one history per pair (Phase 11, ADR 0038): lovers
recorded the other way round replace "classmates", and the line names what it replaced
(`…: lovers; before, turn 3: …: classmates`). If Inspector → Retrievals shows many facts not fitting
(kept/offered), raise the memory budget.

A fact about two people comes back from both sides (since 0.1.0-beta.15, Phase 8): `Hana event: betrayed Kaito` is recalled
when you address Kaito, not only Hana. Extraction lists the other people an event, goal, knowledge fact
or destroyed item involves; being there is not taken as knowing.

Who knows a fact matters (since 0.2.0): a fact the story keeps from someone is marked
`hidden_from` them until the story shows them finding out (ADR 0033). What someone in the scene is not shown to
know goes in a `<Private>` section with a rule: only its holders know it, and nobody voices it in front of
those it is kept from (ADR 0034). The chat's memory mode can withhold it instead, or keep to a first-person
narrator's knowledge (ADR 0035).

A fact quoted from another turn is not injected (since `extract-v14`, Phase 19, ADR 0054). Each extracted fact comes
with a short quote of its evidence; when a quote of 12 characters or more is not in the turn the fact was extracted
from (the model restating what an earlier turn said, say), the fact is kept as pending, "evidence not in the turn": it is never
injected; the fact is remembered from the turn that said it when that turn's extraction found it. A shorter quote, or a fact without one, is
not checked. The Inspector does not list pending facts yet. The model also
sees less of the previous turns (each message up to 1,000 characters instead of 2,000), so an extraction reads about a
sixth fewer input tokens.

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
  can reach the port can read your stored chats and change settings.
- **A saved API key is only sent to the host it was saved for.** A connection test or model list for
  another host goes without it, and saving an endpoint on another host drops the saved key: enter the
  key again. (Up to `0.1.0-beta.21`, a test, a model list or a changed endpoint sent the saved key to
  whatever URL it named.)
- **Without a token, the sidecar answers only to known host names** (ADR 0030). It accepts requests
  addressed to an IP address, `localhost` or a single-label name such as `nmos` or `sidecar`. Anything
  else gets HTTP 400: a web page using DNS rebinding reaches the sidecar only under its own domain name,
  so it cannot read your chats or settings. If you reach the sidecar by a domain name (a reverse proxy,
  a tailnet name), add it to `NMOS_ALLOWED_HOSTS` in `.env`, for example
  `NMOS_ALLOWED_HOSTS=risu.example.com,*.ts.net`, or set a token. With a token the token decides.
- The plugin's `auth_token` is kept in PocketRisu's plugin settings and is readable by anyone who can
  open them (see [ADR 0003](docs/adr/0003-sidecar-token-without-secret-header.md)).
- The Inspector in a browser tab (`/inspector?token=…`) keeps the token in its links, and so in that
  browser's history. The sidecar's access log masks it (`token=***`). The panel's Inspector tab sends it
  in a header instead.

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
  default 3 s deadline covers up to about 10,000 messages without extraction and embeddings. With both on,
  recall adds about 0.4–0.7 s, and at 10,000 messages the 3 s default is no longer enough (3.1–3.3 s
  measured). For long chats, raise Deadline (ms) in the panel's Settings tab: about 4,000 at 10,000
  messages with extraction on, 5,000 at 15,000. The panel's Status tab tells you when a request used 80 %
  of the deadline or missed it, with the value to set. A PocketRisu notice follows the first reply on a page
  that went without memory for it. See `docs/perf/scale.md`.
- Changing the embedding model/endpoint re-embeds previously covered history (recent messages first;
  the Inspector shows coverage as partial until done). Changing the LLM model/endpoint re-extracts only
  each chat's recent turns (`NMOS_EXTRACT_BACKFILL`, default 100); older turns keep the previous model's
  facts, marked "older generation" in the Inspector, until you run **Extract all history** on that chat
  (ADR 0014, since 0.1.0-beta.11). An update that brings a new extractor generation (such as `extract-v14`) does
  the same once, and reads each chat's canon sources once more; the CHANGELOG says which updates do.
- Item and character names are free text unless the story links them: "지도" and "해안 지도" are
  different items. An item lost or destroyed in turns extracted before 0.1.0-beta.13 still shows its
  last holder until **Extract all history**.
- A promise the story forgets stays open; only the story (a kept, broken or released promise) closes it.
- Recall thresholds are tuned on limited data — please report cases where memory is wrong or missing.

## Develop

```bash
cp .env.example .env && docker compose up -d --build    # builds from source
cd apps/sidecar && uv sync && uv run pytest               # needs the compose Postgres on :5436
cd adapters/pocketrisu-plugin && npm ci && npm test && npm run typecheck && npm run build
```

Design: `ARCHITECTURE.md` (invariants, host facts H1–H22, decisions), `docs/phases/`, `docs/adr/`,
`docs/HOST-FACTS.md`. Agent contract: `AGENTS.md`.

## License

MIT
