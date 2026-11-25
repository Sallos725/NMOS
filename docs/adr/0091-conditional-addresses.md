# 0091 — Conditional forms of address (`extract-v20`, `canon-v2`)

Status: accepted, 2026-11-24, PHASE-64. Builds on ADR 0028 (`addresses`), ADR 0038 (per-direction standing facts and
history), ADR 0047 (canon facts and locks), ADR 0081 & 0086 (`ADDS` zero-reextract compiler switches). Migration `0040`.

## Context

`addresses` (ADR 0028) is single-valued per `(subject, object)` direction. Role-play characters routinely switch speech
levels and forms of address by context — formal in public or at work, informal when alone, or under other settled
conditions (missions, disguise, anger, letters). One slot causes four failures:

1. A private form settled later supersedes the public form (`before, turn N: ...`), misleading the response model in
   public scenes.
2. Updating one branch later (e.g. a promotion) overwrites any combined string and drops the other branch.
3. Public titles (`public`) and secret private nicknames (`hidden_from`) cannot carry separate knowledge boundaries.
4. `packet-v12` (`replaced_marks`) treats the still-active public form as superseded and suppresses excerpts mentioning
   it, while Author's Note "Changed from the setting" flags canon's public form as replaced.

## Decision

1. **Separate assertion rows per condition slot, not a merged blob.** Each turn or canon entry records only the
   conditional address(es) it establishes, with its own quote, turn and knowledge marks. Later turns never copy earlier
   surviving conditions, preserving Invariant 7 (editing/deleting a turn removes only that turn's condition), Invariant
   10 (provenance), and Invariant 6 (public title in `<Facts>`, private nickname in `<Private>`).
2. **Closed canonical scopes plus situational label (`assertion.address_condition jsonb`, migration `0040`).**
   - `NULL`: unconditional / general default (all existing rows and non-`addresses` predicates).
   - `{"scope": "public", "when": "<phrase or null>"}`: public / workplace / in front of others.
   - `{"scope": "private", "when": "<phrase or null>"}`: private / alone together.
   - `{"scope": "situational", "when": "<phrase>"}`: any other settled specific condition (`when` required, 1–60 chars,
     normalized casefolded text keys the slot).
   - `{"scope": "all", "when": null}`: explicitly ends a prior conditional split and unifies addressing everywhere.
   Canonical `public` and `private` slots prevent slot fragmentation when later turns phrase the same setting slightly
   differently ("회사에서" vs "공적인 자리"), while `situational` supports arbitrary settled conditions without
   hardcoding an unbounded taxonomy.
3. **Read-side folding (`facts._address_versions`).** All `addresses` assertions for `(subject, object)` still share one
   version key and fold per slot:
   - Each slot keeps its own current value and per-slot history (`earlier`/`first` and `replaced_marks` only see values
     that slot actually superseded).
   - Split cleanup: once both `public` and `private` are active, an earlier `default` row from a prior turn/canon source
     is superseded into the new slot's history so no stale duplicate baseline remains.
   - Unification: a positive `scope="all"` closes all earlier active slots (`default`, `public`, `private`,
     `situational`) and becomes the sole current unconditional address, preserving closed entries in its history.
   - Negations and owner locks (`fact_lock`) operate per slot (`all` still conflicts with any locked slot).
   - `retrieval.replaced_marks` excludes any superseded address form that remains active in another conditional slot for
     the same `(subject, object)` pair, so emotional-slip or private habits reusing a former default form are not
     suppressed from excerpts.
   - Packet selection caps `situational` rows at 3 newest per direction (`SITUATIONAL_ADDRESS_MAX`).
4. **The response model evaluates the condition, never NMOS.** Active conditional rows are rendered in `fact_text` as
   `<subject> addresses <object> [<label>]: <value>` (`default` and `all` omit the bracket). Because all pre-Phase-64
   rows have `address_condition = NULL`, every historical trace replays byte-identically under every packet policy while
   new conditional rows work immediately on both `packet-v19` and `packet-v20` and carry distinct heads for
   `packet.restated`.
5. **Generations (`extract-v20`, `canon-v2`).** `extract-v20` builds on `extract-v19`, keeps `REGISTRY` unchanged so no
   earlier generation key moves, and joins `generations.ADDS` (switching queues zero already-served turns). When
   `extract-v20` is selected, `canonfacts.generation` selects `canon-v2` so character cards and lorebooks extract
   conditional addresses too (`scope="all"` in canon normalizes to `NULL`); under every other compiler, `canon-v1` and
   its pinned key stay unchanged.
6. **Slip guard preserved.** Both prompts include explicitly stated or narrated recurring habits (e.g. involuntarily
   slipping back into a given name when flustered or overcome by emotion) while forbidding inventing a condition from an
   accidental one-off slip or ordinary dialogue (ADR 0028 item 2).

## Consequences

- Switching production from `extract-v19` to `extract-v20` queues zero turn extractions and reads in-force canon once
  under `canon-v2` (deduplicated across chats by Phase 57).
- Rolling back from `extract-v20` to `extract-v19` queues zero turn extractions and reuses existing `canon-v1` reads.
- Two situational rules phrased very differently ("전투 중" vs "싸울 때") occupy separate situational slots until
  unified by `scope="all"` or retracted by the owner.
- An older sidecar image ignores `assertion.address_condition` and inserts `NULL`, keeping rollback safe after switching
  the compiler back first.
