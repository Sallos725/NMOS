# Phase 64 — Conditional forms of address

Status: **approved**, 2026-11-24 (owner, in the design conversation of 2026-11-24: `default` / `public` / `private` +
`situational` + `all`, canon included, build now). An owner request, not a roadmap stage. Numbered 64 because Phase 63
(`docs/phase63-scene-contrast`) was allocated and closed earlier the same day.

**High risk** (`AGENTS.md §14`):
- **a new extractor generation (`extract-v20`) and canon generation (`canon-v2`)**: prompt changes, so new generation
  keys (D20); switching to `extract-v20` from `extract-v16`/`v18`/`v19` queues no already-served turns (`ADDS`), while
  `canon-v2` reads in-force canon once (deduplicated across chats by Phase 57);
- **a migration (`0040_address_condition.sql`)**: adds nullable `assertion.address_condition jsonb` with a CHECK
  constraint;
- **fact folding and memory selection**: `addresses` gains per-condition slots at read time (`facts._address_versions`),
  locks (`_changes`), repairs (`repairs.py`), dropped-fact comparison (`dropped.py`), secrets (`secrets.py`), carried
  memory (`carry.py`), and packet rendering (`facts.fact_text`).

Invariants it touches (`AGENTS.md §3`):
- **Inactive sources cannot influence generation (Invariant 7) & Provenance (Invariant 10)**: each conditional address is
  its own assertion row from the turn or canon entry that settled it — later turns never copy earlier surviving
  conditions into their own row, so editing or deleting a turn cleanly removes only that turn's condition.
- **Character knowledge ≠ world knowledge (Invariant 6)**: separate rows per condition let a public title stay `public`
  while a private pet name carries `limited` / `hidden_from` into `<Private>` and stays out of ungated Author's Notes.
- **Current and historical state both answerable (Invariant 5)**: changing the public title supersedes only the public
  slot while keeping the private slot current and keeping history per slot; unifying with `scope="all"` closes earlier
  slots and keeps them in history.
- **Unknown is a valid result (Invariant 4)**: unconditional addresses keep `address_condition = NULL`, and NMOS never
  guesses whether the current scene is public or private — it hands all active conditional forms to the response model.

## Why

`addresses` (ADR 0028) holds one current value per `(subject, object)` direction. In role-play, characters frequently
use different speech levels and forms of address depending on context — formal title in public or at work, informal
speech or pet name when alone, or other settled situational rules (during missions, in disguise, when angry, in
letters). With one slot:

1. Settling a private form supersedes the public form (`before, turn N: ...`), causing the response model to use the
   private form in public.
2. Updating one branch later (e.g. a work promotion) overwrites any combined free-text string and wipes out the other
   branch.
3. Public titles (`public`) and secret private nicknames (`hidden_from`) cannot have separate knowledge marks.
4. `packet-v12`'s `replaced_marks` suppresses older excerpts quoting the "superseded" form, and the Author's Note's
   "Changed from the setting" falsely reports canon's public title as replaced.

## What it does

S1. **Data shape and migration (`0040_address_condition.sql`).** Nullable `assertion.address_condition jsonb` holding
`{"scope": "public|private|situational|all", "when": "<phrase or null>"}` for `addresses` assertions only:
- `NULL` (default): unconditional / general form of address (all existing rows and non-`addresses` predicates).
- `public`: public, workplace, formal settings or in front of others (`when` optional, ≤ 60 chars).
- `private`: private settings or when alone together (`when` optional, ≤ 60 chars).
- `situational`: any other settled specific condition (`when` required, 1–60 chars, normalized for slot keying).
- `all`: explicitly ends a prior conditional split and unifies addressing everywhere (`when` always `null`).

S2. **`extract-v20` (selectable, not default).** Built on `extract-v19` (keeping `feeling`, `when_happened`, `story_clock`,
`told`, roles, name pairs). Adds `ADDRESS_CONDITION_RULE` and the `address_condition` JSON field, covering both agreed
situational rules and explicitly stated/narrated recurring habits (such as involuntarily slipping back into a given name
when flustered or overcome by emotion), while preserving ADR 0028's "a slip is not a change" guard against accidental
one-off slips. Joins `generations.ADDS`, so switching among `extract-v16`, `extract-v18`, `extract-v19` and
`extract-v20` queues no already-served turns. Earlier generation keys (`extract-v15`..`v19`, `canon-v1`, `summarize`,
`reveal`, `embed`) stay pinned and byte-identical.

S3. **`canon-v2` (paired with `extract-v20`).** When `extract-v20` is selected, `canonfacts.generation` produces
`canon-v2` (`PROMPT_V2`), asking for `address_condition` (`public`, `private`, `situational`) on `addresses` facts from
cards, lorebooks, notes and personas. Any `scope="all"` in canon degrades to `NULL` (default). Under all other
compilers, `canon-v1` and its pinned generation key are unchanged.

S4. **Read-side folding (`facts._address_versions`).** All `addresses` assertions for `(subject, object)` still share one
version key and fold chronologically across slots:
- Without any `address_condition` in history, folding is identical to today.
- `default`, `public`, `private`, and each normalized `situational` phrase maintain independent current slots and
  per-slot history (so `before:`/`first:` and `replaced_marks` only see what that slot actually replaced).
- Split cleanup: when both `public` and `private` are active and an earlier `default` exists from an earlier turn/canon
  source, that earlier `default` is superseded into the newly-arriving slot's history so no duplicate baseline lingers.
- Unification: a positive `scope="all"` closes all earlier active slots (`default`, `public`, `private`, `situational`)
  and becomes the sole current unconditional address, retaining closed entries in its history.
- Negation closes only the matching slot.
- Owner locks (`fact_lock`) hold off only the locked slot and `all`, never other slots.
- Active-slot guard in `retrieval.replaced_marks`: a superseded address form (e.g. a past default given name) is not
  marked obsolete for excerpt suppression if another active conditional slot for the same pair still uses it.
- Packet selection caps `situational` addresses at 3 newest per direction (`SITUATIONAL_ADDRESS_MAX`) so a pathological
  extraction cannot flood the packet; the Inspector and Panel still show all.

S5. **Packet, Author's Note, Panel, Inspector, Timeline, Repairs, Carry.**
- `facts.fact_text` and `secrets.secret_text` format conditional addresses as `<subject> addresses <object> [<label>]: <value>`
  (`label` is `when` when set, else `in public` / `in private`; `default` and `all` print no bracket). Because every
  pre-Phase-64 row has `address_condition = NULL`, all existing packets and historical replays remain byte-identical under
  every policy (`packet-v0`..`packet-v20`), while conditional rows render cleanly under both `packet-v19` and `packet-v20`
  and keep distinct `_head` values for `packet.restated`.
- `notes.py`, `inspector.py`, `views.py` (Memory document, Person sheet, Memory map), `timeline.py`, `repairs.py`,
  `dropped.py`, `endings.py`, `carry.py`, and `archive.py` carry and display `address_condition`.

## Out of scope

- Evaluating whether the current scene is public or private at `beforeRequest` (the response model decides).
- Showing `CURRENT ADDRESSES` in the extraction prompt or adding confirmation calls for address endings.
- Changing the code default compiler (`extract-v16`) or default packet policy (`packet-v19`).
- Plugin changes (the panel renders sidecar HTML; plugin build stays unchanged).
- Paid evaluation runs (zero-call tests and the owner's live trial are the check, as in Phases 58–62).

## Acceptance criteria

1. Migration `0040_address_condition.sql` applies cleanly to fresh databases and every upgrade fixture in
   `fixtures/upgrade/`, preserving existing row counts and id hashes with `NULL` on existing rows, and rejects malformed
   `address_condition` payloads.
2. Every pinned generation key in `test_phase60_pins.py`, `test_phase61_pins.py` and `test_phase62_long_replies.py`
   remains byte-identical.
3. `extract-v20` prompt growth over `extract-v19` is under 15 %; switching among `extract-v16`, `extract-v18`,
   `extract-v19` and `extract-v20` is classified `adds` and queues zero already-served turns.
4. `canon-v2` activates with `extract-v20`, extracts conditional addresses from canon, copies `address_condition` on
   Phase 57 reuse, and leaves `canon-v1` untouched for all other compilers.
5. Folding satisfies every scenario: default+private coexist, default+public coexist, split-cleanup retires stale default
   once both public and private exist, `scope="all"` unifies and rollback/delete restores prior branches, situational
   slots coexist and update independently, negations and locks stay slot-scoped, and independent knowledge marks route
   private addresses to `<Private>` and keep them out of secret-off Author's Notes.
6. Archives export and restore `address_condition` losslessly; carry links preserve it; dropped-fact restore preserves it.
7. Historical traces replay byte-identically; full sidecar suite (`NMOS_TEST_REQUIRE_DB=1`) and docs consistency pass.

## Stop conditions

- Any earlier pinned generation key moves: stop and fix before proceeding.
- Switching between `extract-v19` and `extract-v20` queues already-served turns: stop and fix.
- `extract-v20` prompt grows by more than 15 % over `extract-v19`: tighten wording before shipping.
- Any existing replay or upgrade fixture regresses: stop and fix.
