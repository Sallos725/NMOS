# NMOS — Architecture

> Narrative Memory OS for PocketRisu (primary) and RisuAI (secondary).
> This file is the **stable contract**. It changes rarely and only by explicit decision.
> Phase-specific scope lives in `docs/phases/PHASE-N.md`. The long-form design rationale
> lives in `docs/reference/ultimate_narrative_memory_architecture.md` (reference only, not a spec).

---

## 1. Core idea

Preserve conversation, canon, edits, swipes and branches as **immutable source history**.
Treat every "memory" (facts, state, relationships, knowledge, summaries, threads, style)
as a **rebuildable projection** of that history.

```text
Host (PocketRisu)
   │  beforeRequest / output listener / snapshots
   ▼
Thin Host Adapter (plugin)          ← no memory logic here
   │  HTTP (token auth)
   ▼
Sidecar
   ├─ Reconciler ──► Source Ledger (immutable)
   │                    │
   │                    ▼
   │               Compiler (async, versioned)  ──► Projections (rebuildable)
   │                                                   │
   └─ Retrieval ◄──────────── Indexes (rebuildable) ◄──┘
        │
        ▼
   Selector ► Context Compiler ► MemoryPacket ► back to plugin ► injected
```

## 2. Invariants (non-negotiable)

1. **Raw evidence is never destroyed** by NMOS itself. Summaries may replace text in the prompt, never in storage.
   The one exception is the owner explicitly deleting a whole conversation (D23, ADR 0009).
2. **Derived memory is rebuildable** from `source ledger + compiler version + config`.
3. **The response model never writes canonical memory.** MCP tools, if any, are read-only.
4. **Unknown is a valid result.** States include known / unknown / ambiguous / conflicting / pending / inferred.
5. **Current state and historical state are both answerable** (versioned facts, not overwrites).
6. **Character knowledge ≠ world knowledge.**
7. **Inactive sources cannot influence generation.** After edit/delete/reroll/swipe, dependent derived memory is invalidated before the next packet is built.
8. **Retrieval ≠ utilization.** Retrieved, visible, placed-in-context, and actively-used are separate decisions.
9. **Storage is PostgreSQL.** Domain code uses PostgreSQL features directly (`pg_trgm`, `pgvector`, explicit SQL, §6); replacing the store is not a goal. *Amended 2026-09-26 by owner decision (audit A-06); it read "Storage is replaceable … repository/index interfaces", which the code never did.*
10. **Every automatic claim has provenance** back to source revisions and compiler version.

Additional operational invariants:

- **Fail open.** Sidecar down or slow ⇒ the host generates normally without memory.
- **Never knowingly inject stale semantic state.** Stale ⇒ mask it and fall back to raw evidence or abstain.
- **The plugin never mutates host chat data** (no `setChatToIndex`).

## 3. Layers and responsibilities

| Layer | Owns | Must not contain |
|---|---|---|
| Host Adapter (plugin) | ID capture, manifest building, request gating, packet injection, output notification, settings | DB, extraction, ranking, long work, migrations |
| Source Layer | conversations, source objects/revisions, worldline commits, membership, host observations | interpretation of content |
| Compiler | normalization, entity/assertion/event extraction, validation, verification | direct writes to projections without provenance |
| Projection Layer | fact/knowledge/relationship versions, threads, scenes | anything not rebuildable from ledger + compiler |
| Retrieval Layer | routing, lexical/SQL/vector/graph search, fusion, selection, packet compilation | canonical writes |

## 4. Verified host facts (PocketRisu `a14c911`, source 2026-09-12, runtime 2026-09-22)

These were checked in source and **override** assumptions in the reference document.
H1–H7 were re-checked and extended by the Phase 0A runtime spike; H8–H14 are new runtime facts
(H13–H14 found while running Phase 0B against the real host); H15–H17 were added later with their ADRs.
Evidence for every runtime claim is in `docs/HOST-FACTS.md`.

| # | Fact | Consequence |
|---|---|---|
| H1 | `beforeRequest` replacer is called as `replacer(formated, model)`; 2nd arg is the **model mode** (`ModelModeExtended`), not a request purpose. Runtime: send/reroll/continue/retry → `model`; Auto Suggest → `submodel`. Trigger/Lua LLM calls also use `model` (source). | Main-generation gating needs a heuristic; auxiliary requests (summary, translation, etc.) pass through the same hook. |
| H2 | The replacer runs **inside the retry loop**; `formated` is only reset per fallback model. Runtime: 2 failures + 1 success = 3 calls with identical prompts, ~7 ms apart. | Injection must be idempotent (marker check) and reconcile/retrieve must be cached per request. |
| H3 | The replacer runs **after** host prompt assembly and context trimming, and **before** the Lua `request` trigger, whose returned array replaces the prompt wholesale. | Injected tokens can overflow max context; triggers may rewrite our packet. |
| H4 | New AI messages get `chatId = generationId`. Regeneration that replaces a message yields a **new** `chatId`, and the replaced reply moves into the new message's `swipes`; `continue` keeps the existing `chatId` but **replaces `generationId`** (so `generationId ≠ chatId` afterwards). With the default `useSayNothing`, "Continue Response" on a char tail appends a `*says nothing*` message and continues *that* message, which becomes `role: 'char'`. | Reroll is observed as delete + append, not as a new revision of the same ID. Lineage must be inferred from position/parent/swipes. `generationId` is not a stable message key. |
| H5 | Chat branching calls `reissueMessageIds()` and copies messages up to and including the branch point. The copied AI messages **keep their origin `generationId`**. A `{{specialcomment::branchedfrom::<origin chat.id>::<origin chat name>::<origin branch-point chatId>::}}` message is appended last (`role: 'char'`, `isComment`, `disabled: true`). | Cross-chat branches are new conversations unless we parse this marker; the prefix maps to the origin by position (and by `generationId` for AI messages). |
| H6 | `normalizeChat()` assigns UUID `chatId` to messages missing one at hydration and import. Message ids are unique only **within** a chat: importing a chat keeps every message `chatId` under a new `chat.id`. | Logical message identity is `(host chat id, Message.chatId)`, never `chatId` alone. |
| H7 | `output` listeners are awaited sequentially; snapshots are plain copies. The `output` snapshot precedes some host post-processing (reroll `swipes` are attached after it). | Listener must return immediately; background work is fire-and-forget. Output notifications are provisional hints; the next request snapshot is authoritative. |
| H8 | V3 plugins run only in a secure context (sandbox uses `crypto.randomUUID`). Over plain-HTTP LAN they do not load; on localhost/HTTPS `crypto.subtle` is available in the sandbox (`a14c911`, v1.12.0). *2026-10-08, PocketRisu v1.13.0 (the owner's Phase 38 check):* over plain-HTTP LAN the plugin loads, but `crypto.subtle` is missing. | Plugin-side SHA-256 is available on localhost/HTTPS; deployment must be localhost or HTTPS (Remote Access). Where `crypto.subtle` is missing the plugin skips every request and says so (K6). |
| H9 | The current chat index is positional: importing a chat prepends it without changing `chatPage`, so the same index then names a different chat. | Never use character/chat index as identity; key conversations by `chat.id`. |
| H10 | Edit, delete, disable, swipe switch, branch, import and reload fire no plugin hook. | Divergence is discovered only at the next main-generation snapshot. |
| H11 | Build `a14c911` has no group-chat type (`character.type` is only `"character"`; `isGroupChat` is hard-coded `false`). | Group-chat principal logic has no host surface on this build. |
| H12 | `saveSecretHeader` is an unimplemented stub; `nativeFetch` fetches directly from the browser (proxy fallback), passes headers through, and accepts a numeric `requestTimeoutMs`. | Sidecar token lives in a plugin arg (ADR 0003); sidecar must serve CORS; deadlines use `requestTimeoutMs` + a local timer. |
| H13 | V3 `addRisuReplacer` registers no unload callback (`loadPlugins` clears only `chatOutput`). After a V3 plugin is disabled, updated or re-imported, its old `beforeRequest` replacer stays registered against a dead iframe and **every generation hangs** until the page is reloaded. | Always reload PocketRisu after installing/updating/disabling the NMOS plugin (documented in README). The plugin cannot guard against this. |
| H14 | On reroll the host removes the tail AI message *before* `beforeRequest` runs (S2 beforeRequest saw 7 of 8 messages; confirmed in 0B live runs). The regenerated reply appears only in the next request's snapshot. | Live reroll reconciles as "head minus tail" → retract; lineage to the new reply is not observable in the same request. |
| H15 | The V3 plugin iframe is sandboxed with only `allow-scripts allow-modals allow-downloads` and `allow="screen-wake-lock"`. Runtime (v1.12.0): a `target="_blank"` link is blocked ("sandboxed frame whose 'allow-popups' permission is not set"), and `navigator.clipboard.writeText` is refused by permissions policy. The V3 API has no call that opens a URL. | The plugin cannot open a browser tab. The Inspector is shown inside the panel from `/v1/inspector*`, and links in it must be handled by the panel (following one would navigate the plugin frame). |
| H16 | With the `mainDom` permission (host confirm, persisted; a denial is permanent until reset) a V3 plugin gets the page through an async `SafeElement` proxy (text is escaped, `setInnerHTML` is sanitised). Element listeners are registered on the whole document. A plugin re-import leaves drawn elements behind until reload. | The progress HUD (D28) is opt-in from the panel, hit-tests clicks against its rect, and removes a leftover `.nmos-hud` before drawing. |
| H17 | The V3 API has no user-name call. `getDatabase(['personas', 'selectedPersona'])` returns the personas (`id`, `name`, …) and the selected index behind the host's "db" permission, asked once (a denial returns `null` and is permanent until reset). The host names the user after the chat's `bindedPersona` (in the `getChatFromIndex` snapshot), else the selected persona. A typed `{{user}}` is stored with the name in place. | The plugin reads the persona name at load and in the background, never on the request path; the sidecar resolves it as the persona (ADR 0023, D34). |
| H18 | The V3 `alert(message)` is PocketRisu's `alertNormal`: it sets the one global alert store (a later alert replaces the one on screen) and shows a modal with a Confirm button. Shown after a reply it appears over the chat and leaves the reply as it is. | The plugin alerts only from the output listener, after a reply, at most once per page (deadline advice, audit A-09); never on the request path. The one other alert answers the owner's own tap on the chat-menu switch, once per tap (ADR 0048). |
| H19 | The V3 API exposes canon (v1.13.0): `getCharacter()` (the card: `name`, `desc`, `personality`, `scenario`, greetings, `globalLore`), `getCurrentLorebookEntries()` (the character's, the chat's and the enabled modules' entries, every one, activated or not), the chat's `note` and `localLore` in `getChatFromIndex`, and `personaPrompt` through `getDatabase` (H17's permission). An activated entry's `content`, the card's `desc`/`personality`/`scenario`, the note and the persona prompt are in the outgoing prompt verbatim (the greeting only while the host's context still reaches it). `getCharacter()` clones the current chat's messages (82–93 ms at 10,000 messages); the lorebook and persona calls take about 1 ms. | The plugin reads lorebooks, the note and the persona at each request, and the card off the request path; activated entries are known by their text in the prompt (PHASE-14, ADR 0045). |
| H20 | Card and lorebook texts can hold the host's CBS blocks, rendered in the prompt, not sent verbatim (v1.13.0, source reading): `{{#if …}}`, `{{#if_pure …}}`, `{{#when …}}`, `{{#each …}}` and `{{#func name …}}` show their body only for some values of the chat's variables, or not as written; `{{#pure}}`, `{{#pure_display}}`, `{{#code}}` and `{{#escape…}}` show it; `{{/…}}` closes the innermost block; any other `{{#…}}` is no block. | NMOS reads a canon text raw, with every branch; a canon fact whose evidence is only inside a conditional block is not served (ADR 0047 amendment 2). |
| H21 | A V3 plugin's frame can save a file (v1.13.0, Chromium and Firefox; an iPhone home-screen app, where the host may then alert, K38; Android not observed): a Blob on an `<a download>` clicked by script, even seconds after the owner's tap, is saved under its name. `nativeFetch` returns binary bodies whole on both routes (30 MB: ≈0.15–0.26 s). A link from the frame to a file on another origin does not download; it navigates the frame to an error page. | The panel's Export fetches the archive through `nativeFetch` and saves it as a Blob, never by a link (PHASE-16 Q6). |
| H22 | The V3 API has no chat-list call (v1.13.0). `getDatabase(['characters'])` (H17's permission) returns every active character with every chat's `id`: a chat not opened since the page loaded is a placeholder without messages, while an opened one carries all of them and stays loaded until reload (≈0.5 ms with none open, ≈100 ms with 10,000 messages open, ≈130–150 ms with 15,000; a probe round making two such copies showed host tasks of 50–66 ms). A deleted chat and a character moved to the trash or deactivated (restorable, same chat ids) both just leave the list. | Not used yet (C10, AGE-4). A chat missing from the list is not necessarily deleted, and the read costs more with every chat the owner has opened, so it cannot sit on the request path. |
| H23 | A V3 plugin's frame can send a request body whole through `nativeFetch` on both routes (v1.13.0, Chromium and Firefox; up to 64 MB observed): a `Uint8Array` (transferred: the frame's copy is emptied) or a JSON string; a `Blob` is refused (`Invalid body type`), and so is a POST or PUT without a body. base64 in JSON is ≈2.3× faster than a `Uint8Array` in Chromium. | The panel's restore sends an archive in 8 MB chunks of base64 in JSON (PHASE-38 Q3). |

## 5. Key decisions

Short ADR-style entries. Full ADRs go in `docs/adr/`.

**D1 — Plugin-first, no fork.** Pure plugin mode is the only supported mode until profiling
proves a bridge API is needed (see reference §82 criteria). Any future fork is bridge-only.

**D2 — Token budget is reserved, not stolen.** Because of H3, the user lowers the host's
max context by `reservedMemoryTokens` (setting; default 4,000 since Phase 15, ADR 0049; 2,000 since Phase 12, ADR 0042;
800 since Phase 10, was 600). The packet
never exceeds that reserve.
Trimming host history from inside the plugin is opt-in since Phase 60 (ADR 0083, D82); it removes only what the host
would send, and the reserve is unchanged.

**D3 — Do not re-inject what the host already sent.** Evidence whose source revision is
already present in the outgoing `formated` messages is excluded from the packet.
Activated lorebook entries are treated the same way. Lorebook is canon for conflict checks,
not a retrieval payload by default. **Amended 2026-11-23 (ADR 0083, D82):** messages before a trimming boundary leave
the in-context set before recall, so their evidence may be excerpted; the trace records the effective set.

**D4 — Worldline commits only on divergence.** Appends update membership; commits are created
for edit / delete / swipe / reroll / disable / branch / import / manual. Full DAG semantics
are kept in the schema but not exercised beyond what reconciliation needs. An append is recorded as a
`worldline_append` row of the head commit (migration 0013) and, when the request provably extends the
head, reconciled from the head's tail only (ADR 0010).

**D5 — Lazy compilation.** Assistant output enters the ledger as `PROVISIONAL` immediately,
but semantic compilation runs only after it becomes `ACCEPTED` (user continued from it).
Swipe churn does not burn extraction calls.

**D6 — Closed predicate registry.** The compiler may only emit predicates defined in
`packages/domain/predicates` with declared subject/object types, cardinality
(single/multi-valued), and epistemic class. Unknown predicates become `pending` candidates
for review, not facts. Since `extract-v6` the registry also has `destroyed` (an item that no longer
exists; D30, ADR 0017), and since `extract-v7` `fulfilled` (a kept promise; D32, ADR 0019). An
`event` also carries `salience` (`major` / `minor`, migration 0016; D32, ADR 0020). Since `extract-v8`
an `event`, `goal`, `knows` or `destroyed` carries typed participants (`with`, migration 0017; D33,
ADR 0021); they are outside the registry fingerprint like other read rules, but part of the prompt.
Since `extract-v9` `also_called` also records the name the target turn reveals for a character listed
as unnamed (D35, ADR 0024). Since `extract-v10` the registry has `addresses` (how one character speaks to
and calls another, single per direction; D38, ADR 0028). Since `extract-v11` a predicate no longer declares an
epistemic class: nothing read it (audit A-14). The prompt also says that notes outside the story (OOC, system
lines, requests to the memory, memory markup) are not evidence (audit A-12, K27). **Amended 2026-11-23 (ADR 0086,
D86):** a compiler may declare per-compiler predicates outside `REGISTRY` (`predicates.EXTENSIONS`, `extract-v19`'s
`told`); validation and prompt formatting read `REGISTRY` plus the compiler's extension (`registry_for`), while the
registry fingerprint hashes `REGISTRY` alone and the extension is hashed into that compiler's `prompt` fingerprint so
earlier generation keys do not move.

**D7 — Bounded extraction context, per turn (revised 2026-09-23, ADR 0008).** The unit of
extraction is the **turn**: a run of user messages plus the run of replies that answers it (comments,
disabled and pre-`allBefore` messages excluded; the greeting is turn 0). A turn is extracted once,
when its anchor (last reply) is accepted, with at most the previous `K` turns as context
(`NMOS_EXTRACT_TURNS`, default 3). An edit inside turn *t* re-extracts only turns `[t, t+K]`.
Extraction is keyed by `(anchor revision, turn_hash, extractor generation)` (D20). **Amended
2026-09-24 (ADR 0012):** the prompt also lists up to `NMOS_EXTRACT_HINTS` (default 40; part of the
generation) entities mentioned on the head before the target turn, newest first, so the model can reuse
names. This is the only input from beyond the `K`-turn window; it is recorded on the extraction row
(`hints`) and does not affect validity: every assertion still needs evidence in the target turn.

**D8 — Synchronous invalidation, asynchronous recompilation.** At `beforeRequest`, stale
derived rows are masked synchronously (no LLM). Re-extraction is queued. Until it finishes,
retrieval uses raw evidence for the affected range.

**D9 — Principal modes.** `omniscient_narrator` (default for single-call bots): world truth
available, character knowledge boundaries attached as annotations.
`character_pov`: hard epistemic ACL; hidden values are never placed in context. **Not implemented
and not authorized** (Phase 4 shipped the soft subset only, D19; Track B, B5).
Hard isolation across simultaneously generated characters is out of scope (reference §30).

**D10 — Deterministic structure first.** Status windows, HTML/regex display blocks, and other
machine-shaped content in messages are parsed deterministically (per-bot parser configs)
before any LLM extraction. This is the preferred source for current-state facts.

**D11 — Lexical recall must work for CJK.** Postgres default FTS tokenization is inadequate
for Korean/Japanese. Use `pg_trgm` (or `pg_bigm` if available) for raw evidence recall.
Exact-quote recall always prefers lexical over vector search. The trigram index covers the normalized
text projection (D21), not raw content.

**D13 — Main-generation gating (O3, ADR 0001).** Inject only when `mode === 'model'` and the
host chat's latest user message is in a non-assistant prompt message (cleaned-text anchor match,
newest first; no preset layout assumed). The packet goes before that turn.

**D14 — Branches are new conversations (O4, ADR 0002).** Record origin chat ref, origin
conversation (if known) and branch-point message ref from the `branchedfrom` marker; no
cross-conversation revision linking.

**D15 — Raw recall scoring (ADR 0004).** Candidates must match the latest user message
(`word_similarity ≥ 0.4`); the previous AI turn only breaks ties; `disabled` and `allBefore`-cut
ranges are inactive and never recalled. A query matching more than 200 head messages is too broad to
score: lexical recall abstains for it (trace `too_broad`), other routes still run (Track A, A3). Amended by ADR 0052:
a second lexical route looks up the message's keywords one by one (D62).

**D16 — Deterministic state via parser rules (Phase 1).** JSON rules → `state_observation`
projection; current state read through head membership (inherits D8 invalidation).

**D17 — Extraction validity is keyed by window (Phase 2, D7; ADR 0008).** `active_membership.turn_hash`
(anchor rows) makes an extraction valid only while the head shows the same turn and bounded context;
the per-message `window_hash` was kept for generations compiled before turns until ADR 0031 retired it
(2026-09-26): extractions match on `turn_hash` only. Jobs run in `nmos-worker`
through a SKIP LOCKED queue; single-valued predicates form fact versions.

**D18 — Hybrid recall (Phase 3, ADR 0005).** Exact cosine over head-membership chunk embeddings (pgvector),
RRF with lexical, abstention by per-signal bars, query-side instruction for instruction-tuned embedders,
fail-open to lexical on embedding timeout. Since D70 the query is embedded while recall reads, and the timeout bounds
the wait after the reads. **Amended by PHASE-60 S5 (ADR 0084):** under `packet-v20` a short message is embedded with
the end of the reply before it (`sem_query`, D70); under any policy, a reranker the owner configured may reorder the
fused candidates (D88). Without either, recall is as above.

**D19 — Soft character knowledge (Phase 4 subset; revised 2026-09-22, ADR 0007).** Each assertion
has `knowledge = public | limited | unknown`. `public` is openly known and needs no list; `limited`
names characters shown to know it (`known_by`) and/or characters it is kept from (`hidden_from`);
`unknown` means the evidence does not show who knows. Awareness of anyone not listed is unknown, never
"does not know"; the packet Note says exactly this. A name in both lists is contradictory evidence and
is dropped from both (noted on the assertion). Names are free text in this soft phase. A fact hidden
from a character addressed right now is ranked first. Hard POV isolation stays out of scope: a sim bot
writes every character in one generation (D9). **Amended 2026-09-26 (ADR 0026, D37):** a name in
`known_by` no longer counts toward ranking. **Amended 2026-09-27 (ADR 0033, D43):** `hidden_from` names only
characters a fact is deliberately kept from, never someone who was only absent.

**D20 — Derived projections are bound to a generation (ADR 0006).** An extractor generation hashes
compiler version, prompt and predicate-registry fingerprints, normalizer version, endpoint identity,
model and output-affecting settings. An embedding projection hashes endpoint, model, normalizer,
chunker and document profile. Credentials are never part of a key. Jobs, extractions and embedding
rows carry their key. A worker only claims jobs for the generation its handler implements. Vector
readers use only the active projection. Older generations stay stored for audit; fact readers may fall
back to one per turn (below), never mixing two in one turn.
Embedding activation queues the recent window first, then every older item an earlier projection
covered, at background priority. **Extractor activation (amended 2026-09-24, ADR 0014)** queues only
the recent window (`NMOS_EXTRACT_BACKFILL` turns); per turn, facts come from the active generation if
it has the turn, otherwise from the most recently active earlier generation that does (never two in
one turn), until "extract all history". A rebuild discards every generation of that chat. Coverage
(compiled / pending / failed / not queued / served by an older generation) is measured per
conversation and partial coverage is shown as partial.

**D21 — One normalized-text projection (ADR 0006).** `revision_text(revision, normalizer)` stores
`clean_text()` output. Lexical recall, embedding, extraction and excerpting read it, and query text is
normalized the same way. It is derived: written at ingest, backfilled at startup, rebuildable with
`nmos-rebuild --text`. Raw `source_revision.content` is unchanged. Since `clean-v3` NMOS's own memory markup
(the packet, or a line shaped like one of its `<Fact>`, `<Claim>`, `<Thread>`, `<Excerpt>`, keyed `<Item>` lines,
spelled as the packet writes it) is dropped with its content, so a reply that echoes memory is not read as
story (K27). Bounded processing of long messages
(embedding 8 × 700 chars, extraction 6,000 target / 2,000 context chars) is recorded per revision and
visible in the Inspector.

**D22 — NMOS never ingests a chat by itself; history and rebuild are explicit (ADR 0008).** A chat
enters the ledger only when the user generates in it with the plugin on. First sight extracts the
latest `NMOS_EXTRACT_BACKFILL` turns; the rest of a chat is extracted on request
(`POST /v1/conversations/{id}/extract-history`, which also runs failed jobs again); only the failed jobs run again with
`POST /v1/conversations/{id}/retry-failed` (owner, 2026-10-14), so no turn that never failed is queued. A rebuild (`POST /v1/conversations/{id}/rebuild`)
marks the chat's active-generation extractions discarded (kept for audit) and re-extracts every turn.

**D23 — The owner can delete a conversation (ADR 0009).** `POST /v1/conversations/{id}/delete`
removes a conversation and every row recorded for it, raw revisions included, in one transaction. The
`source_revision` delete guard passes only inside that transaction and only for that conversation's
rows (migration 0012). NMOS never deletes a conversation or raw evidence on its own. If the host chat
still exists, it is synced as a new chat at the next generation.

**D24 — Request deadline 3 s by default; long chats stay plugin-only (owner, 2026-09-23).** On
PocketRisu v1.12.0 the host stalls after `getChatFromIndex` hands the plugin a copy of the whole chat
(≈0.9 s at 5k messages, ≈1.7 s at 10k; `docs/perf/scale.md`), and the V3 API has no partial read. The
plugin keeps reading the whole chat (D1, no bridge); the default `deadline_ms` is 3,000 (was 800) and
the settings panel accepts 200 ms–30 s. The deadline is a cap: short chats still finish in ≈0.2 s,
and fail open is unchanged. Chats beyond the default's reach get memory only with a higher deadline.
**Amended 2026-09-26 (owner decision on audit A-09):** the default stays 3 s. The plugin warns instead.
The status tab shows a card when the last request used 80 % of the deadline or more, or missed it, with
the value to set: 1.25× what it took, rounded up to 500 ms. After a reply that went without memory for the
deadline, the host's alert says the same, once per page (H18).

**D25 — One current holder per item (ADR 0011).** `possesses` facts are versioned per item, not per
holder: an item's latest assertion is current, earlier holders are its history. A read-side rule
outside the registry, so it needs no new extractor generation.

**D26 — Entity identity at read time (Phase 5, ADR 0012).** Each fact read resolves subject and
object mentions of the head's active assertions to entities of that conversation, without storage
or model calls: the same entity type and normalized name is one entity, the persona names are one,
and names are linked only by actual `also_called` assertions (both names in the source turn) that
are narrated or that the named character says about their own name (amended 2026-09-24). A name
linked to otherwise unconnected names is ambiguous and links nobody. Fact version keys use entity ids
where resolved, text otherwise. Ids are `uuid5(conversation, RESOLVER_VERSION, type,
name)`; a resolver change takes effect on the next read. **Amended 2026-09-24 (ADR 0023):** the
persona's name as the host reports it is a persona name for characters (`resolve-v3`). **Amended 2026-09-25
(ADRs 0024, 0025):** a reveal of a description the extraction was shown also links (`extract-v9`), the
owner's links join names (`resolve-v4`, D36), and an entity is named after its first name that is not
an unnamed character's `?` description.

**D27 — Assertion semantics (Phase 5, ADR 0013).** Each assertion has `polarity` (positive /
negative), `modality` (actual / hypothetical / dreamed / unknown; missing means unknown) and `source`
(narration / character_claim with `asserted_by`). Facts come only from actual narration; a negation
ends the current version only if it denies the same relation (same holder for an item, same object
and value otherwise) and otherwise stands as a negative fact. A character's claim (modality actual or unknown;
amended 2026-09-24) never supersedes narration and reaches the packet only as a `<Claim>` after facts. Non-actual assertions are stored and
inspectable, never injected. Rows from before `extract-v5` read as narration.

**D28 — Optional progress display on the chat screen (owner decision 2026-09-24; not a phase feature).**
A small pill at the top right of the PocketRisu page shows each main request's outcome (memory
injected / nothing relevant / skipped and why) and the open chat's background extraction and embedding
progress from `GET /v1/conversations/{id}/coverage`. Off by default (plugin arg `hud`); turning it on
in the panel asks for the host's `mainDom` permission (H16), and a denial leaves it off. The request
path only emits fire-and-forget events: the display cannot delay, change or fail a request. Coverage is
polled every 3 s only while work is pending for the chat the user is on, at most once per second for
bursts. Any drawing error stops the display for the session. No sidecar or schema change.

**D29 — Superseded projections are pruned once replaced (O5 for generations, ADR 0015).** Vectors of
an embedding projection other than the active one (`legacy:*` included) are deleted for revisions the
active projection has embedded, once it covers everything older projections had covered in that chat
and has no job pending there; the worker does it every 10 minutes. `revision_text` rows of older
normalizers go at startup once the current row exists. Superseded LLM extractions and their
assertions are never pruned. Vectors of revisions off the head stay until O5's worldline question is
decided.

**D30 — One whereabouts per item (Phase 6, ADRs 0016, 0017).** An item's holder (`possesses`), its
place (`located_in` of an item) and its end (`destroyed`, since `extract-v6`) share one version key.
The newer positive statement is current and closes the others, unless they come from the same turn;
an end also closes the holder and place of its own turn. A holder or place from a later turn than the
end is `disputed="true"` against it (the owner's Q4), with both sides in one packet line, until a new end
or a denial of the end. Negations end only what they deny (D27).

**D31 — Full-manifest observations are compacted losslessly (O5, ADR 0018).** A host observation of a
whole manifest (edit, reroll, swipe, delete) may be stored as the rows that differ from the chat's
latest base observation, only when they rebuild it exactly. Bases (a chat's first full observation, or
one differing by more than 25 %) stay full. The worker does it off the request path. Nothing else on
abandoned worldlines is removed.

**D32 — Promise threads and event salience (Phase 7, ADRs 0019, 0020).** A promise its maker says,
or the narration states (modality actual or hypothetical), opens a thread; `fulfilled` closes it as
kept and a negative `promised` as broken, stated by the narration, the maker or the recipient. A
resolution names its promise by text (equal, else a clear trigram-overlap best), never by id, so a
re-extraction of the opening turn does not orphan it. Threads are a read-time fold like facts; nothing
is stored and nothing closes on age. Open threads whose maker or recipient is mentioned (not the
persona) go in a `<Threads>` section before the facts (at most 3). Extraction is shown the chat's open
promises (`extract-v7`). A packet holds at most 3 `event` facts: major before minor or unlabeled, and a
minor event only when the query is about it. Minor events are never deleted. Since `extract-v9` an event
is major by what it changes, in action or in words (D35, ADR 0024).

**D33 — Typed participants (Phase 8, ADR 0021).** An `event`, `goal`, `knows` or `destroyed` lists the
other characters or groups its value involves as `{name, type}` (`extract-v8`, migration 0017); nothing
is inferred from text. Participants are entity mentions under `resolve-v2`, read after every subject,
object and alias name, so they never change an existing entity or the KNOWN ENTITIES hints (ADR 0012
amended). A participant named in the user's message counts like the subject for facts and claims; the
persona never counts. Participation changes no knowledge mark, version key or thread. Older rows have
no participants and recall as before. Since `extract-v9` participants are listed in KNOWN ENTITIES too
(D35, ADR 0024).

**D34 — The host's persona name is the persona (ADR 0023; owner-reported bug, not a phase feature).** The
plugin reads the personas from the host (H17) at load and every 30 s in the background, picks the chat's
bound persona or else the selected one, and sends its name with each sync. The sidecar keeps the latest
(`conversation.host_persona_name`, migration 0018). The resolver treats it like `{{user}}` for
characters, so both spellings are one entity; recall never counts any of the persona's names as a
mention, and KNOWN ENTITIES leaves the persona out. No name (refused permission, older plugin) means
the behavior before.

**D35 — Salience by change; names revealed later (ADR 0024; owner-reported, not a phase feature).**
`extract-v9` labels an event `major` when it changes the story, in action or only in words: a
confession or admission (the confession itself is an event), a secret revealed, a betrayal, a death, a
first meeting, a change in how two characters treat or address each other, a decision that changes a
relationship, goal or plan, a power first shown, or an incident others must deal with; routine scene
business is `minor`. A character shown without a name is named by a `?` description; the prompt lists
such characters as UNNAMED CHARACTERS and asks each turn whether it reveals one, and an `also_called`
from a listed description to a name in the turn is valid. KNOWN ENTITIES includes typed participants.

**D36 — The owner joins names (ADR 0025; owner request, not a phase feature).** `entity_link`
(migration 0019) records that two names of one conversation and type are the same entity. It is owner
input, kept by rebuilds and deleted with the conversation. Resolution (`resolve-v4`) joins the two
names whenever the head mentions both; a linked name is never ambiguous. The panel adds and removes
links on an entity's Inspector page; removal keeps the row (`removed_at`). The owner splits names since D54; each
join, split and undo is previewed since D65.

**D37 — How the cast stand with each other comes first (ADR 0026; owner report, not a phase feature).**
Fact ranking gives a mentioned fact a prior among equal mentions: `+0.5` for `relationship` and
`feels_toward` (`STANDING`, read side, outside the registry), `+0.3` for a `major` event; a `known_by`
name adds nothing. `STANDING` facts take the packet budget after state and before threads, and open the
`<Facts>` section. The retrieval trace records how many state items, threads and facts fit, and the
Inspector shows facts as kept/offered.

**D38 — Speech level and form of address (ADR 0028; owner report, not a phase feature).** `extract-v10`
adds `addresses` (character → character, value text, single per (subject, object)): how the subject now
speaks to and calls the object, when the target turn settles it (an agreement, a request or permission, a
first use taken up, a decided change back). It is narration although the evidence is dialogue; a reply that
only uses a speech level is not a change. `addresses` is in `STANDING` (D37).

**D39 — Accountable packets (Phase 9, ADR 0027).** Every request
records a ledger of the lines it offered its packet (state, thread, fact, claim, excerpt), each with its
provenance (assertion, revision or state key), cost, whether it was placed and why not, and the request's
inputs (query, previous reply, the ids already in the prompt, budget, recall options, generations, the
head position). Migration 0020. The packet compiler is a named policy: `packet-v1` (default,
`NMOS_PACKET_POLICY`) skips excerpts that only restate an offered fact, keeps 30 % of the budget inside
the frame for the best remaining excerpt, shortened to its best sentence or cut to fit, and caps parser
state at 40 %; `packet-v0` is the earlier compiler. Since D42 the default is `packet-v2`. A
recorded request replays **as of** its time: the head cut at its position, and only extractions, vectors
(`revision_embedding.created_at`) and owner links NMOS had by then. It reproduces the recorded ledger while
the story up to that position is unchanged, and compiles the same inputs under another policy for an
offline A/B (`tools/replay_packets.py`). Echo, report only: a placed line is echoed when the next reply
reuses a span of its content that the request did not contain. An echoed secret (`hidden_from`) is flagged.
Echo never ranks anything. Inspector "Last packet"; `GET /v1/trace/{id}/audit`, `/replay`.

**D40 — Text PostgreSQL cannot store (ADR 0029; audit A-01, not a phase feature).** A lone UTF-16 surrogate
(half an emoji) is verified in a message body's hash as sent, then stored as U+FFFD with the revision keeping
the host's hash. Other request text is made storable before validation, and every jsonb value written is
too. Host ids holding one are refused with 422. Hash format v1 and the plugin are unchanged.

**D41 — Host check without a token (ADR 0030; owner decision on audit A-05).** A sidecar with no
`NMOS_AUTH_TOKEN` answers only requests addressed to an IP address, `localhost`, a single-label name or a
name in `NMOS_ALLOWED_HOSTS`; others get 400. With a token, the token decides.

**D42 — Korean token estimate (ADR 0032; owner decision on K26).** The default packet policy is
`packet-v2`: `packet-v1` with non-ASCII characters estimated at 1.2 tokens instead of 1.5 (ASCII stays 3.5
characters a token). Each policy keeps its own rate, so a recorded request replays exactly. The default
reserve (600) is unchanged.

**D43 — Secrets (Phase 10, ADR 0033).** A secret is a valid assertion kept from someone (`limited`, non-empty
`hidden_from`, not dreamed); `hidden_from` is for what is deliberately kept from a character, not for absence.
Secrets are read, not stored (`secrets.fold`). The extraction lists open secrets whose people the turn names
(OPEN SECRETS S1…S8) and answers a numbered `secrets` check; the worker turns each finding into `learned`
(subject: who found out; value: `[turn N] <the listed line>`). A reveal ends, for that character from its turn
on, the listed turn's secret of the same head and every other secret whose head and content match; the fact
then drops the name from `hidden_from` and carries `revealed`. `learned` is never a fact itself, and deleting
the revealing turn restores the secret. Generation `extract-v12`.

**D44 — Private section (Phase 10, ADR 0034).** The request computes the scene cast (characters of the two
turns before it, characters named now, the persona; compared by entity). A limited fact or promise that someone
in the cast is not shown to know is private: the default policy `packet-v3` emits it in a `<Private>` section
with a rule in the Note (only holders know it; others do not act on it; holders keep it from those in
`hidden_from`). A mentioned fact hidden from someone in the cast ranks 0.8 higher. `packet-v2` stays available.

**D45 — Per-chat memory mode (Phase 10, ADR 0035).** Each conversation stores `memory_strict` and
`memory_narrator` (migration 0021), set from the Inspector's chat page and recorded in every trace's recall
options. A narrator keeps only public, unmarked and narrator-known lines (and a Note line saying so). Strict
replaces each private line with a content-free `<Secret holders=… not_known_by=…>` line, one per pair of sets,
outside the Private section. Excerpts that say a withheld line's content are left out.

**D46 — Budget pressure (Phase 10, ADR 0036).** A request reports the memory lines its packet left out for the
budget and the smallest budget (100s, up to `FIT_CAP`: 8,000 since ADR 0049) that holds them all; the panel's Status tab shows it with a
button that sets the plugin's budget, and reminds the user to lower the host's max context by as much (D2).
`packet-v4` (and `packet-v5`, D48) leave out a line that says an earlier line again (same head and content, or a
claim restating a fact of the same head); the ledger keeps it as `restates`.

**D47 — Plugin build check (ADR 0037, K19).** The plugin file carries a build id (a hash of the file) and sends
it with every sync. The sidecar image ships the plugin file of its commit and reads its id; `/v1/health` and the
Inspector's first page say whether the plugin in use is that build, and `GET /v1/plugin/nmos-pocketrisu.js`
serves the matching file. Shown, never enforced. Claims are marked private like facts and show their knowledge marks only in the
Private section.

**D48 — Relationship pairs, the persona's full name, what a standing fact replaced (Phase 11, ADR 0038).** A
`relationship` is versioned per pair, not per direction: each direction keeps its latest, and a symmetric one (a table
of head nouns: friends, lovers, siblings, classmates, rivals, colleagues…) replaces the other direction's either way
(K24). Feelings and speech levels stay per direction. `resolve-v5`: a character name ending with a persona name as its
own word is the persona. The default policy `packet-v5` names, on a standing fact's line, the earlier value it
replaced and its turn; since amendment 1 (K42) a version kept from someone only under the same knowledge marks
(recorded as `history_marks`; older traces replay without it).

**D49 — Open business (Phase 11, ADR 0039).** Since `extract-v13` goals, questions, threats and debts are threads
beside promises: the prompt lists OPEN THREADS, and `resolved` ends one by owner and text with an outcome (migration
0022 stores it, and a cause the story states in `because`). Rows of earlier generations keep goals as facts. Reveals are
applied before threads are folded, so a revealed goal or promise is revealed as a thread too.

**D50 — Stated causes (Phase 11, ADR 0040).** `packet-v6` (the default until D51) shows a fact's or claim's stated cause
(`; because: …`), counts its words in relevance, and ranks facts with a cause higher when the message asks why. At read
time a cause links to the event it names only when one of the same people, at most 5 turns back, clearly matches with
names left out; links show in the Inspector, never in the packet. No cause is inferred.

**D51 — One numbering for `turn` (ADR 0041; found in the Phase 11 real-host smoke).** `packet-v7` gives an excerpt's `turn`
and a state item's `as_of_turn` the turn index of their message, the number facts, claims, threads and secrets show
(ADR 0008); earlier policies show the message's position there, and their traces replay so. A message without a turn gets
no turn attribute, and excerpts stay in story order. The Inspector's state table shows the turn index. `packet-v7` is
the default (owner, 2026-09-28).

**D52 — Scene summaries (Phase 12, ADR 0042).** A `summarize` projection with its own generation, written by the
extraction model: each 8-turn window of the head, once it is 4 replied turns old, and a story so far over the current
scene summaries. A summary is keyed by its window's member revisions, so any change inside the window masks it at once;
the story is keyed by its scenes. A summary is held while it repeats a secret still kept from someone or was written
before one (it is written again).

**D53 — Story and cast (Phase 12, ADR 0043).** The default policy `packet-v8` adds `<Story>` (the story so far and
the scene summary the message is about, in at most 30 % of the budget; none for a first-person narrator) and `<Cast>`
(each scene character's place, condition, feeling toward the persona, what they carry and, when the message names
them, open goals, as their ordinary lines, not repeated elsewhere). The default memory budget is 2,000 tokens (4,000 since
D59), and
summaries are on by default.

**D54 — The owner repairs memory (Phase 13, ADR 0044).** Owner repairs are owner input (`owner_repair`), never edits of
an assertion or a message: close or reopen a thread, mark a secret found out or kept (and, from step 4, retract or
correct a fact, split two names). A repair names its target by what it says (turn, the turn's hash, kind, maker, text,
and since ADR 0044 amendment 2 its quote of the raw text), so it survives rebuilds and new extractor generations: a
generation that words the item past the text match is found by the quote, at any turn; an edit of that turn makes it
match nothing, and it is listed.
It applies from its turn, in the order repairs were made; a replay reads the repairs in force at its time.

**D55 — Canon is source (Phase 14, ADR 0045).** The card's story fields, the greeting a chat started from, its author's
note, its persona's prompt and every lorebook entry the host shows it are kept per conversation as immutable source
revisions of kind `canon`. A manifest (each key's text hash and metadata, identified by the hash of its canonical JSON,
computed alike by plugin and sidecar) is the chat's canon at one time; a request records its manifest id and the keys
its prompt held, so it replays with its own canon. The plugin reads the card off the request path (H19) and uploads
canon in the background, one upload per chat at a time. No message pipeline reads canon, and the packet is unchanged.

**D56 — Names from canon (Phase 14, ADR 0046).** A lorebook entry's keys name one thing. After the story's resolution,
when the keys the story knows all name one character (not the persona) and no key names anything else it knows, the
keys it does not know become that character's aliases (K31). Canon never joins, splits or unsettles what the story and
the owner settled. A key given to two characters is ambiguous, and the owner's split keeps an alias out. A request
records the manifest whose names it used, and its replay reads exactly that one.

**D57 — Canon facts and the owner's lock (Phase 14, ADR 0047).** A `canon` generation (its own kind; the message
extractor is unchanged) reads the canon in force with the extraction model: the card's story fields and greeting, the
note and the persona at once, a lorebook entry once a request's prompt held it, each text once, in parts. Its facts are
from before turn 0 and fold with the story's, which supersedes them from the turn it says something new; they take no
part in secrets, threads or the scene. A story statement that replaces a canon `relationship` with something else is
listed with the owner's choices (`identity` too until amendment 1: on real chats it listed the same identity in
another language). `fact_lock`, an owner repair, keeps a canon fact or a correction
current and holds off later statements, listed as conflicts. A canon fact whose text the prompt held is not sent again
(D3), unless a lock holds it against the story. A request records the canon generation it read; its replay reads it. Amended 2026-11-25 (PHASE-65, ADR 0047
amendment 3): a conditional block is judged on the text the model read (macros replaced); a persona or card text is read
under the chat's names, never `plain`, except that an earlier `plain` read of such a text without name macros keeps
serving.

**D58 — NMOS off for one chat (ADR 0048; owner request outside the Phase 14 steps).** The plugin arg
`disabled_chats` lists host chat ids NMOS is off for. Such a chat's requests pass through untouched after the chat is
read: nothing is synced, uploaded or retrieved, and no output notice is sent. What the sidecar keeps of it stays; taken
off the list, its next generation syncs as usual. It is switched from the chat input's ☰ menu or the panel's "This
chat" card; the sidebar's ☰ menu opens the panel.

**D59 — A packet that fills its budget (Phase 15, ADR 0049).** `packet-v9`, the default, is `packet-v8` whose excerpt
count, excerpt length and fact limit grow with the budget, from the request's own settings: by the budget's share of
2,000, up to 4 (facts up to 2, the added slots only for facts kept from no one). Threads, events, secrets, `<Cast>`
and `<Story>` keep their limits. At 2,000 and below
it is `packet-v8`; recall stops growing at 8,000, the panel's largest suggestion. The plugin's default budget is 4,000,
fixed; the user still lowers the host's max context by it (D2).

**D60 — NMOS Archive (Phase 16, ADR 0050).** An archive is one `.nmos.zip`: a JSON Lines file per table, rows from
PostgreSQL's `row_to_json` (exact timestamps, jsonb, reals and vectors), then a manifest with the format version, the
schema's migrations, what it holds and each file's rows and SHA-256. It always holds the ledger, canon, the owner's
input, the recorded requests and every generation; the settings without keys for the whole install; the model's work
by default; embeddings when asked; never jobs, derived text or a credential (any credential found refuses it). It is
written from one read-only snapshot by `GET /v1/archive`, `python -m nmos_sidecar.archive export` and the panel's
Export buttons, which save it as a Blob (H21). `python -m nmos_sidecar.archive restore` checks every file first, refuses
a newer archive or a conversation already present (never merged), builds the archive's schema level in a scratch
schema, loads the rows, applies the later migrations and copies them in with ids and timestamps kept (shared
sequenced ids moved past the install's own when taken, recorded requests' assertion refs with them). The panel's
**Restore from an archive…** (Phase 38, ADR 0050 amendment 2) uploads it in 8 MB chunks (H23) and runs the same
restore while NMOS runs, the shared ids' sequences held to the commit, then the startup steps for the new rows.

**D61 — Model-call usage (Phase 17, ADR 0051).** Each row a model call of the worker produced (a turn's or canon
part's extraction, a scene or story summary, an embedded chunk) keeps that call's usage as the provider reported it,
never estimated: `calls`, `ms`, the provider's `model`, and `input` / `output` / `cached` / `reasoning` tokens only
when the response carried them. NULL is a row from before migration 0027, `{"calls": 0}` a row written without a call.

**D62 — Keyword lexical recall (Phase 18, ADR 0052).** Up to four keywords of the user's message (particles and
question endings off, names kept whole, question and stop words out) are each looked up at `word_similarity ≥ 0.8`;
a keyword in more than 200 or more than half of the head messages, or not found within its 25 ms slice, is dropped;
scores sum `log(messages / matches)` under the lexical timeout. A keyword hit is its own admission signal in fusion. An excerpt only this route found is
left out when it repeats a secret still kept from someone. Recorded as `lexical_keywords`; older traces replay without it.
Amendment (Phase 41, ADR 0073, owner 2026-10-09): fresh v18 requests record
`keyword_particles`. Exact Hangul word-plus-particle matches may fill unused keyword candidate slots after the
unchanged fuzzy list; existing weights/order and the 50-candidate cap remain. Combined fuzzy/exact breadth gates
only additions. Lookups share the original route deadline and each word's remaining 25 ms; canceled or broad
legacy lookups cannot authorize additions. Supplement admission also checks elapsed time after the SQL returns,
so late backend cancellation cannot admit an over-budget addition; this does not promise immediate server interruption.
A full old list adds nothing. Missing historical flags replay off,
and v16/v17 bypass the correction. This changes no stored generation, canonical fact or packet activation floor.

**D63 — Excerpts that fill their length (Phase 18, ADR 0053).** `packet-v10` (the default until Phase 27 made `packet-v11`
the default, D72; available as `NMOS_PACKET_POLICY=packet-v10`) is `packet-v9` whose excerpt
starts from the sentence holding most of the message's keywords (then most shared trigrams) and adds whole neighbouring
sentences, after then before, within `excerpt_chars` and at most four sentences; a longer best sentence is cut there.
`packet-v9` stays for replays.

**D64 — `extract-v14` (Phase 19, ADR 0054).** A turn extraction's context messages are cut at 1,000 characters (the
target's at 6,000), its prompt's examples are synthetic, and a row whose quote (12 characters or more) is not in its
target turn as the model saw it (`threads.similarity < 0.7`, each member cut at 6,000 characters) is stored `pending`, "evidence not in the
turn". Only the turn worker applies that check; canon reads do not. Reveals are unchanged.

**D65 — A join, a split or an undo is shown before it is made (Phase 20, ADR 0055).** A preview is the difference of
two reads of the head, as it is and as it would be (`memory_view(what_if=…)`): the entities of the two names, facts
that stop or start being current and which version takes their place, relations and promises of a character with
itself, threads, secrets, repairs whose match changes, conflicts, the persona and canon aliases. Nothing is written.
Its fingerprint (head, links and repairs in force, generations, the difference) makes the action answer 409 when
memory changed since; without one the action works as before. The story's order still decides between two facts.
After an undo the owner may re-extract the turns extracted while the join held (their hints list the two names as
one): those turns' extractions are discarded and just they are queued, at the owner's provider's cost. A worker
whose job a rebuild or a re-extraction made obsolete while the model answered stores nothing.

**D66 — A reveal check instead of a re-extraction (Phase 22, ADR 0057).** "Extract all history" keeps the extraction
of a turn extracted before an earlier turn's secret (K29) and asks a reveal check: the turn's OPEN SECRETS, CONTEXT and
TARGET, answered with `secrets` only. A check is an extraction of a `reveal` generation under the window
`reveal:<turn hash>`, naming the extraction it checked; its `learned` rows are served with the turn while that
extraction serves it, and read as of an earlier request only when made by then. Nothing is discarded.

**D67 — How it started, when the message asks (Phase 21, ADR 0056).** A user message with a first cue (처음, 최초, 예전,
옛날, 원래, 초반, 첫 before a space, 번 or 째; "at first", "originally", …) ranks events mentioned first, then oldest,
before salience and score, keeps `minor` events without the lexical bar, breaks equal scores toward the older fact, and
keeps a standing fact whose source is in context when an earlier version the prompt does not hold (stated before the
window, or canon not held) has its marks. Recorded as `first_cue`; older traces replay without it.

**D68 — A name as the story says it (Phase 24, ADR 0058).** For one request, a character's three-syllable Hangul name
with a common family name also goes by its given name (백이안 → 이안), and a character held under a Latin name by a
Hangul word of the message that spells it on a fixed key (하진 → Hajin); not the persona, and not a name another entity
holds or two characters would share. They count wherever the message is matched against names: fact selection and a
secret's holder addressed (D19), threads, the scene's cast (D44), whose groups then put the characters the message
names first. Nothing is stored. Recorded as `name_variants`; older traces replay without it.

**D69 — A role between two people is its own fact (Phase 25, ADR 0059).** `extract-v15` adds `role_toward`
(character → character, a value, one current value per direction: tenant of, employer of, teacher of…) and narrows
`relationship` to personal ties (kin, romance, rivalry, friendship); a pair keeps its relationship and each
direction's role at once, and a turn that says where someone lives and the role they hold there gives `located_in`
and `role_toward` both. `role_toward` is a standing fact (ADR 0026): it ranks, leads and carries its history as
`relationship`, `feels_toward` and `addresses` do, canon may state it, and the Inspector's pair view shows it per
direction. Older generations have no such rows, so recorded requests replay as they were.

**D70 — The query embedded while recall reads (ADR 0061; K34, AGE-24).** Recall starts the query's embedding call on
its own thread before lexical recall, reads the state, the facts, threads, cast and summaries meanwhile (none of them
needs the vector), and then waits for the embedding at most `embed_timeout_ms` (300): a request never waits longer for
the embedding than when the call alone had that time, and the embedder gets the reads' time as well (≈100–300 ms at
the measured sizes, where the owner's production fallbacks sat: 70 % of recalls, behind a proxy at 280–450 ms). A
request that now has vectors pays the vector search and a fuller packet, as a request with vectors always did.
The query HTTP task has a total deadline of twice the timeout (AGE-74 correction, 2026-10-09). DNS/transport cleanup
can outlive cancellation; eight shared non-waiting slots bound outstanding query/prefetch calls including cleanup,
and saturation falls back to lexical search. Worker batch transport is unchanged. A sync
whose bodies carry the chat's newest user message starts that text's embedding at once, and the retrieve that follows
(the plugin sends the same text as its query) takes it instead of calling: the embedder has the sync's time too, and
such a request waits for nothing. Fail-open to lexical, the vector search, the fusion and the ranking are as before;
the trace records the embedder's time (`embed`), the wait after the reads (`embed_wait`), the search (`vector`) and,
for a prefetched embedding, how long before recall its call began (`embed_lead`). Nothing recorded changes: requests
replay as they were.
**Amended by PHASE-60 S5 (ADR 0084):** under `packet-v20` (`SEM_QUERY_POLICIES`) a message shorter than 40 normalized
characters with a previous reply is embedded as that reply's last 400 characters, a line break and the message
(`retrieval.sem_query`). Only the embedding input changes: lexical and keyword recall, fact relevance and excerpt
anchors read the message alone. Recorded as `recall_options.sem_query` (null when it did not apply); a replay embeds
the recorded text, and a trace without the key replays with it off. The sync-time prefetch builds the same text with
the same function from the reply before the synced message (the sync's bodies, else the head's stored revision), so a
short message still finds its embedding waiting; a failed lookup or a mismatch costs only the bounded wait above.

**D71 — The chunk cap, a setting of the projection (ADR 0062; K13, AGE-24).** A message is embedded in chunks of 700
normalized characters from its start, at most `NMOS_EMBED_MAX_CHUNKS` of them (default 8: 5,600 characters, the cap
since #13; a value under 1 is refused at startup). The cap is in the projection key (D20), so each projection embeds by
its own cap (`process_embed` reads it from the generation's spec) and a changed cap is a new projection that re-embeds
every chat once (ADR 0014 item 5, K18); the default is the cap it was, with the key it had, so an upgrade re-embeds
nothing. The search is unchanged: the best chunk per message, one candidate per message. Measured on the M0 v2 main
chat's evaluation copy (Codex, on #242): its messages normalize to at most 5,481 characters, within the default, and a
cap of 24 compiles the same 40 packets — the first draft's claim that the cap cut the owner's replies in half was wrong.

**D72 — The excerpt lands on the answer (`packet-v11`; ADR 0063; Phase 27, AGE-31).** Under `packet-v11` a message
found by a word route whose vector similarity is at or above `vector_min_sim` is excerpted from the chunk the vector
found, as a vector-only hit always was (a word hit below the bar, or without a vector, from the whole message), and a
why or contents question (`facts.WHY`, `packet.CONTENTS`) grows its excerpt by whole sentences to 320 characters with no
sentence cap; other questions keep `packet-v10`'s four. The tie-break anchor between sentences holding the same keywords
is the recorded recall option `excerpt_anchor`: `packet-v11` reads "keywords" (the question's keywords, or the question
itself when it has none; the default, decided by measurement in Phase 27 step 2 — with "focus" the forbidden total rose
93 → 96, with "keywords" it fell to 87), `packet-v10` always anchors on "focus" (the question and the previous reply);
`tools/eval_rp.py --anchor` replays either. **`packet-v11` is the default since Phase 27 step 3** (the M0 main cases
that need memory 16 → 19 of 23, `docs/perf/answer-span.md`; the owner allowed the smaller packets it makes, Q5);
`packet-v10` stays available as `NMOS_PACKET_POLICY=packet-v10`. Recorded requests replay as they were.

**D73 — `extract-v16`: a role ended as listed, and a name said two ways (ADR 0064; Phase 28, AGE-24).**
**The default since 2026-10-04** (the owner's decision, Phase 28 step 3); `NMOS_EXTRACT_COMPILER=extract-v15` selects
the earlier extractor with its key unchanged. Off by default until then.
The extractor is shown the roles in force (CURRENT ROLES, as open promises, threads and secrets
are shown, numbered) and names the one a turn ends; the worker writes the ending with the listed value, so ADR 0013's
value match closes exactly that role (asking the model to copy the value failed on the owner's run); and it is
asked for `also_called` when a turn writes a character in full and by part of the name, unless the two could be
different people, the part checked on its own in the turn (ADR 0012's provenance and ambiguity rule unchanged). A
read-side join of a name and its given name was measured first and withdrawn: the stored assertions never named the
split pairs in the same turn.
Measured since (ADR 0064 items 2 and 4, Phase 29): a listed ending is applied only after one more call about that role
says it ended, and an ending marked planned, or the other direction of one, is held for the owner, never applied; an
alias whose two names are both in the turn is asked once more about those two names and held unless confirmed, a
held one listed for the owner's link; under `extract-v16` a Hangul or Latin name counts as written only as a word of
its own. Every held ending and alias is a pending row with its record; the owner sees them under "Needs attention".

**D74 — A chat seen for the first time is extracted in story order (ADR 0065; Phase 30, NMO-36).** A first sight's
window (the latest `NMOS_EXTRACT_BACKFILL` turns) is claimed oldest first, so every turn's lists (KNOWN ENTITIES, OPEN
PROMISES, OPEN SECRETS, OPEN THREADS, and `extract-v16`'s CURRENT ROLES and NAME PAIRS) come from the turns before it, as
in a generation's backfill; newest first, each turn was extracted before every turn before it and its lists were empty.
A live turn of a chat whose first-sight window is still queued or running waits behind it; a dead job holds nothing.
Every generation; no prompt, generation key or migration changes.

**D75 — Recall that knows what changed (`packet-v12`; ADR 0066; Phase 31, AGE-24).** Under `packet-v12` an excerpt
older than a fact's current version that repeats a value the fact replaced and not the current one is left out (the
selected facts by reused spans; the standing facts and places the question names also by marks: a place's word for a
"where" question, a quoted form of address for a "what is … called" question; not a fact whose old value the question
names), an ended role leaves the facts unless no fact about the same two is current and the question names both, and the
excerpt's anchor breaks a tie on the question's one-character words. A question with a history cue (`HISTORY_CUE`:
`FIRST_CUE` plus 전에, 이전, 첫날, before, used to, previously) keeps the old excerpts and the ended roles. The default
since 2026-10-05 (owner, on the second reduced live gate); `NMOS_PACKET_POLICY=packet-v11` keeps the previous packet.

**D76 — What was said, and the turns not extracted yet (`packet-v13`; ADR 0067; Phase 33, AGE-10).** A message with a
speech cue (말했, 뭐라고, 대사, "said", a phrase in quotes; a question about what someone is called only with a history
cue) takes the quote route: the quoted speech of the chat's messages searched lexically with the question's words,
narrowed by a turn number, a first cue or the first meeting of the characters it names, and at most two `<Quote>`
lines with the words verbatim, placed before the excerpts. A speaker is written only when the quote's own sentence
names one; a quote only the route found passes the secret test. An excerpt from a turn the active extractor has not
extracted is raw evidence: never dropped for restating a fact, and it may take one more slot.

**D77 — What a line is for (`packet-v14`; ADR 0068; Phase 34, AGE-10).** Every ledger line is required (state, cast, the
story so far, knowledge boundaries, what the question names, quotes, the first excerpt), supportive or risky (a disputed
line). A supportive line placed in each of the last `rest_after` requests (recorded, `NMOS_REST_AFTER`, 2) that none of
their replies echoed rests for the next two requests; the question naming it, its own words finding it or a history cue
keeps it. Nothing is stored: the requests are the recorded traces. An excerpt after the first needs half the best fused
score or a word hit. **The default on 2026-10-08** (owner, on a live run on a real chat: no repetition felt; repeated
lines' echo 0.29 → 0.39), then in the default through `packet-v15` (D78).

**D78 — The anchor is what was asked (`packet-v15`; ADR 0069; Phase 35, AGE-10).** Under `packet-v15` a history cue's
keywords (처음, 첫날, 예전) break ties in `grown_excerpt` instead of picking its best sentence, and a first cue adds 처음 and 첫
to the tie words; one-syllable function words (`retrieval.FUNCTION_SYLLABLES`) break no tie; and a word hit's vector
chunk gives way to the whole message when the question names a one-syllable noun and the message holds a sentence with
more of those nouns, then of the anchor words (`packet.anchor_rank`). The keyword route and lexical recall are
unchanged. **The default on 2026-10-08** (the owner, on the zero-call replay: the bench 289 of 314 against 286, no
case lost), then in the default through `packet-v16` (D79).

**D79 — A name is not a question about everything (`packet-v16`; ADR 0070; Phase 36, AGE-10).** Under `packet-v16` a
message that holds a character's name makes required (never resting, ADR 0068) only that character's facts about how it
stands now (`facts.NOW`) or with another (`facts.STANDING`), its knowledge boundaries, and any of its facts the
message's words point at (overlap at least `LEXICAL_BAR`); its other facts, a past event or a trait named by the name
alone, are supportive and rest when unused, unless the question asks for its kind (`facts.ASKS`) or the fact holds one
of the question's one-syllable nouns. Ranking and limits are unchanged. **The default since 2026-10-08** (the owner, on
the zero-call replay: the bench as `packet-v15`, required lines 76 % → 67 % on the trial chat);
`NMOS_PACKET_POLICY=packet-v15` keeps the previous packet.

**D80 — A status window over time (`packet-v17`, status flags; ADR 0071; Phase 39, AGE-43).** One history of every
status key along the head (`state.history`) feeds the Inspector's lanes, a `<StateHistory>` line under `packet-v17`
for a message that names a key and asks how it changed (required; not the default), and the flags of a rule's `watch`
keys: a change the reply's prose does not name goes to "Needs attention", deterministic, nothing stored; a dismissal is
an owner repair (`state_dismiss`, migration 0029). The replay of the trial install's requests changes none.

**D81 — Questions about the persona (`packet-v18`; ADR 0072; Phase 40, AGE-18).** Explicit third-person questions
can rank at most two matching facts or attributed claims about the resolved persona between a current-query
name mention and a previous-reply name mention,
sharing the cap across both. An unshared Korean given name is accepted only on this route; ordinary persona
mentions, entity resolution and Cast are unchanged. Existing history, event, rest, mode and token rules apply.
The owner includes the correction in `0.4.0`; zero-call replay found no new majority failure (see `docs/perf/phase40-persona-questions.md`). The reduced live host answer check is open. After actual-model synthetic verification and
6113 trial deployment, the owner selected `packet-v18` as the 0.4.0 default (2026-10-09).

**D82 — Old dialogue left out in steps (ADR 0083; PHASE-60 S1).** Opt-in: with the plugin's `trim_old_turns` on (off by
default; `keep_recent_turns` 20, 4–200) `/v1/retrieve` carries `trim: {keep_recent_turns, step}`, `step` equal to
`keep_recent_turns`; a request without it is served as before. The sidecar decides the boundary (its turn numbers,
ADR 0008): `cut = floor((now − keep_recent_turns) / step) × step`, lowered to the first turn of the prompt's window
not covered — served by an extraction (D20) and held by a current scene summary not held back for a secret (D52) —
rounded down to a multiple of `step`, so the boundary moves only in whole steps. No boundary (`keep_from_id: null`
with a `reason`: `short`, `uncovered`, `no_summaries`, `stale`, `empty_packet`) when nothing can be cut, the head is
stale, summaries are off or the packet is empty. The cut messages leave the in-context set before recall (D3);
`recall_options.trim` records the decision. Every answer carries `coverage` (`recorded_through_turn`,
`covered_through_turn`). The plugin applies the boundary to a copy in `beforeRequest`, never to the host chat, and
drops nothing (reason `format`) unless every dropped prompt message is `user` or `assistant`, carries exactly one host
message and lies in one contiguous run before the boundary and before the latest user turn; no answer, a stale one,
an empty packet or any error drops nothing. The Status tab and the HUD say what was left out and the tokens saved.

**D83 — Where memory goes (ADR 0083; PHASE-60 S2.2–S2.3).** `[NMOS.memory]` in any outgoing message (string content or
text parts) is replaced at its first occurrence by the packet (by nothing when there is none) and removed everywhere
else, on every path out of `beforeRequest` (an auxiliary request, the plugin or the chat off, the turn not found, a
failure); with a marker the default placement is not used. `end` inserts before the trailing run of `assistant`
messages. When the packet lands after the latest user turn (`end`, or a marker after it: `landsAfterUserTurn`),
`GUARD_LINE` follows `</NarrativeMemory>` in the same message and the plugin asks for `reservedMemoryTokens` − 40, so
the reserve bounds the whole message (D2). Idempotence is by content, not role (H2): a prompt that already holds the
packet text being placed is returned as it is, and a prompt the plugin returned (the last 4, for 2 minutes) is
returned unchanged when it comes back. Canon observation, the turn index and the in-context ids read the prompt as the
host sent it; a marker in canon text is stored as written and `clean-v3` is unchanged, so nothing is re-derived.

**D84 — A packet that knows where it stands (`packet-v20`; ADR 0082; PHASE-60 S2.1, S3, S4).** `packet-v19` plus four
reads of what is stored, no model call, each gated on a policy set that holds `packet-v20` alone. *How far memory has
got:* when the head has a replied turn after the latest one an extraction serves, the Note says memory is recorded
through turn N and the chat is right where a newer message disagrees (or that nothing is recorded yet); recorded as
`recall_options.coverage`. *Gone:* a character (not the persona, not one the owner left out) whose current, narrated,
positive, undisputed `has_status` holds a word of `gone.py`'s lists as a whole word, with no recovered word, negation
or near miss, or whose `located_in` is a whole name on its short list of non-places, has that status line marked
`gone="true"`, `required`, first in its `<Cast>` group or first in `<Facts>` (`<Private>` when private; strict and
narrator modes apply as to any fact, D44, D45), at most 8, newest first, within 10 % of the budget, whether or not the
turn names it. Canon and carried rows never pin; a character a row of a later turn in
the scene window names is not pinned. The rule errs toward not pinning; the lists are policy constants, so a change is
a new policy. *Return gap:* a `<Cast>` character whose current run (appearances at most 5 turns apart, begun at most 5
turns ago) follows at least 40 served turns without it carries `back_after="~N turns"`; turns no extraction serves are
not counted (invariant 4). *Settled:* up to 3 threads closed in the last 15 turns whose maker or recipient is in the
scene or named, broken, failed and abandoned before the rest, then newest, follow the open threads as `<Thread
status="…" … closed_turn="…">`, `supportive`, not counted in `threads_limit` (none when it is 0). Each mark is explained in the Note only when a
kept line uses it. Not the default; older policies compile as before, fresh or replayed (D39).

**D85 — The owner pins a character (ADR 0087; PHASE-60 S8).** `owner_repair` kind `entity_pin` (migration `0038` widens
the kind check) names a character by name and type as `entity_exclude` names its target, resolved on every read, so a
name the story joins to it follows and a split one does not; `entity_exclude` wins over a pin. Removed like any
repair, kept by rebuilds, archived, deleted with the chat. A chat's entities and a person's sheet name the pin. The
setting `pin_at_mentions` (`NMOS_PIN_AT_MENTIONS`; off when unset, empty or `0`; a runtime setting that queues nothing)
enables `@name` pinning for one request. Under `packet-v20` (`PIN_POLICIES`), `pinned_characters` collects the
request's pins in order, never the persona and never an excluded character: first `@name` matches in the user's message
(only with `pin_at_mentions` on: `@` at the start of a word followed by a character's normalized name or alias, up to
two words, with at most one trailing Korean particle; an `@` inside a word, an unknown name or a name two characters
share does nothing), then the owner's pins, newest first. Each pinned character joins the scene's cast after everyone
already in it, so knowledge marks, `<Private>`, strict and narrator modes, and scene summaries treat it as present. Its
own chat's `NOW` and `STANDING` facts rank as if the message named it and are marked `required` (facts named only by a
pin do not count as a message name for `packet-v19`'s unrelated-question fill); its other facts rank as before. After
the cast's own 4 groups, each pinned character without one gets a `<Cast>` group of the same shape, at most 3 beyond
the 4 (`PIN_EXTRA`), in pin order, from its own chat's rows only (carried rows never fill a pinned group or become
required by a pin); a pinned gone character keeps its `gone="true"` line first in that group. A live request with pins
records each resolved character's name and source (`at` / `owner`) as `recall_options.pins`; its replay reads that
record instead of the message or the pins in force (a trace without it replays with none). Older policies ignore pins
and `@name`.

**D86 — `extract-v19`: when it happened and who was told (ADR 0086; PHASE-60 S7, S8).** Selectable
(`NMOS_EXTRACT_COMPILER=extract-v19`, not the default; `extract-v16` stays the default). Built on `extract-v18`
(keeping roles, name pairs and `feeling`), adding `when_happened`, `story_clock` and `told`.
`when_happened` (`assertion.when_happened`, migration `0037`, 1–80 characters) is kept on `event` and `promised` only
when the target turn places it at another time than the turn itself — a short phrase in the story's own words, resolved
against the story clock when one is shown, never a computed timestamp and never used to order rows; dropped on any
other predicate or compiler, and carried through `ASSERTION_COLUMNS`, fact reads and archives.
`story_clock` (`extraction.story_clock`, migration `0037`) records the literal `date` / `time` status-window values as
of the target turn (single `rules_version`, latest position per category, at most 80 characters each), shown as one
prompt line (`CLOCK_LINE`) and recorded on the extraction like the hints (D7), never part of validity.
`told` (character → character, multi, with typed participants `with` via `EXTENSION_PARTICIPANTS`) records that a
character passed on something that matters later which the hearer did not have; it requires a quote (`evidence`), else
is parked `pending`. It stays outside `REGISTRY` in `predicates.EXTENSIONS["extract-v19"]` (D6 amended), hashed with
`EXTENSION_PARTICIPANTS`, `CLOCK_LINE` and the length caps into `extract-v19`'s `prompt` fingerprint so the keys of
`extract-v15`–`extract-v18` and of canon, summarize, reveal and embed do not move. `told` changes no knowledge marks by
itself; `memory_view` keeps reading `REGISTRY` alone, while `facts.served_told` reads served `told` rows of compilers
whose extension declares it, oldest first, as of `upto` / `known_at` (`packet-v20`'s `happened` and `told` lines:
D87). `extract-v19` joins `generations.ADDS` with `extract-v16` and `extract-v18`, so switching among them
with the same model and endpoint is classified `adds` in both directions and queues no already-served turns.
`fact_restore` keeps `when_happened` beside `repairs.RESTORED` (the dropped-facts listing reads it; it does not read
`feeling`, so a restored `feels_toward` loses its feeling detail, since Phase 58). Known limits: a `told` row kept from someone keeps its knowledge marks but is in `secrets.NOT_SECRETS`, so it
is not tracked as a secret and no reveal check ends it. No owner repair retracts a `told` row: it is never a fact of the
view. `told` rows take no part in entity resolution, so a teller or hearer named only in them has no entity.

**D87 — When it happened, and who told whom, in the packet (`packet-v20`; ADR 0086; PHASE-60 S7, S8).** Under
`packet-v20` (`HAPPENED_POLICIES`) a line whose assertion has a `when_happened` (D86) carries `happened="…"` right after
its `turn`: fact lines (in `<Facts>`, `<Private>`, a `<Cast>` group and a gone line), thread lines (a cast group's goals
included), settled lines and told lines; claim lines carry none. The Note then says `happened` is when it happened in
the story and `turn` when it was told. Under `TOLD_POLICIES`, with `facts_limit` above 0, at most 2 (`TOLD_MAX`) served
`told` rows (`facts.served_told`, D86) follow the facts as `<Fact kind="told">` lines (teller told hearer: what, and whom
it is about when it names them), only when the teller or the hearer (never the persona) is in the scene or named in the
user's message under any name they go by: ranked as facts are, then the scene's newest; not said again while its
message is in the prompt (D3); a tired one rests (D77's rest key); never a carried row. A line whose value or quote says a
secret still kept from someone is left out as a keyword-only excerpt is (D62, a hidden `secret_gate` entry), and the
next may take its place; the rest is any fact line's: private in its scene, strict and narrator modes (D44, D45). The
Note says a told Fact does not show that the hearer believed it. Older policies emit neither. Known limit: the pages that draw told chains (the person sheet, the Inspector's
character page, the memory map) show them as they show facts, the owner's view, not filtered by strict or narrator
mode; only a row whose teller or hearer the owner left out is dropped.

**D88 — An optional reranker (ADR 0084; PHASE-60 S5; amends `AGENTS.md §4` "Models").** Opt-in: a reranker exists only
when both `NMOS_RERANK_URL` and `NMOS_RERANK_MODEL` are set (`runtime.reranker`; also settable in the panel); otherwise
no code path calls one. Not tied to a policy: a live request, after the fusion and with the in-context messages left
out, sends the user's message (not `sem_query`) and the top 30 (`rerank.MAX_CANDIDATES`) eligible candidates, each cut
to 1,000 characters, in one `POST <url>/rerank` over the sidecar's `httpx` client, and the scores reorder those 30
ahead of the rest; at most one call per live request (the trim's empty-packet re-read, D82, calls none). The call is
bounded by its own timeout on the sidecar (`NMOS_RERANK_TIMEOUT_MS`, 600 by default, 50–5,000): `/v1/retrieve` carries
no remaining deadline, and the plugin's deadline (3,000 ms by default) still fails the whole request open on its side,
so `NMOS_EMBED_TIMEOUT_MS` + `NMOS_RERANK_TIMEOUT_MS` should stay well under it. A timeout, an error or a malformed
answer (not every index exactly once with a finite score) leaves the fused order. With a reranker configured the
trace records `rerank_used`, `rerank_ms` and each scored candidate's `rerank`; a replay never calls one and reapplies
the recorded scores to the same candidates (a request whose call failed replays in fused order; a replay with a
replaced query applies none). The key is a credential (`runtime.SECRET`): bound to its endpoint's host, never in a
trace, a log or an archive (an archive holding it is refused, D60); `/v1/health` says only whether one is configured.
Only the `standard` format exists (`NMOS_RERANK_FORMAT`: `{model, query, documents, top_n}`, answered by `results[]` or
`data[]` of `{index, relevance_score}`); no other is built. It derives nothing stored and is part of no generation key.

**D89 — A chat that carries another chat's memory (`conversation_carry`; ADR 0085; PHASE-60 S6).** Owner input
(migration `0036`): one link in force per target (a partial unique index), never a chat to itself, a source's own link
not followed. *The frozen reading:* at link time the source is read once, as of its head and a cutoff position (the
head's end, or the last message of a turn the owner chose on the current head), with the readers a request uses, and
the rows are stored with the link as `snapshot`: names and types, never entity ids (the source's persona written as
the persona), no verbatim text (no `evidence`), each row's provenance in `from` (source conversation, assertion,
revision, generation, repair, source turn). Nothing is re-read; the owner links again for a newer reading (the old link
gets `removed_at`). More than 2,000 rows (`carry.MAX_ROWS`) is refused with 422 `too_many_rows: rows=<N> max=<M> (…)`;
`POST …/carry` with the preview's fingerprint (`expect`) answers 409 with a fresh preview when the source's reading
changed since. *Only `packet-v20` reads a link* (`CARRY_POLICIES`), resolving carried rows by name in the target (D26).
`continue`: facts, aliases, open threads and the story so far fold after the target's canon and before turn 0
(`CARRY_BASE`, turn -1, negative ids), resolved after the target's own rows, and the target's story supersedes them as
it does canon (D57); lines say `source="carried"` and the earlier story is a `<Summary scope="earlier chat">`; they
take no part in the scene cast, gone pins, the return gap, settled lines, told lines, pins or secrets. `regression`:
rows are listed apart, never in current facts, cast, gone pins or open threads, and at most 6 (`REGRESSION_MAX`) are
offered as `timeline="previous"` lines in a `<Regression remembered_by="…">` group, private, through strict and narrator
modes (D44, D45); a row's rememberers are all the named for a public row, the named in `known_by` for a limited one,
otherwise only the named the row involves, always minus `hidden_from`, and a row with none is not carried. A request
records the link it read as `recall_options.carry` (link, source, commit, position, mode, names); its replay reads that
link, removed since or not. Both foreign keys are `ON DELETE CASCADE` and deleting either chat counts the links
(`carry_links`); an archive holds a link only when both chats are in it (`carry_left_out` in the manifest). The
read-only lists and screens show carried rows (`view_of(carried=True)`: `/facts`, `/entities`, `/threads`, `/secrets`,
the panel's memory document and person sheet, which also get the link's `carry` block); previews, repairs, the
author's note, dropped facts, endings, the Inspector's pages, the hub and the map read the chat alone. Known limits: a
source's very last reply may not be in a reading, since it is extracted only once the user continues from it (D5).
Closed regression threads are stored but never offered. A restore that renumbers assertions moves the snapshot's
`from.assertion` but not a recorded trace line's `ref.source_assertion`. Amended 2026-11-23 (the phase's
review): a regression link's lines follow the target's `memory` exclusions as its own rows do (an excluded character
is no rememberer, and a line left with none is dropped); a carried persona marker reads as the target's host persona
name (ADR 0023) in every line, screen and link preview, the stored snapshot unchanged; a replaced link's `removed_at`
is its successor's `created_at`, read under the locks.

**D90 — What the model request carries (`llm_extra_body`, `llm_no_temperature`; ADR 0088; PHASE-61).** One JSON object
the owner writes is merged at the top level into every chat-completions request made with the extraction model
(extraction and its confirmations, reveal checks, summaries, canon facts, the author's-note calls, the settings test); a
switch sends the request without a `temperature`, the only alternative to 0. The body may not name the request's own
fields, hold a credential-like or non-ASCII key name or one of the install's own credentials, exceed 2,048 bytes, or
hold a number PostgreSQL would store in another form. A generation's spec gains `request` (the body, keys sorted) only
when the body is not empty and says `temperature: null` only when none is sent, so with both at their defaults every key
is the key before; `request` and `temperature` are model fields of `generations.classify`, so a change of either alone
is a `model` change (the owner's choice, carry on by default, PHASE-57 A3). A provider that rejects the body fails the
job; it is never sent again without it. An image from before this decision reads such a spec as a version change, so a
rollback clears both settings first.

**D91 — A log of model calls, and what the worker is doing (`model_call`, migration `0039`; ADR 0089; PHASE-61 S5–S6).**
Every model call made outside the request path (the worker's extraction, reveal checks, summaries, canon facts and
embeddings; the sidecar's author's-note calls and settings tests) writes one row: when, what kind, the chat and job when
known, the generation, the model, the endpoint without userinfo or query, the outcome (`ok`, `http`, `timeout`,
`transport`, `bad_reply`), the HTTP status, the time taken, the usage the provider reported and, for a failure, the
first 300 characters of the provider's error, with any of the install's own keys replaced. Never a prompt or a reply;
the one free text is the provider's own error message, which may quote the request as a job's `last_error` already does.
The row is written on its own connection outside the job's transaction, with two-second bounds, and a failure to write
it is logged and dropped: the log cannot fail a call, and cannot hold one beyond those bounds. `/v1/retrieve` writes
none. Rows are operational data: kept as long as traces, never archived, deleted with their chat. `GET
/v1/worker/status` answers with counts of the job table (waiting by kind, running, being tried again, given up on,
finished lately, the newest error) and the last hour of the log; a queued job of a generation its kind has left is
counted apart, since no worker claims it. `GET /v1/worker/calls` and the Inspector's Model calls page list recent rows.
All of it is read-only and none of it changes a key, a packet or a setting.

**D92 — The cap on each message the extraction model is shown is a setting (`NMOS_EXTRACT_TARGET_CHARS`; ADR 0090;
PHASE-62).** Extraction, the reveal check and scene summaries showed the model the first 6,000 normalized characters of
each message (K13); on the owner's production about half of the text of long replies lay past it. The cap is now the
setting's value (default 6,000, up to 36,000), the `target_chars` and `message_chars` their generations' specs already
held: at the default every key, prompt and row is unchanged, and another value is another extract, reveal and
summarize generation. A job reads at its generation's cap (`extraction.target_cap`), so the evidence check looks in
what the model was shown; a row records its cap only when it is not 6,000. A change of the cap alone is classified
`reads` and queues what a carry-on queues (D20, ADR 0078): what was read keeps serving, what comes due is read at the
new cap. "Read the cut turns again" queues, per chat and on request, one extraction for each turn an earlier cap cut
(and the scene summaries cut the same way, when asked), after showing their count and a range of input tokens; the
earlier readings stay. An image without this must not meet a database left at another cap: the cap is set back first.

**D93 — Conditional forms of address (`extract-v20`, `canon-v2`; ADR 0091; PHASE-64).** Selectable
(`NMOS_EXTRACT_COMPILER=extract-v20`, not the default; `extract-v16` stays the code default). Built on `extract-v19`
with `address_condition` (`assertion.address_condition jsonb`, migration `0040`, null for unconditional addresses, every
other predicate and all earlier generations): `{"scope": "public|private|situational|all", "when": "<phrase or null>"}`
(`when` up to 60 characters in the chat's language, required for `situational`, null for `all`). Covers both agreed
contextual rules (public vs private, missions, disguise) and explicitly stated/narrated recurring habits (e.g.
involuntarily slipping back into a given name when flustered or overcome by emotion), while still rejecting accidental
one-off slips (ADR 0028). When `extract-v20` is selected, `canonfacts.generation` activates `canon-v2` so character
cards, lorebooks, notes and personas extract conditional forms of address too (`scope="all"` in canon normalizes to
null); all other compilers keep `canon-v1` and its pinned key unchanged. `extract-v20` keeps `REGISTRY` unchanged and
joins `generations.ADDS`, so switching among `extract-v16`, `extract-v18`, `extract-v19` and `extract-v20` queues no
already-served turns. Each conditional address is its own assertion row (preserving Invariants 6, 7 and 10) and folds
per slot at read time (`facts._address_versions`): `default`, `public`, `private`, and each normalized `situational`
phrase hold independent current values and per-slot histories; once both `public` and `private` are active, a stale
earlier `default` is retired into history; `scope="all"` closes all earlier active slots into one unconditional form;
negations and `fact_lock` apply per slot (`all` still conflicts with any locked slot); `retrieval.replaced_marks` does
not mark a superseded address form obsolete while another active conditional slot for the same pair still uses it;
packet selection caps `situational` rows at 3 newest per direction (`SITUATIONAL_ADDRESS_MAX`). Active conditional rows
format in `fact_text` and `secret_text` as `<subject> addresses <object> [<label>]: <value>` so the response model
judges the situation while historical traces (all null) replay byte-identically under every packet policy.

**D94 — `packet-v21` (ADR 0092; PHASE-65 S10).** Opt-in (`NMOS_PACKET_POLICY=packet-v21`; `packet-v19` stays the
default). `packet-v20` plus what only it does, each addition gated on `V21_POLICIES`, so `packet-v20` and older compile
and gather as before. Every excerpt and quote that repeats a secret kept from someone present is fenced in `<Private>`
(normal mode) or withheld (strict, narrator); `<State>` / `<StateHistory>` values of 3 letters or more that repeat one
are withheld; a public line drops a `because`, `disputed_by`, `before` or `first` clause that repeats one; a settled
thread reads under its closing's marks; strict mode keeps an unspoken `feels_toward` readable in `<Private>`. `<Cast>`
reads 4 turns and may hold peer feelings, forms of address (a pair's slots together or not at all) and a persona group,
placed after every `packet-v20` line within 15 % of the budget. Feeling detail on `feels_toward` lines; titles the
persona uses as aliases; the quote route only beside a question or recall cue outside the quotes; v21 keywords; the
reranker on `sem_query` and the matched chunk, its order deciding the floor; gone read from presence rows only; rerolls
counted once for rest and standing facts never resting (`audit.replay` alike); a replaced value drops only an excerpt
that names its subject; `when_happened` scored on temporal questions; closed regression threads; a status question
that names no one asks every window (D97). Not measured yet.

**D95 — `resolve-v6`: direction, composite persona names, derived names (ADR 0095; PHASE-65 S3; amends D26, D34,
D56).** An alias has a direction: a name that is the subject of every alias counted for it is one person; a shared
target stays ambiguous; a `?` description never makes a name ambiguous. A host persona name is split on `/`, `|`, `·`
and parentheses into primary names, the only ones folded into `{{user}}`; no name is folded by its last word. Derived
persona names (given and first names, Hangul and Latin spellings, surname plus persona) join the persona as links the
owner can split, unless the owner or another name says otherwise. A lorebook entry may join one person's names the
story kept apart (never the persona's, never unrelated names); `secondkey` is not a key. `@name` reads vocatives,
honorifics, up to three words and aliases. Entity ids change once; they are not stored.

**D96 — The author's note in the chat's language (ADR 0093; PHASE-65 S8).** A note request's `language` is `"chat"`
(the default, read from the scene summaries, else threads and facts) or `"en"` (the prompts as before). With `"en"` and
secrets left out, a model-written part is also checked by meaning against the open secrets: the embedder (cosine ≥
0.62), else one call of the note's model; a failing check counts as a leak. Every line goes through `tells`; open
threads are capped (15, 25 %); before the first scene summary the chronicle is made from threads and NOW facts.

**D97 — Status windows in more shapes, keys that stay (ADR 0094; PHASE-65 S9; amends D80).** Windows read as nested
bars, 【】《》『』, multi-line blocks, Markdown tables and HTML cards, with what the earlier rules read read the same way.
A window's keys are prefixed `<character>.<key>` only when one reply holds windows of two or more names sharing a
non-scene key; scene keys never are; a bare pin or watch covers a key by its last part. The rules version is
unchanged. Under `packet-v21` a status question that names no character asks that key of every window.

**D12 — MCP is optional deep recall**, never the correctness mechanism. Tools are read-only
and bound server-side to `(conversation, worldline, principal)` via a scope token.

## 6. Stack (confirmed by owner 2026-09-22; O2 resolved: PostgreSQL)

| Part | Choice |
|---|---|
| Sidecar | Python 3.12, FastAPI, Pydantic v2, psycopg 3 with explicit SQL, `uv` |
| DB | PostgreSQL 16 + `pg_trgm` (+ `pgvector` from Phase 3) |
| Migrations | plain SQL files in `migrations/`, applied by a small runner |
| Worker | same codebase, separate process, Postgres-backed job table (`SKIP LOCKED`) |
| Plugin | TypeScript → single bundled `.js` (esbuild) in PocketRisu V3 plugin format |
| Tests | pytest (sidecar), vitest (plugin pure functions) |
| Deploy | Docker Compose on homelab; optional token in the plugin arg `auth_token` (ADR 0003, H12); TLS if crossing hosts. Without Docker (Phase 23, ADR 0060): a portable bundle per PocketRisu portable target — `NMOS-vX-win-x64.zip` (`NMOS.exe`, tray), `-macos-arm64.dmg` (menu-bar `NMOS.app`, signed ad hoc), `-linux-x64.tar.gz` and `-linux-arm64.tar.gz` (`start.sh`) — each with PostgreSQL 16 (`pg_trgm`, `pgvector`), Python and the plugin, attached to tagged releases |

## 7. Repository layout

```text
nmos/
├── AGENTS.md / CLAUDE.md / ARCHITECTURE.md
├── README.md / CHANGELOG.md
├── docker-compose.yml         # development: postgres + sidecar + worker, built from source
├── deploy/docker-compose.yml  # release: published images (attached to each GitHub release)
├── .env.example
├── docs/
│   ├── HOST-FACTS.md          # runtime host evidence (Phase 0A, extended since)
│   ├── STATUS.md / KNOWN-ISSUES.md / guide.ko.md
│   ├── phases/PHASE-0.md … PHASE-9.md (+ PHASE-0-RETRO.md)
│   ├── perf/                  # measurements and model evaluations per phase
│   ├── adr/
│   ├── audits/                # external audits and their reviews
│   ├── proposals/             # Track A/B and feature proposals (not authorized until decided)
│   └── reference/             # long-form design doc (non-normative)
├── adapters/
│   ├── pocketrisu-spike/      # Phase 0A observation plugin (throwaway)
│   └── pocketrisu-plugin/     # Phase 0B thin adapter (TypeScript → dist/nmos-pocketrisu.js)
├── apps/
│   └── sidecar/               # Python package nmos_sidecar:
│                              #   canonical, reconcile (pure), ledger, retrieval, packet, api,
│                              #   extraction, facts, entities, threads, vectors, worker, inspector, …
├── migrations/                # numbered SQL, applied by nmos-migrate
├── fixtures/
│   ├── host/                  # recorded PocketRisu observations
│   └── unit/                  # cross-language hash vectors
├── tools/                     # release check, benchmarks, evaluations, replay; Phase 0A spike tooling;
│                              #   native/: the Docker-free bundles (builder, launcher, tray, menu-bar app, smokes)
└── docker/
```

The worker (`nmos-worker`) lives in the same package. Domain code is split into packages only when a
second consumer needs it; empty future directories are not created in advance.

## 8. Roadmap (summary)

| Phase | Deliverable | Uses LLM? |
|---|---|---|
| 0A | Host observation spike → `HOST-FACTS.md` | No |
| 0B | Adapter + sidecar + ledger + reconcile + raw lexical recall + budgeted injection | No |
| 1 | Deterministic state parsers (D10), inspector v0 (read-only), traces — **done (beta)** | No |
| 2 | Predicate registry (D6), bounded extraction (D7), assertions, fact versions — **done (beta)** | Yes, async |
| 3 | Hybrid retrieval (SQL + trigram + pgvector), RRF, selector, abstention — **done (beta)** | Embeddings only |
| 4 | Soft subset — knowledge marks (D19) — **done (beta)**; hard principal modes (D9 `character_pov`) not authorized | Yes |
| 5 | Entity identity, assertion semantics (Track B, B1) — **done (beta.12)** | Yes |
| 6 | Item transitions and conflicts (Track B, B2) — **done (beta.13)** | Yes |
| 7 | Promise threads and event salience (Track B, B3 narrowed) — **done (beta.14)** | Yes |
| 8 | Typed event participants (Track B, B3 narrowed) — **done (beta.15)** | Yes |
| 9 | Accountable packets: ledger, excerpt room, echo, as-of replay (Track B, B6 narrowed) — **done (beta.19)** | No (the answer probe uses one) |
| 10+ | Rest of B3 (events, relationships, causal links), canon, hard POV, forensic recall, MCP | Yes |

Each phase gets its own `PHASE-N.md` with acceptance criteria before work starts.

## 9. Open decisions

These must be resolved by the owner, not by an implementing agent.

- ~~O1 — Relationship to MIRRA and VEIL~~ — **resolved 2026-09-30: NMOS is an independent
  project, no longer related to MIRRA or VEIL.** Owner decision in
  [NMO-16](https://linear.app/sallos725/issue/NMO-16), recorded here by NMO-32.
- ~~O2 — Postgres vs SQLite~~ — **resolved 2026-09-22: PostgreSQL** (§6).
- ~~O3 — Main-generation gating heuristic~~ — **resolved 2026-09-22: D13 / ADR 0001.**
- ~~O4 — Cross-chat branch policy~~ — **resolved 2026-09-22: D14 / ADR 0002.**
- ~~O5 — Retention of abandoned worldlines~~ — **resolved 2026-09-24 (D29, D31).** Decided 2026-09-23 for superseded projection
  generations: LLM extractions are kept; embeddings and deterministic projections may be pruned once
  a newer generation fully covers the chat (`docs/proposals/TRACK-B-PHASE-5-PLUS.md` §4; implemented
  as D29, ADR 0015). Decided 2026-09-24 for host observations (`docs/phases/PHASE-6.md` Q5):
  full-manifest observations are compacted losslessly (only rows changed against the previous
  observation, as appends already are); everything else on abandoned worldlines is kept (implemented
  as D31, ADR 0018).
