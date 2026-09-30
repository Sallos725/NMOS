# Proposal — Ideas from a survey of another memory plugin

> Status: proposal only (2026-09-29). It does not authorize a phase or change the current scope in `AGENTS.md`,
> `ARCHITECTURE.md` or `docs/STATUS.md`. The owner decides where each candidate goes (§6). Owner, 2026-09-29: follow the
> recommended order.

## 1. Source

The owner asked for the ideas worth taking from another community memory plugin for RisuAI (a single bundled V3
plugin, read locally; not named here). No code was copied: this document restates ideas in NMOS terms and checks
each one against NMOS's code, host facts and measured data.

How that plugin works, in one paragraph: after each reply a "writer" model call turns the turn into typed edits of a
per-chat wiki (documents with slots, per-person profiles, numeric scores); before each main request a "router" call
picks up to six wiki documents and a "director" call (one or two passes, with searches it asks for) writes a note
that is injected as one system message. The wiki is edited in place; rerolls are undone from a change history.

NMOS already differs on the points that matter most: an immutable source ledger with rebuildable projections instead
of an edited wiki, no model call on the request path, no write to host data, keys on the server.

## 2. Taken now

| Idea | NMOS | Where |
|---|---|---|
| Read the host's CBS blocks, fail closed on what cannot be resolved | A canon fact quoted only inside a conditional block is not served. Sample 2's copy: 125 of 323 served canon facts came from such blocks | H20, ADR 0047 amendment 2, PR #176 |

## 3. Already in NMOS

| Idea there | NMOS equivalent |
|---|---|
| "Unknown never replaces a known value" guards on model edits | Not needed: assertions accumulate from evidence and supersede by statement; 0 placeholder values ("unknown", "없음"…) among ~14,000 assertions on the two measured copies |
| One current feeling per directed pair, with a short history | `feels_toward` and `relationship` are `single` per (subject, object) with versioned history; each direction has its own lock (ADR 0038, 0047) |
| A target-specific speech record that non-observation cannot erase | `addresses` (ADR 0028) |
| Main-request filter (skip auxiliary modes; the chat's latest user message must be in the prompt) | `isMainGeneration` (D13, ADR 0001); see C1 for the open part |
| Per-item validation (reject one bad edit, keep the rest) | `extraction.normalize` gives each assertion its own status (`valid` / `pending` with a reason) |
| Idempotent retries with per-edit receipts | Jobs keyed by `dedupe_key`; projections rebuild from the ledger |
| Reroll rollback by message identity | The reconciler (worldline commits, active membership, H14) |
| Pins that the model may not override | The owner's lock (ADR 0047) and repairs (ADR 0044) |
| Lore "seed" facts that the story may override | Canon facts sit before turn 0 and the story supersedes them (ADR 0047) |
| Knowledge-boundary note in the injected text | The packet `<Note>` states known_by / hidden_from and "do not assume either way"; see C9 for the stronger wording |
| Run inspector with retention | Inspector, `retrieval_trace` with `NMOS_TRACE_RETENTION_DAYS` |

## 4. Candidates

Each candidate: what it is in NMOS terms, why, what it costs, and what must be true first.

**C1 — Trigger and Lua model calls on the request path.** That plugin's code notes that Lua `LLM()`, trigger
`runLLM` and other plugins reach `beforeRequest` with mode `model`, and it adds probes of the previous reply to tell
them apart. `docs/HOST-FACTS.md` Q1 already records from source that trigger/Lua calls pass `'model'` and that
whether they also pass D13's test "was not observed". If they do, NMOS syncs, recalls and injects a packet into a
side call: wasted work and a misleading trace. *Cost:* one run of the local harness with a bot whose trigger calls
the model. *Kind:* host evidence, then a correctness fix if needed; no phase.
*Measured 2026-09-29 (no change):* this is K14, already accepted. The host source confirms the path (HOST-FACTS
Q1). The owner's production request log, read from a copy (2026-09-23 to 09-29), has none: all 751 `model` requests
carried chat history with the model's replies, and all 560 packets went into those. Tightening the gate would risk
dropping memory from real requests for a case not seen; K14 records the numbers.

**C2 — Every assertion's evidence found in its turn.** That plugin rejects a score change unless its quote is an
exact substring of the reply. NMOS checks quoted evidence only for reveals (trigram containment 0.7, PHASE-10). The
same check for every assertion would park an unsupported one as `pending`. *Cost:* a validation change, so a new
extractor generation (D20), measured with M0. *Kind:* the "Queued for the next extractor generation" list in
`docs/STATUS.md`.

**C3 — Repeated evidence before a lasting trait.** That plugin changes a personality axis only after 4 pieces of
evidence from 3 different scenes, and a person reviews it. In NMOS a single statement makes a `has_trait` current. A
read-side rule could serve a trait as current only after it is stated in N turns of M scenes, and as "once" before
that. *Cost:* a packet-policy change measured offline by replay (no model calls). *Risk:* a card's trait stated
once in canon would need an exception (canon counts as settled).
*Measured 2026-09-29 (dropped):* on the two measured copies the active extraction holds 18 and 14 `has_trait`
facts, and no value is stated in two turns (0 of 32). NMOS's traits are free text, so a repetition threshold would
hide every one; that plugin can count repetitions because its axes are a fixed vocabulary. Not pursued.

**C4 — Token usage of NMOS's own model calls.** That plugin shows provider-reported usage per stage (with cache
and reasoning tokens) and marks estimates as such. NMOS records calls but not their tokens, and the owner pays for
extraction. Store the provider's `usage` with each extraction and summary, and show totals per chat in the
Inspector's coverage. *Cost:* a migration (two nullable columns) and a panel line. *Kind:* Stage 6 or ops.

**C5 — The HUD tells a fallback from a failure.** That plugin's progress card shows a failed step that fell back
(its keyword search after a failed model call) in a neutral colour with the fallback's name, not as an error, and
ends with what was written. NMOS's HUD has request outcomes; recall without vectors (K34) is only in the Status tab.
Show "lexical only" and "cached packet" as their own neutral outcomes, and after an extraction "N facts" in the
Status tab. *Cost:* plugin UI only. *Kind:* UI; ships with the next milestone.

**C6 — Imported data carries its own provenance kind.** When that plugin imports memory it cannot check against a
source, it keeps it but rewrites every evidence reference to "manual, unverified" and prefixes the reason. Phase 16
(approved) restores an NMOS archive, which holds the ledger itself, so nothing restored is unverified there. The rule
belongs to importing another plugin's memory (Phase 16 out of scope; proposal P4 of
`PUBLIC-RELEASE-AND-BENCHMARK.md`): such rows would be their own source kind, labelled unverified in provenance and in
the Inspector, never shown as extracted. *Kind:* P4, if it is ever taken.

**C7 — Merge with a preview.** That plugin's person merge builds a plan first: blockers, every conflicting field
with a choice of side, numbers never summed, a backup downloaded before applying, and the plan refused if memory
changed since. NMOS's name joins (ADR 0025) apply at once. A preview of what a join changes (facts that would
conflict, locks involved) and an undo that restores the exact state fit Stage 6's "entity merge/split". *Kind:*
Stage 6, remaining items.

**C8 — Bounded, model-directed search.** That plugin's director may ask for up to 8 typed searches (chat, memory,
lore) in its first pass; the plugin runs them and a second pass must answer from them, citing only the returned
references. For NMOS this is an opt-in "deep recall" tier: the sidecar runs the searches on its own indexes
(lexical, vectors, graph) and checks the citations. *Cost:* one or two model calls on the request path, against
invariant-level latency goals, so off by default. *Kind:* Stage 7 (forensic recall).

**C9 — A stronger knowledge rule in the packet note.** That plugin prefaces its note with: a character does not
mention or act on a fact they have not witnessed, and missing memory does not prove ignorance. NMOS's `<Note>` says
who knows a fact but not what to do with it. *Cost:* a packet-policy version (replays keep their policy); the effect
is on the reply model, so it needs a live A/B on the secret gate (`tools/eval_secret_gate.py`), which costs model
calls. *Kind:* packet policy, owner OK for the spend.

**C10 — Memory of chats deleted in the host.** That plugin scans the host's chats and offers to delete memory whose
chat is gone. NMOS keeps a deleted chat's memory until the owner deletes the conversation (ADR 0009). A panel list of
conversations whose chat the host no longer has would need to list the host's chats: `getDatabase` characters behind
the "db" permission (H17), not measured for cost. *Cost:* host evidence first. *Kind:* UI, Stage 6.
*Host evidence (2026-10-01, H22):* `getDatabase(['characters'])` lists every active chat's id. It takes ≈0.5 ms
with no chat opened and ≈100–150 ms with 10,000–15,000 opened messages, which stay loaded until the page reloads.
A chat whose character was moved to the trash or deactivated (restorable) leaves the list just as a deleted one does.

## 5. Not recommended

| Idea there | Why not in NMOS |
|---|---|
| Numeric affinity, suspicion and personality scores estimated by the model | A number the story never states cannot be traced to evidence (invariant 10) and hides "unknown" (invariant 4); that plugin needs per-turn clamps and allowed deltas to keep them stable |
| Writing its scope id into the host's chat (`setChatToIndex`) | Forbidden (AGENTS §4, Plugin) |
| Waiting for the previous turn's extraction before the main request | Fail-open and latency: NMOS serves what it has and marks the rest pending |
| Model calls and API keys in the plugin | Keys and long work belong to the sidecar (AGENTS §4) |
| Per-user prompt blocks appended to the extraction prompt | Every variant would be its own generation (D20); the owner's repairs cover corrections |
| Reading another plugin's storage, reading the host page's DOM for names | Fragile and outside the V3 API's contract (H16, H17) |

## 6. Recommended order (owner decision)

1. **C1** measured: not seen in production, K14 updated, the gate unchanged.
2. **C6** only with P4 (importing another plugin's memory), if that is ever taken.
3. **C4 + C5** as Phase 17, after Phase 16 (owner, 2026-09-29); `docs/phases/PHASE-17.md`, approved 2026-09-29.
4. **C2** on the queued list for the next extractor generation (queued in `docs/STATUS.md`, 2026-09-29); **C3**
   measured and dropped (§4).
5. **C7 and C10** with Stage 6's remaining items; **C8** with Stage 7; **C9** only with an approved spend.
