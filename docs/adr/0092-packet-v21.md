# 0092 — `packet-v21`: secrets gated on every line, a wider cast, quotes only when asked, standing facts that never rest

Status: accepted, 2026-11-25, PHASE-65 (S10). The owner's plan, decisions 1 and 5–7. Not the default:
`packet.DEFAULT_POLICY` stays `packet-v19`; making it the default waits for the replay of `AGENTS.md §7` item 6 and
the owner. Builds on ADR 0082 (`packet-v20`), 0067 (the quote route), 0068 (rest), 0034 (`<Private>`), 0035 (strict
and narrator), 0081 (feeling), 0091 (conditional addresses). Recorded as built at `361130c`.

## Context

ADR 0027 versions the packet compiler by policy and leaves the gathering code unversioned. The audit found selection
faults that a bug fix under the existing policies would change for every recorded request: the quote route starting on
quoted dialogue and taking the excerpt reserve with it (E1), keywords cut twice (E2), a reranker fed the short message
and overruled by the fused floor (E3), secrets told by an ordinary excerpt, a status value, a `because` clause or a
settled thread (C3), a strict mode that hid an NPC's unspoken feeling from the model playing them (E5), `<Cast>`
without the persona or the forms of address (E4, C8), the feeling detail of `extract-v18` never printed (A4), gone
pins lifted by a dream or a rumour (E6), rest that silenced how two people stand and counted rerolls (E7), a replaced
value dropping unrelated excerpts (E8), closed regression threads never offered (F1). The owner's decision 1 put
these behind a new policy so `packet-v20` and older replay as they were.

## Decision

1. **`packet-v21` is `packet-v20` plus what only it does.** It joins every `*_POLICIES` set `packet-v20` is in, and
   each addition is gated on `V21_POLICIES = {"packet-v21"}` (`packet.py`, `retrieval.py`), so `packet-v20` and older
   compile and gather as before (differentials in PHASE-65 criterion 2).
2. **Secrets, on every line a scene may read.** Every excerpt and quote is checked against the secrets still kept from
   someone present (`summaries.leaks`): in normal mode it is fenced in `<Private>` with its knowledge marks, in strict
   and narrator modes withheld as `secret_gate`. A `<State>` or `<StateHistory>` value that repeats such a secret is
   withheld, unless it has fewer than 3 letters (`STATE_GATE_LETTERS`). A public fact line drops a `because`,
   `disputed_by`, `before` or `first` clause that repeats one (`entry_v21`; gone lines too). A settled thread reads
   under its closing's knowledge marks (`closed_by`, PHASE-65 S2) when they are narrower. A `told` line reads
   whom the telling is about and is gated only for a kept-from character present. In strict mode a `feels_toward`
   that is limited and kept from no one by name stays readable in `<Private>`: an unspoken feeling is not a plotted
   secret.
3. **`<Cast>`.** It reads 4 turns (`CAST_TURNS_V21`). Each group may also hold the character's feelings toward and
   forms of address for other scene characters (`CAST_PEERS` = 2 per group), and the persona gets a group (where they
   are, their condition, what they carry). A pair's address slots (ADR 0091) enter together, each with its label, or
   not at all; a pair with a slot the scene may not read keeps all its forms out of `<Cast>` (they stay in lead and
   `<Private>`). These extra lines are placed after every line `packet-v20`'s groups hold, within `CAST_EXTRA_SHARE`
   (0.15) of the inner budget counted from where that pass ended, never into the room held for lead and `<Private>`;
   an unplaced one is marked `cast_cap`. A fact `<Cast>` or a gone pin already says is not said again, and the next
   one takes its slot.
4. **Feeling and names.** A `feels_toward` line carries its feeling detail. A title the persona uses for exactly one
   character (at most 8 characters, `TITLE_MAX_CHARS`) is an alias of that character for the request; `@name` pins by
   name variants (ADR 0058). A first-person message brings the persona's own aims, questions and threats, and the
   persona's settled threads are listed.
5. **The quote route and keywords.** A message asks for words only beside a question or recall cue read outside the
   quoted words (`quotes.asks_for_words(v21=True)`); a `<Quote>` longer than the excerpt share leaves the reserve to the
   first excerpt that fits. Keywords strip at most one question ending and one particle that fits the final
   consonant, keep tokens with digits and demote literary verb endings (`keywords(v21=True)`). Speakers are read from
   any generation that recorded them, the one in use first.
6. **The reranker** reads the text the query was embedded with (`sem_query`, ADR 0084) and each candidate's matched
   vector chunk padded by 200 characters (`RERANK_DOC_PAD`); after a rerank its order decides what clears
   `EXCERPT_FLOOR`.
7. **Gone and the return gap** read only rows that show the character present: narrated, actual, as the subject
   (`presence_rows`), with `gone.py`'s v21 word lists; a death carried by a `continue` link stays pinned.
8. **Rest.** Rerolls of one turn count once and the current request's earlier attempts not at all
   (`overuse.recent(dedupe_positions=True, exclude_position=…)`); `addresses`, `feels_toward`, `relationship`,
   `role_toward` and settled threads never rest. `audit.replay` passes the same arguments under `packet-v21`, so a
   replay matches the live request.
9. **What changed.** A replaced value drops an excerpt only when the excerpt names the fact's subject (any of its
   names); `when_happened` is scored on a temporal question (`TEMPORAL_CUE_V21`); a history cue keeps a standing fact
   whose earlier versions lie outside the window.
10. **Budget.** A supportive summary yields to the lead lines and `<Private>`; the story so far keeps its place
    (required continuity, owner 2026-10-07).
11. **Regression.** Closed regression threads reach `<Regression>` (`carry.regression_threads`); a promise kept or
    broken in that timeline is remembered.
12. **Status questions.** A message that names no character any key is prefixed with asks that key of every window
    (`asked_keys(every_window=True)`, ADR 0094). Earlier policies ask none of them (PHASE-39 Q3b).

## Consequences

- No generation key, prompt or stored row changes; the policy is a setting (`NMOS_PACKET_POLICY`).
- A `packet-v21` request can be longer in `<Cast>` and `<Private>` and shorter in `<Excerpt>`; its secret gates are
  instructions and fences, not isolation (K11; hard POV is not authorized).
- `tools/replay_sequence.py` builds its own `recent` without collapsing rerolls, so a sequence replay under
  `packet-v21` rests differently from the live request (K55).
- Not gated: a claim's `because` clause (claims render through `claim_entry`). The title lookup reads titles from the
  persona only (the cast is not known when aliases are made, and the cast reads them). Only supportive summaries yield.
- `CUT_RISK` (0.5) only forbids shortening an excerpt that would cross a secret's bar once cut; it drops nothing.
- Measurement: none yet. The replay of an earlier gate's databases under `packet-v20` / `packet-v19` beside
  `packet-v21` comes before any default change.
