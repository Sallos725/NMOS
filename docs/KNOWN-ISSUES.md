# NMOS Known Issues

Current as of `v0.1.0-beta.13` (2026-09-24), with Phase 7 changes marked "unreleased". This is the single list of what does not work, or works
only partly, in the current release. Each release's "Known limitations" in `CHANGELOG.md` describes
that release at the time; entries fixed later are listed under [Resolved](#resolved) below.

"Tracked" says where a fix would come from. Track B stages are proposals
(`docs/proposals/TRACK-B-PHASE-5-PLUS.md`) and are not authorized; "host" means NMOS cannot fix it
without a PocketRisu change.

| ID | Issue | Area | Tracked |
|---|---|---|---|
| K1 | Long chats wait before the reply; beyond ≈10,000 messages memory needs a higher deadline | Performance | host |
| K2 | The first generations in a long chat NMOS has not seen yet go without memory | Performance | by design (chunked first sync) |
| K3 | After an edit, reroll or swipe, a long chat takes the slow sync path | Performance | protocol change (not planned) |
| K4 | Phones were not measured | Performance | evidence |
| K5 | Every generation hangs after installing, updating or disabling the plugin until reload | Host | host (H13) |
| K6 | PocketRisu must be opened at `localhost` or HTTPS | Host | browser rule |
| K7 | Tested on one PocketRisu build only; no group chats | Host | evidence / host (H11) |
| K8 | Names can still split: a new name with no stated alias is a new entity | Memory | reduced in beta.12 (ADR 0012); owner merge/split: Track B, B7 |
| K9 | A destroyed or used-up item keeps its last holder in turns not extracted by `extract-v6` | Memory | fixed for new turns in beta.13 (ADR 0017); older turns: "extract all history" |
| K11 | Character knowledge is a hint, not isolation | Memory | Track B, B5 (hard POV) |
| K12 | A word in more than 200 messages brings no lexical excerpts | Recall | accepted trade-off (A3) |
| K13 | Very long messages are only partly embedded and extracted | Recall | accepted limit (#13) |
| K14 | Rare over-injection into an auxiliary call; transformed input gets no memory | Gating | accepted (ADR 0001) |
| K15 | Thresholds and extraction quality are checked on limited data | Quality | evaluation (A5 baseline) |
| K16 | NMOS does not notice a chat deleted in PocketRisu | Data | host (H10) |
| K17 | Storage grows with abandoned branches | Data | O5 decided: superseded vectors pruned (ADR 0015), observations compacted (ADR 0018); abandoned branches kept |
| K18 | Changing a model or endpoint re-processes history at the provider's cost | Data | LLM: bounded to the recent window since beta.11 (ADR 0014); embeddings: by design |
| K19 | Plugin and sidecar versions are not checked against each other | Setup | not planned |
| K20 | Small UI delays: bot name, menu language | UI | not planned |
| K21 | API keys and the auth token are stored in plain text | Security | host (H12) |
| K22 | What becomes a fact depends on the extraction model's labels | Memory | measured per model (`docs/perf/phase5-extraction.md`, `docs/perf/phase7-extraction.md`) |
| K23 | A promise stays open until the story keeps or breaks it in words extraction recognizes | Memory | Phase 7 (unreleased); owner repair: Track B, B7 |

## Performance

**K1 — Long chats wait before the reply.** Measured on PocketRisu v1.12.0, desktop Chromium: NMOS
adds ≈1.5 s at 5,000 messages, ≈2.7 s at 10,000 and ≈4.1 s at 15,000 per warm generation. Most of it
is the host: after `getChatFromIndex` hands the plugin a deep copy of the whole chat, the page stalls
(≈1.7 s at 10k); the sidecar's own processing at 10k is ≈135–165 ms. The V3 API has no call that
returns part of a chat. The 3 s default deadline covers up to ≈10,000 messages with ≈0.25 s margin.
*Workaround:* raise **제한 시간(ms) / Deadline (ms)** in the panel's Settings tab (≈5,000 at 15,000
messages). Otherwise those requests go without memory; the chat itself is unaffected.
Evidence: `docs/perf/scale.md` (real-host check), D24.

**K2 — First generations in an unseen long chat go without memory.** The first sync of a chat NMOS
has not seen needs 7.4 s (5k), 15.2 s (10k), 22.4 s (15k). It uploads in durable chunks across
several generations; those generations fail open. *Workaround:* none needed; memory starts once the
upload completes. A temporarily higher deadline finishes it in one generation.
Evidence: `docs/perf/scale.md`.

**K3 — Edits, rerolls and swipes take the slow sync path.** Only a pure append is proven and
reconciled from the tail (ADR 0010). Anything else — an edit, a deleted message, a swipe, and every
reroll (the host removes the old reply before the plugin runs, H14) — takes the full path: ≈0.9 s at
10,000 messages in the sidecar benchmark instead of ≈0.16 s. **Not measured on the real host**: added
to K1's ≈2.7 s, a reroll near 10,000 messages is likely to exceed the 3 s default and go without memory.
Removing the remaining full-manifest parsing needs a plugin–sidecar protocol change (ADR 0010).
Evidence: `docs/perf/scale.md` (bench table, "Edit near head").

**K4 — Phones were not measured.** All latency numbers are desktop. A phone browser's copy of a
long chat is likely slower; the real envelope there is unknown.

## Host

**K5 — Reload after installing, updating or disabling the plugin.** PocketRisu does not unregister a
V3 plugin's `beforeRequest` hook; the old one stays attached to a dead frame and every generation
hangs until the page is reloaded (H13). The plugin cannot guard against it. *Workaround:* reload
(F5). Documented in README and the Korean guide.

**K6 — `localhost` or HTTPS only.** Browsers do not run PocketRisu plugins on plain-HTTP LAN
addresses such as `http://192.168.x.x:6001`. *Workaround:* PocketRisu Remote Access (HTTPS) or an SSH
tunnel to `http://localhost:6001` (README "Requirements").

**K7 — One tested host build; no group chats.** Behavior is verified on PocketRisu `a14c911`
(v1.12.0) only. Upstream RisuAI uses the same V3 plugin API but is untested. That build has no
group-chat type (H11), so group-chat scenarios (S13) could not be run.

## Memory

**K8 — Names can still split.** Since 0.1.0-beta.12 facts are keyed by entity (ADR 0012): names are
joined when the story states both in one turn ("하나(Hana)") or a character introduces their own
nickname, and extraction is shown the chat's earlier names so it reuses them ("해안 지도" stays "해안
지도" 3/3 in the real-model check). A new name with neither — the model writing "지도" for a hinted
"해안 지도", or a nickname only others use — is still a separate entity, and two different items with
the same name and type are still one. A character introducing themself under someone else's name
merges the two until that turn is edited or deleted (the Inspector shows each alias's turn). Knowledge
marks (`known_by`, `hidden_from`) stay free text. Owner corrections (merge/split) are Track B, B7.

**K9 — Destroyed or used-up items keep their last holder.** A new holder ends the previous one (ADR
0011), and since 0.1.0-beta.12 so does a statement that the holder no longer has it ("lost", "dropped
into the sea", "gave away"; ADR 0013; 3/3 in the real-model check). An item that is destroyed, eaten or
used up with no such statement still shows its last holder. *Fixed for new turns in 0.1.0-beta.13:*
the extraction records `destroyed` (burned, eaten, used up), which ends the holder and the place (ADR
0017). This holds only for turns extracted by `extract-v6`. Older turns need "extract all history", and
real-model accuracy is not measured yet.

**K11 — Character knowledge is a hint.** Facts carry `public` / `limited` (`known_by`,
`hidden_from`) / unknown marks and the packet tells the model how to use them, but one generation
writes for every character, so a secret can still leak (ADR 0007). Hard per-character isolation
(D9 `character_pov`) is not authorized (Track B, B5).

**K22 — Facts depend on the model's labels.** Since 0.1.0-beta.12 only what the extraction model labels
as actual narration becomes a fact (ADR 0013). On the tested model (`deepseek-v4.1-flash`) 1 of 32
(release candidate: 1 of 34) real events was labeled non-actual, no plan, dream or claim became a fact in 21 runs, and one run
inferred a negation from a clue the narration did not state (`docs/perf/phase5-extraction.md`). Other
models were not measured. *Workaround:* check the Inspector's "not actual" list if a fact is missing. Since Phase 7 each event is also labeled major or minor, which decides whether a mention alone brings it into the packet (4 of 4 major scenes 3/3; minor scenes never labeled major; `docs/perf/phase7-extraction.md`).

**K23 — Promises stay open until the story closes them.** Since Phase 7 (unreleased; ADR 0019) a
promise is an open thread until a turn keeps it (`fulfilled`) or breaks, withdraws or releases it.
Three cases leave one open: the story forgets it (nothing closes a promise because it is old); the
closing turn was extracted by a generation before `extract-v7`, which has no `fulfilled`; or the
closing turn words the promise so differently that it matches no open promise, or matches two (the
Inspector lists it under "matching no open promise"). An open promise reaches the packet only when
its maker or recipient is mentioned, at most three at a time. *Workaround:* "Extract all history" for
older turns; owner repair (close a promise by hand) is Track B, B7.

## Recall and gating

**K12 — Broad words bring no lexical excerpts.** If a query's words occur in more than 200 messages
(a main character's name, a recurring place), lexical recall abstains for that request (Inspector
trace `too_broad`) instead of scoring most of the chat. Vectors, state and facts still answer; with
embeddings off, such a query gets no excerpts. Accepted trade-off of Track A, A3
(`docs/perf/scale.md`).

**K13 — Very long messages are partly processed.** Embeddings cover at most the first 8 chunks of
≤700 normalized characters (≤5,600); extraction reads the first 6,000 characters of each message in
the target turn and 2,000 of each context message. The Inspector flags partly processed messages
(#13).

**K14 — Gating edge cases.** A main generation is recognized by the user's latest input appearing in
the prompt (ADR 0001, amendment 2). A `model`-mode auxiliary call (trigger/Lua) whose prompt contains
that input is treated as main and may get a packet (not observed; accepted as rare over-injection).
A preset that sends the input only in transformed form (e.g. translated) gets no memory (fail-safe).

**K15 — Tuned on limited data.** Recall thresholds were set on few real chats (ADR 0004/0005). The
evaluation baseline uses synthetic cases and a stub extractor (`docs/perf/eval-baseline.md`), so it
checks correctness (stale, deleted, rerolled, other-branch memory), not extraction quality.
Extraction quality depends on the model: a weak model may still record a refused action as done
(`docs/perf/turn-extraction.md`). Reports of wrong or missing memory are the main input here.

## Data and lifecycle

**K16 — Chat deletes in PocketRisu go unnoticed.** PocketRisu fires no plugin hook for delete, edit,
swipe or branch (H10); NMOS sees changes at the next generation in that chat. A chat deleted in
PocketRisu stays in NMOS. *Workaround:* delete it in the panel's Inspector tab (ADR 0009; cannot be
undone, and nothing but a sidecar log line records it).

**K17 — Storage grows with abandoned branches.** Abandoned worldlines (rerolled or
edited-away branches, with their vectors) and host observations (≈2.7 KB per generation at 10k) are
kept for audit, and so are superseded LLM extractions (by decision). A 10,000-message synthetic chat
with embeddings takes ≈120 MB. Since 0.1.0-beta.13 (ADR 0015), superseded vectors are deleted once the
new embedding projection covers the chat, and older normalized text at startup, so a model change no
longer leaves a second copy of every vector. Since 0.1.0-beta.13 (ADR 0018), an edit, reroll or swipe
no longer keeps a full copy of the chat's manifest: the worker stores it losslessly as the rows that
changed (≈1.1 MB → ≈1.4 KB per action at 10,000 messages). Abandoned branches stay, by decision (O5).
*Workaround:* delete conversations you no longer use.

**K18 — Model changes re-process history.** Changing the LLM or embedding model or endpoint, or a
release that changes the extraction generation (as 0.1.0-beta.8 did), re-derives all previously
covered history with the new model, recent turns first, at the provider's cost. Until done, the
Inspector shows partial coverage and older facts may be missing (ADR 0006). **Since 0.1.0-beta.11 (ADR 0014):** an LLM change re-extracts only each chat's recent
window (`NMOS_EXTRACT_BACKFILL`); older turns keep the previous model's facts until "extract all
history". Embedding changes still re-embed everything covered. With a reasoning model,
per-turn extraction produces ≈19 % more completion tokens than per-message did (≈9 % fewer tokens
overall; ADR 0008).

## Setup and UI

**K19 — No version check between plugin and sidecar.** A plugin newer than the sidecar shows HTTP
errors in features the sidecar lacks (e.g. a 0.1.0-beta.6 plugin's Inspector tab against a beta.5
sidecar: 404). Memory injection keeps working or fails open. *Workaround:* upgrade both parts
together, as each release note says.

**K20 — Small UI delays.** After an upgrade, the Inspector shows a conversation's bot name from its
second message (the plugin reads it in the background). Plugin menu names switch language only after
a page reload.

## Security

**K21 — Plain-text secrets.** LLM/embedding API keys saved in the panel are stored unencrypted in the
local Postgres (`app_config`); keys in `.env` stay in that file. The plugin's `auth_token` is a plugin
argument, readable by anyone who can open PocketRisu's plugin settings, because `saveSecretHeader` is
an unimplemented stub on the tested build (H12, ADR 0003). The token is off by default.
*Workaround:* never expose the sidecar or database to the internet; set a token when binding to a LAN
or Tailscale address (README "Security").

## Behavior by design

Not issues, but often reported as one:

- **Nothing is injected early in a chat.** Memory covers only what has left the prompt; while
  everything is still in context there is nothing to add.
- **Only chats you generate in are read.** NMOS never scans other chats (D22); a chat enters NMOS on
  its first generation with the plugin on.
- **Auxiliary requests (summaries, suggestions, translations) never get memory** (ADR 0001).
- **The newest turn's facts wait for the next turn.** A turn is extracted after you continue from
  its reply (ADR 0008); until then it is still in the prompt.

## Resolved

| Was listed in | Issue | Resolved in |
|---|---|---|
| 0.1.0-beta.12 (K10) | An item's holder and its place were separate facts and could disagree | 0.1.0-beta.13 — one whereabouts per item (ADR 0016) |
| 0.1.0-beta.12 (K17, part) | Superseded vectors and full-manifest host observations kept growing | 0.1.0-beta.13 — pruned and compacted (ADRs 0015, 0018); abandoned branches kept by decision |
| 0.1.0-beta.8 | `possesses` multi-valued: giving an item away did not end the previous holder | 0.1.0-beta.10 — one current holder per item (ADR 0011); rest is K8–K10 |
| 0.1.0-beta.4 | Warm sync linear in chat length; 800 ms default reliable only up to ≈5,000 messages | 0.1.0-beta.10 — append fast path, incremental manifest, 3 s default (ADR 0010, D24); rest is K1–K3 |
| 0.1.0-beta.4 | A query matching nearly every message ran into the 300 ms lexical budget | 0.1.0-beta.10 — stops at 200 matches (`too_broad`); rest is K12 |
| ≤ 0.1.0-beta.6 | Presets that add instructions after the user's input got no memory | 0.1.0-beta.7 (ADR 0001, amendment 2) |
| 0.1.0-beta.6 | beta.6 plugin against a beta.5 sidecar: Inspector tab 404 | general form is K19 |
| (not listed; found 2026-09-24) | Fact and state reads could take ≈7 s at 10k messages right after an edit, reroll or swipe, so that request went without memory | 0.1.0-beta.11 (`docs/perf/scale.md`) |
| K18 (LLM part) | A new LLM model re-extracted all covered history | 0.1.0-beta.11 — recent window only (ADR 0014); embeddings unchanged |

One-time upgrade effects (migration 0012's index build, beta.8's re-extraction, beta.4's
re-derivation of beta.3 facts and vectors) are described in their release notes and are not listed
here.
