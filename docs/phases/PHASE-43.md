# Phase 43 — Status windows by their shape, per chat, told as changes

Status: **approved** by the owner, 2026-10-11 ("추천대로 승인"): Q1–Q6 as recommended (answers below). Drafted at
the owner's request after the Phase 41 live check. Amends Phase 39 amendment 2 (explicit card-bound status
configuration) and ADR 0071. Not a roadmap stage; a correction phase beside the current one (AGENTS.md §7.5).

## Why

1. **Setup is bound to the wrong thing.** A status rule is regex JSON bound to a card's exact display name. A
   renamed card or two cards with one name break or mix it, and the Settings view "saved JSON rules" lists every
   card's rules together, which the owner finds confusing.
2. **The current status can be invisible to the model.** NMOS withholds a current status value whose source
   message is in the prompt (D3: in context), and decides that from the message's prose. The owner's presets strip
   every status bar from the prompt, so on the trial install's newest card chat no current status value was placed
   in 14 of 14 requests. In the incident of 2026-10-11 (Phase 41 investigation), a request failed open, the model
   had no date in its prompt and invented one 15 days ahead; the next request's packet then carried that invented
   date as current state, faithfully. NMOS held the correct earlier value but never showed it.
3. **Placing the whole status every turn is heavy.** One trial card's status has 23 keys (about 1,700 characters
   as `<State>` items); its inventory value alone is 413 characters, repeated every turn.

## Proposal

S1. **A built-in shape detector, no regex.** In a reply, an outermost balanced `[ … ]` block whose `|`-separated
segments are at least three and at least 60 % `key=value` or `key: value` fields (a leading `Label:` such as
`Status:` is allowed; values cleaned as the rule parser cleans them) is a status window candidate.
Existing regex rules stay available as an advanced override and keep working unchanged.

S2. **Per chat, confirmed once.** When the same key set appears in at least two replies of a chat, the panel offers
"this chat has a status window (N keys) — track it". Confirmation binds the detected shape to that conversation
(Q1, Q2). Values, history and flags stay per chat as today.

S3. **The panel shows this chat only.** Detected keys, their current values, the toggle and pins for the open chat.
Other chats' and cards' bindings move to a collapsed management list; regex JSON only under advanced settings.

S4. **The packet tells the status as changes.** When a chat tracks a status window, its packet carries the current
value of a few core keys (Q3) and only the keys that changed since the previous status window, as changes: a number
as `44 (−1)`, a list as `+ added / − removed`, other text as the new value. This is placed whether or not the source
message counts as in context. A recorded recall option under `packet-v18`, off for historical traces (Q4, Q5).

## Evidence so far (read-only, private restored copy of the trial install; no provider calls)

| Chat | Replies | Detector values equal to the bound rule's | Recurring blocks found that are not status windows |
|---|---:|---:|---:|
| Card A (2 chats, 9 keys) | 14 | 126 / 126 | 0 |
| Card B (23 keys) | 49 | 1,127 / 1,127 (with the rule parser's tag cleaning) | 0 |
| Card C (no rule configured) | 2 | — (found a real 3-key status window) | 0 |
| Other chats | 13 | — | 0 (one non-recurring block ignored) |

Two prototype fixes were needed: brackets inside a value (`Location: … [a place] …`) required balanced outer
blocks, and five values differed until the parser's tag cleaning was applied. Lorebook-data blocks in replies were
not detected. This is one install's data; acceptance needs a wider synthetic false-positive set (A2).

## Answers (owner, 2026-10-11: as recommended)

- Q1: confirmed once in the panel; nothing starts tracking by itself.
- Q2: a confirmation binds the detected key set to the card, so a new chat of that card where the same keys appear
  is tracked too (a card binding, as today, plus the key set).
- Q3: core keys are the pinned keys plus the keys that changed in at least half of the last ten status windows.
- Q4: always placed; no literal prompt check.
- Q5: existing card-bound rules stay as they are; the panel offers to track a detected window beside them.
- Q6: bindings, key sets and pins live in the existing `app_config` parser JSON; no migration.

## Steps

1. This record (approval, answers, step order).
2. **S4 first**, alone: the packet's status as core values plus changes, placed even when the source message is in
   context, under a recorded `packet-v18` option (`state_changes`). Works with today's card-bound rules; it is the
   correction for the date the model could not see.
3. S1–S2: the sidecar's detector (a `shape` rule kind), a read-only candidates endpoint and explicit track/untrack/pin
   endpoints. Detection never writes configuration; only the track call does.
4. S3: the panel shows the open chat only, offers detected windows and pins; other bindings collapsed; JSON under
   advanced.
5. Evidence A1–A5 recorded against the shipped code (done 2026-10-11, [below](#step-5-evidence-a1a5-against-the-merged-code)).

S4 details fixed by this record:
- The previous window is the latest earlier head reply with an observation under the same rules version. The first
  window has no previous one: every key is new and told, without change marks (corrected in step 2: with only core
  keys, a chat's first status would have been left out).
- Unchanged keys that are not core are left out (not shown as `+0`).
- Change forms: an integer `44 (−1)`; `a / b` with both parts numeric, the change of the first part; a list (split on
  ` / ` or `, `, at least three items) as `+ added / − removed` by item name, a `×N` quantity as its change; any other
  value as the new value. Dates and times are text: no arithmetic (Phase 42's boundary).
- Core keys: pinned ∪ scene keys (date, time, place: Phase 42's clock names plus location/place, also under an
  entity) ∪ keys changed in at least 5 of the last 10 windows (fewer windows: at least half of them). Scene keys were
  added in step 2: a story's date changes once in many turns, so by change rate alone it was left out, which is the
  incident this phase corrects. A list's whole value is told when the message asks about it or the key is core.
- The in-context filter is dropped only with the option on, under `packet-v18`, for a chat with active rules; v16/v17
  and historical traces (option missing: off) keep today's behavior.

## Questions for the owner (answered above)

- Q1. Confirm in the panel (recommended), or start tracking automatically after N recurrences?
- Q2. After confirmation, bind to this chat only, or also to new chats where the same key set appears
  (recommended: same key set on the same card, so a new chat of that card starts tracked)?
- Q3. Core keys: automatic (keys that change in most status windows, such as date, time, location) plus pins in the
  panel (recommended), or pins only?
- Q4. Also skip the block when the prompt already holds the latest status window (the plugin checks the literal
  text), or always place it (recommended: always; it is small once told as changes)?
- Q5. Existing card-bound rules: keep both, with a one-click conversion in the panel (recommended), or migrate?
- Q6. Where the per-chat binding lives: `app_config` JSON (no migration) or a table (migration, high risk).

## Acceptance (once approved)

- A1. On the trial install's copy, the detector's values equal the bound rules' for every reply (above) and no
  non-status block recurs.
- A2. A synthetic false-positive set (prose with `=` or `|`, markdown tables, code, lorebook-data blocks, quoted
  logs, nested brackets) proposes no status window.
- A3. Packet: the state block's tokens per request on both cards, before and after; the zero-call replay gate shows
  no newly failed probe or forbidden phrase; chats without a status window are byte-identical.
- A4. The incident shape: a request whose prompt holds no status window gets the correct current date from NMOS.
- A5. Panel: the open chat's window only; other bindings collapsed; old card rules unchanged; restore and archive
  carry the new binding.

## Step 2 evidence (S4)

Tests: change forms, core keys, the first window, a list told as its change and whole when asked; the incident's
shape (the latest bar's message in context, the date still placed) under `packet-v18`, withheld under `packet-v17`
and in a trace replayed without the option; a history question draws its key once.

Trial install's copy (read-only, no provider calls), the same requests replayed with the option off and on:

| Card | Replayed requests | Current date placed | `<State>` characters (p50) | Keys told (p50) |
|---|---:|---:|---:|---:|
| 9-key card | 15 | 0 → 15 | 0 → 279 (max 465) | 0 → 5 |

Its edited head stopped the 23-key card's old requests from replaying, so its current head was measured at the last
16 request positions instead: the whole status 1,805 characters (p50) against 790 told as changes, 23 keys to 7; the
9-key card 469 against 280. Packet tokens on the 9-key card rose by 91 at the median (286 → 377).

Zero-call gate (cached vectors, 338 probes × 3 rounds, this step against its base #295): majority packet text identical
for 338/338, 312/338 passing in every round of both lanes. The eight gate copies hold no status rule or observation
(checked), so the step cannot reach them; the round-to-round variation in both lanes is the lexical route's timing.
Local full suite: 1,542 passed; the two documentation-pointer failures of that run are fixed (the latest phase is 43).

## Step 3 evidence (S1–S2)

The detector (`statusshape.py`) and a `shape` rule kind read a window by its key set: a block counts when it holds at
least three of the set's keys and at least 60 % of them; values are cleaned as every rule cleans them. A sidecar that
predates the kind reports it as an unknown kind and skips it. Endpoints:
`GET /v1/conversations/{id}/status/candidates` (read only: the head's last 30 replies, key sets seen twice or more,
whether the card already reads them, the card's pins), `POST /v1/parsers/card/track` and `/untrack` (the card's other
rules kept, the same key set tracked once), `PUT /v1/parsers/card/pins` (`app_config.status_pins`; reading unchanged).
A request takes its card's pins as the recorded `state_pins`.

- A1, with the shipped parser on the trial install's copy, each card's recurring key set as the panel would offer it:
  the 23-key card 1,127/1,127 values equal to its bound block rule, the 9-key card 126/126 (two chats), a card with no
  rule read 6 values.
- A2 (synthetic): quoted `a=b | c=d` prose, a markdown table, a one-field bracket, a lorebook-data block, wiki and
  markdown links, a log prefix and a bracketed thought with sentence punctuation in its keys are not windows.
- Tests: looking at candidates writes no configuration; track keeps the card's regex rule and is idempotent; a
  second chat of the card is read without asking again; pins reach the packet and its replay; untrack keeps the rest.

## Step 4 evidence (S3)

The Inspector's chat page gets a "Status window (this chat)" card beside the memory mode: each window found (its key
count, how many replies, a preview of its values), Track for one not read yet, and for a tracked one the 📌 pins, Save
pins and Stop tracking (a window read by a hand-written card rule says so and offers pins only). Without the chat's
character name nothing can be bound and no button is shown; an older sidecar shows no card. Settings keeps one line on
where a chat's window is set up, every card's rules and the stored JSON folded, and the hand-written rules (draft,
presets, Apply) under "Advanced". Bindings and pins live in `app_config`; an archive carries the bindings with the parser rules, and the pins since
step 5 (below).

Tests (plugin): the card offers, tracks with the card and key set, saves pins, untracks with the rule id; looking
sends no write; no character name, no buttons; an older sidecar, no card; Settings folds both sections.

## Step 5 evidence (A1–A5 against the merged code)

Code: `main` at `1696474` (Phase 41 amendments 2–3, this phase's steps 2–4, #294, #296), plus the archive correction
under A5. Data: a private restored copy of the trial install's backup taken just before its 2026-10-11 update (11
chats, 141 recorded requests, migration 0029), read in read-only sessions. No provider calls; the copy and the
scripts were removed afterwards.

- **A1.** Each card's recurring key set, as the panel would offer it, read by a `shape` rule against the card's bound
  block rule on every reply of its head: the 23-key card 1,127/1,127 values equal on 49 replies, the 9-key card 90/90
  on 10 (one chat on this copy; step 3's copy had two). No value was read by one rule only, and each card showed one
  key set. Over all 11 chats three key sets recur: the two bound windows and a three-key date, time and location
  window of a card without a rule, which is a status window and not a false block.
- **A2.** The synthetic false-positive set (seven texts) and the detector tests pass (`test_status_shape.py`).
- **A3.** Every recorded request replayed under `packet-v18` with `state_changes` off and on, lexical only in both
  lanes (the `<State>` block does not depend on vectors):

  | Requests | Replayable | `<State>` characters (p50) | Keys told (p50) | Packet tokens (p50) |
  |---|---:|---:|---:|---:|
  | 9-key card | 9 of 11 | 0 → 277 (max 464) | 0 → 5 | 205 → 270 |
  | 23-key card, with status observations under the request's rules version | 10 | 0 → 966 | 0 → 7.5 | 2,635 → 3,113 |
  | Chats without a status rule | 35 of 39 | packet text byte-identical, 35/35 | | |

  With the option off nothing is told on these requests, because the bar's message was in context. The 23-key card's
  other 19 replayable requests after its rule have no observations under their recorded rules version on the copy,
  so neither lane tells a status there; its 49 requests from before the rule are outside the comparison.
  Historical gate, cached query vectors, zero provider calls, 338 probes × 3 alternating rounds, `v0.4.0`
  (`41f410d`) against `1696474`, both `packet-v18` with the recorded particle option on: 312/338 in every round of both
  lanes (291/314 recall, 21/24 quotes), no changed majority result, no new forbidden phrase; the majority result,
  tokens, held and placed counts are equal for 338/338. Tokens varied from round to round on 20 probes with `v0.4.0`
  and 4 with `1696474` (the lexical route's timing; test runs shared the host during parts of rounds 1–2). The gate
  copies hold no status rule, so this phase cannot reach them: the gate measures the merges of 2026-10-11 together.
- **A4.** On every replayed request of both cards whose head held a date, time or place key, the value placed with the
  option on equals the latest bar's value as of the request: 19/19 requests, 57/57 keys (27 on the 9-key card, 30 on
  the 23-key card). With the option off none was placed.
- **A5.** Plugin: 244 tests and the typecheck pass (the card offers, tracks with the card and key set, saves pins and
  untracks; looking writes nothing; an older sidecar shows no card; Settings folds both sections). A new archive and
  restore check of a tracked window and its pins **failed on `1696474`**: the export's list of settings
  (`archive.SETTINGS`) held the parser rules but not `status_pins`, so a restored install kept the binding and lost the
  pins. The key is now on the list; the restored install has the pins and compiles the same packet as the source. A
  real panel check on a host remains the owner's, on the trial install where the matching plugin build is loaded.

Tests on this branch: the full sidecar suite, 1,555 passed (local PostgreSQL); plugin 244 passed with the typecheck.

## Out of scope

Extraction prompts, generations, embeddings, provider calls; host-side preset changes; inferring dates or durations;
any change to raw source revisions. Plugin changes are limited to the panel and, if Q4 says so, a literal check.

## Risk

High risk: status-source scope, derived-state rebuild, packet contents, configuration and restore compatibility.
