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
| H8 | V3 plugins run only in a secure context (sandbox uses `crypto.randomUUID`). Over plain-HTTP LAN they do not load; on localhost/HTTPS `crypto.subtle` is available in the sandbox. | Plugin-side SHA-256 is always available where NMOS can run; deployment must be localhost or HTTPS (Remote Access). |
| H9 | The current chat index is positional: importing a chat prepends it without changing `chatPage`, so the same index then names a different chat. | Never use character/chat index as identity; key conversations by `chat.id`. |
| H10 | Edit, delete, disable, swipe switch, branch, import and reload fire no plugin hook. | Divergence is discovered only at the next main-generation snapshot. |
| H11 | Build `a14c911` has no group-chat type (`character.type` is only `"character"`; `isGroupChat` is hard-coded `false`). | Group-chat principal logic has no host surface on this build. |
| H12 | `saveSecretHeader` is an unimplemented stub; `nativeFetch` fetches directly from the browser (proxy fallback), passes headers through, and accepts a numeric `requestTimeoutMs`. | Sidecar token lives in a plugin arg (ADR 0003); sidecar must serve CORS; deadlines use `requestTimeoutMs` + a local timer. |
| H13 | V3 `addRisuReplacer` registers no unload callback (`loadPlugins` clears only `chatOutput`). After a V3 plugin is disabled, updated or re-imported, its old `beforeRequest` replacer stays registered against a dead iframe and **every generation hangs** until the page is reloaded. | Always reload PocketRisu after installing/updating/disabling the NMOS plugin (documented in README). The plugin cannot guard against this. |
| H14 | On reroll the host removes the tail AI message *before* `beforeRequest` runs (S2 beforeRequest saw 7 of 8 messages; confirmed in 0B live runs). The regenerated reply appears only in the next request's snapshot. | Live reroll reconciles as "head minus tail" → retract; lineage to the new reply is not observable in the same request. |
| H15 | The V3 plugin iframe is sandboxed with only `allow-scripts allow-modals allow-downloads` and `allow="screen-wake-lock"`. Runtime (v1.12.0): a `target="_blank"` link is blocked ("sandboxed frame whose 'allow-popups' permission is not set"), and `navigator.clipboard.writeText` is refused by permissions policy. The V3 API has no call that opens a URL. | The plugin cannot open a browser tab. The Inspector is shown inside the panel from `/v1/inspector*`, and links in it must be handled by the panel (following one would navigate the plugin frame). |
| H16 | With the `mainDom` permission (host confirm, persisted; a denial is permanent until reset) a V3 plugin gets the page through an async `SafeElement` proxy (text is escaped, `setInnerHTML` is sanitised). Element listeners are registered on the whole document. A plugin re-import leaves drawn elements behind until reload. | The progress HUD (D28) is opt-in from the panel, hit-tests clicks against its rect, and removes a leftover `.nmos-hud` before drawing. |
| H17 | The V3 API has no user-name call. `getDatabase(['personas', 'selectedPersona'])` returns the personas (`id`, `name`, …) and the selected index behind the host's "db" permission, asked once (a denial returns `null` and is permanent until reset). The host names the user after the chat's `bindedPersona` (in the `getChatFromIndex` snapshot), else the selected persona. A typed `{{user}}` is stored with the name in place. | The plugin reads the persona name at load and in the background, never on the request path; the sidecar resolves it as the persona (ADR 0023, D34). |
| H18 | The V3 `alert(message)` is PocketRisu's `alertNormal`: it sets the one global alert store (a later alert replaces the one on screen) and shows a modal with a Confirm button. Shown after a reply it appears over the chat and leaves the reply as it is. | The plugin alerts only from the output listener, after a reply, at most once per page (deadline advice, audit A-09); never on the request path. |

## 5. Key decisions

Short ADR-style entries. Full ADRs go in `docs/adr/`.

**D1 — Plugin-first, no fork.** Pure plugin mode is the only supported mode until profiling
proves a bridge API is needed (see reference §82 criteria). Any future fork is bridge-only.

**D2 — Token budget is reserved, not stolen.** Because of H3, the user lowers the host's
max context by `reservedMemoryTokens` (setting). The packet never exceeds that reserve.
Trimming host history from inside the plugin is a later, opt-in feature.

**D3 — Do not re-inject what the host already sent.** Evidence whose source revision is
already present in the outgoing `formated` messages is excluded from the packet.
Activated lorebook entries are treated the same way. Lorebook is canon for conflict checks,
not a retrieval payload by default.

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
and calls another, single per direction; D38, ADR 0028).

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
score: lexical recall abstains for it (trace `too_broad`), other routes still run (Track A, A3).

**D16 — Deterministic state via parser rules (Phase 1).** JSON rules → `state_observation`
projection; current state read through head membership (inherits D8 invalidation).

**D17 — Extraction validity is keyed by window (Phase 2, D7; ADR 0008).** `active_membership.turn_hash`
(anchor rows) makes an extraction valid only while the head shows the same turn and bounded context;
the per-message `window_hash` was kept for generations compiled before turns until ADR 0031 retired it
(2026-09-26): extractions match on `turn_hash` only. Jobs run in `nmos-worker`
through a SKIP LOCKED queue; single-valued predicates form fact versions.

**D18 — Hybrid recall (Phase 3, ADR 0005).** Exact cosine over head-membership chunk embeddings (pgvector),
RRF with lexical, abstention by per-signal bars, query-side instruction for instruction-tuned embedders,
fail-open to lexical on embedding timeout.

**D19 — Soft character knowledge (Phase 4 subset; revised 2026-09-22, ADR 0007).** Each assertion
has `knowledge = public | limited | unknown`. `public` is openly known and needs no list; `limited`
names characters shown to know it (`known_by`) and/or characters it is kept from (`hidden_from`);
`unknown` means the evidence does not show who knows. Awareness of anyone not listed is unknown, never
"does not know"; the packet Note says exactly this. A name in both lists is contradictory evidence and
is dropped from both (noted on the assertion). Names are free text in this soft phase. A fact hidden
from a character addressed right now is ranked first. Hard POV isolation stays out of scope: a sim bot
writes every character in one generation (D9). **Amended 2026-09-26 (ADR 0026, D37):** a name in
`known_by` no longer counts toward ranking.

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
`nmos-rebuild --text`. Raw `source_revision.content` is unchanged. Bounded processing of long messages
(embedding 8 × 700 chars, extraction 6,000 target / 2,000 context chars) is recorded per revision and
visible in the Inspector.

**D22 — NMOS never ingests a chat by itself; history and rebuild are explicit (ADR 0008).** A chat
enters the ledger only when the user generates in it with the plugin on. First sight extracts the
latest `NMOS_EXTRACT_BACKFILL` turns; the rest of a chat is extracted on request
(`POST /v1/conversations/{id}/extract-history`). A rebuild (`POST /v1/conversations/{id}/rebuild`)
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
links on an entity's Inspector page; removal keeps the row (`removed_at`). There is no owner split.

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
state at 40 %; `packet-v0` is the earlier compiler. A
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
| Deploy | Docker Compose on homelab; optional token in the plugin arg `auth_token` (ADR 0003, H12); TLS if crossing hosts |

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
├── tools/                     # release check, benchmarks, evaluations, replay; Phase 0A spike tooling
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

- **O1 — Relationship to MIRRA and VEIL.** Is NMOS MIRRA v2 (superseding its SQLite/MCP-first
  choices)? Does NMOS absorb VEIL's knowledge-boundary role, or consume VEIL as a separate
  plugin for disclosure pacing?
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
