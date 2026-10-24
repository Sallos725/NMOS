# Phase 51 — How long a thread lasts: a horizon recorded at extraction

Status: **draft**, 2026-10-23 (AGE-89). An owner request that came out of Phase 50 (amendment 3), not a roadmap stage. Not
**R8 (owner, 2026-10-23, AGE-90): approved for implementation in `0.5.0`,** with Phase 45 as `extract-v17`; the "after 1.0.0" below is superseded (`docs/ROADMAP-1.0.md` R8).
approved for implementation. **Q1–Q6 answered (owner, 2026-10-23): all as recommended.**
**After 1.0.0**, with the next extractor-generation change: it is an extraction change (a "heavy change" under
`docs/ROADMAP-1.0.md`), and Phase 45 (speakers, held on 2026-10-13 for the same reason) waits for that generation too,
so both are proposed as one generation and one re-extraction (Q5).

The owner asked (2026-10-23) whether NMOS can tell an important debt or promise from a passing one. It cannot: a
thread (a promise, goal, question, threat or debt) carries no importance, and an open one is "old" only by the turns
since it was last said.

**High risk if built** (`AGENTS.md §14`):
- a new extractor generation (re-extraction of every chat's recent window, at the provider's cost);
- a change to what memory selects (the Inspector's "needs a look", the author's note, and, if Q3 says so, the
  packet's threads).

**Step 2 built, 2026-10-24** (branch `claude/extract-v17`, with Phase 45): a thread takes its opening row's horizon
(a restatement with another one changes it); `inspector.stale` is by horizon (`HORIZON_TURNS`: scene 10, arc 30,
lasting never, none 30), and the Inspector's "needs a look", the author's note and the panel's memory follow it; the
Inspector's threads and the memory screen name the horizon. A parity test runs 2,000 random threads without a horizon
through the old and the new rule: the same. `extract-v17` asks for `horizon` beside `outcome` and `because` (S4) and
stores it only under that compiler; `extract-v16`'s prompt and key are unchanged. Step 3 (paid) waits for the owner.

**Step 3 measured, 2026-10-25** (paid, $15.67; with PHASE-45's step 3 under the owner's $90 cap). A test-install copy
reduced to its three longest chats (76, 60 and 49 turns), extracted three times under `extract-v17` on Gemini 3.8
Flash (one turn of 185 in one run failed). Numbers only:
- **Stability:** threads of run 1 matched in another run by maker, kind and text (`threads.similarity` ≥ 0.5) carried
  the same horizon in 60 of 65 matches (92 %); 20 of the 23 found in all three runs had one horizon throughout. Runs
  differ more in which threads they open at all (39–47 in the longest chat) than in how long one lasts.
- **The longest chat's open threads** (16–20 a run): `scene` 5–7, `arc` 6–7, `lasting` 3–4, none 1–5 (an opening the
  model left unlabeled keeps the 30-turn rule). Left out of the note: 8–11 by the 30-turn rule, 11–12 by horizon; every
  `lasting` one stays, every `scene` one older than 10 turns goes. The other two chats: 3–6 open, 1–3 left out by
  horizon against 2–5 by the old rule.
- **The owner's labels** of a sample: asked 2026-10-25.

**Amendment 1 (2026-10-24): a migration after all.** S2 and Q2 (a) assumed `assertion.salience` takes the horizon
without a migration; migration `0016` limits it to `major`/`minor` by a check. Migration `0030`, which Phase 45 needs
anyway for `extraction.speakers`, widens the check to the horizon words. No new column, so Q2's choice stands; the
restore rule is the one of any migration (an archive of `0030` is refused by an older build as newer).

## Why

1. **Every thread weighs the same.** `salience` (`major`/`minor`) is asked for `event` only (ADR 0020, ADR 0024);
   `predicates.salience` drops it from every other predicate. The packet picks threads (`threads.relevant_threads`) by
   whether the message or the last reply names their maker or recipient, then newest first; the Inspector's "needs a look" (`inspector.stale`, PHASE-13 Q6) and the
   author's note (Phase 50 amendment 3) use one rule: an open thread not said again for more than 30 turns.
2. **One rule is wrong both ways** (the test install's copy, read on 2026-10-23, counts only): the longest chat (76
   turns) had 34 open threads, 21 of them older than 30 turns. Among those were a same-afternoon appointment from
   turn 2, plainly over, and a lifelong debt from turn 6, plainly not. A 13-turn chat had a goal opened at turn 6 that
   its own scene summary told as done by turn 7; 30 turns cannot catch that, because the thread is young.
3. **What decides when a thread can go is how long it is meant to last**, more than how important it is: an
   appointment for this afternoon is over by the next scene whether it mattered or not; a vow or a debt for life stays
   open until the story ends it. The extractor reads the turn where the thread opens and can say which it is.

## Proposal

S1. **A horizon on each thread** (Q1), asked by the extractor where a thread opens (`promised`, `goal`, `question`,
`threat`, `owes`):
- `scene`: meant to end within the scene or the day (an appointment this afternoon, a question about what is in front
  of them);
- `arc`: a storyline over several scenes (find the archive, win the match next week);
- `lasting`: open until the story ends it (a debt for life, a vow, a lifelong goal).

S2. **Stored without a migration** (Q2): in `assertion.salience`, which already exists (migration 0016). Its
vocabulary depends on the predicate: `major`/`minor` for `event`, `scene`/`arc`/`lasting` for the thread predicates;
`predicates.salience` validates by predicate and stores anything else as NULL, as it does now. Rows of older
generations stay NULL (no horizon).

S3. **Read side.** A thread takes the horizon of the assertion that opened it (`threads.fold`; a restatement with
another horizon updates it). `inspector.stale` becomes the one rule every reader uses, by horizon (Q4): `scene` after
10 turns not said again, `arc` after 30 (today's rule), `lasting` never; a thread with no horizon keeps 30. Readers:
the Inspector's "needs a look", the author's note (Phase 50), and, only if Q3 says so, the packet.

S4. **The extraction prompt** asks for the horizon in the same item, beside `outcome` and `because`, with one short
example of each. The generation is `extract-v17`, together with Phase 45's speakers (Q5).

## Out of scope

- Closing threads the story finished without saying so (the 13-turn chat's goal). That is the extractor not
  reporting an end (`resolved`, `fulfilled`); a horizon only makes such threads leave sooner. A later phase can offer,
  in the Inspector, the open threads a scene summary tells as done.
- Importance (`major`/`minor`) for threads. If the owner wants it as well (Q1 (c)), it is a second field.
- Changing the packet's thread ranking without the owner's answer to Q3.

## Questions for the owner

- **Q1 — what to record. Answered (owner, 2026-10-23): (a).**
  - (a) **Recommended:** the horizon (`scene`/`arc`/`lasting`). It decides when a thread may leave the note and the
    "needs a look" list, which is what the owner saw go wrong.
  - (b) Importance (`major`/`minor`), as events have. It ranks, but an important appointment for this afternoon is
    still over tomorrow.
  - (c) Both: two fields, a larger prompt change.
- **Q2 — where it is stored. Answered (owner, 2026-10-23): (a).** (a) **Recommended:** `assertion.salience`, its vocabulary by predicate: no migration.
  (b) A new column `horizon`: clearer, but a migration on stored derived data (high risk, restore compatibility).
- **Q3 — who reads it. Answered (owner, 2026-10-23): (a).** (a) **Recommended:** the Inspector and the author's note first; the packet unchanged. (b)
  Also the packet: an open `lasting` thread ranks before others on a tie, a `scene` thread past its horizon drops out.
  That is a packet policy (`packet-v20`) and needs the recall replay gate.
- **Q4 — how long each lasts. Answered (owner, 2026-10-23): (a).** (a) **Recommended:** `scene` 10 turns, `arc` 30, `lasting` never, unlabeled 30.
  (b) Other numbers; the step 3 measurement can suggest them.
- **Q5 — the generation. Answered (owner, 2026-10-23): (a).** (a) **Recommended:** one `extract-v17` with Phase 45's speakers, one re-extraction and one
  live gate. (b) A generation of its own (a second re-extraction).
- **Q6 — older turns. Answered (owner, 2026-10-23): (a).** Rows from before `extract-v17` have no horizon and keep the 30-turn rule; only the recent
  window is re-extracted by the generation change. (a) **Recommended:** as is; the owner can run "Extract all history"
  on a chat to label all of it. (b) Re-extract every chat's whole history (cost per chat, estimated first).

## Steps

1. **Spec** (this file): Q1–Q6 answered (2026-10-23); approval to implement (after 1.0.0).
2. **Read side**, no model: `threads.fold` carries the horizon, `inspector.stale` by horizon, the author's note and the
   Inspector use it; tests on synthetic threads; unlabeled threads behave exactly as on `main`.
3. **Measurement before the generation** (paid, estimated first): on a test-install copy, the horizon prompt on the
   open threads of three chats, three runs; the owner labels a sample by role and number only (public repository);
   agreement and run-to-run stability reported, and how many open threads each rule would leave in the note.
4. **The generation** `extract-v17` (with Phase 45), its migration-free validation, and the full live gate.

## Acceptance criteria

- A thread without a horizon is treated exactly as today (30 turns), in the Inspector and the note (test).
- With the horizon, the longest test-install chat's note keeps every `lasting` open thread and none of the `scene`
  threads older than 10 turns (step 3's copy).
- The horizon's label agrees with the owner's on most of the sampled threads and is stable across runs (bars set with
  the owner before step 3).
- The full live gate passes on `extract-v17`.
