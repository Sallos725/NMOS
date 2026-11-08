# 0078 — A model change carries on: summaries served from an earlier generation, the owner's choice redoes

Status: accepted, 2026-11-08, PHASE-57 A2 and A3 (owner's Q1 and Q5 of 2026-11-08). Amends ADR 0014 (extractor
generations: the recent window on every change) and ADR 0042 (summaries read from the active generation only).

## Context

The extraction, summary, canon and reveal generations all hash the extraction model and endpoint, so changing the model
changes all four. Until now each activation queued the latest `extract_backfill` turns of every chat, every due summary
window of every chat, and every chat's canon in force for the new generations. Until the summarizer caught up, a chat
had no summaries, because a summary was read from the active generation only. Startup ran the same activation with no
previous keys, so every start queued that work again for the active generations, and a sync queued every due window
the active summarizer had not written (an edit, a swipe or a delete runs `summaries.schedule` over all windows). An owner
who changes models because one ran out of quota paid most when they could least.

## Decision

1. **Summaries are served like turns (ADR 0014 for summaries).** A due window's scene summary is the active
   summarizer's for the window's key, else the one of the most recently activated earlier `summarize` generation
   (`summaries._SERVES`, `_PREFER`); one generation per window. The story so far is, of each generation's newest story
   made only from served scenes, the one made from the most scenes, the active generation's first. The read-side
   checks (`held`, `leaks`, `unlisted`) apply whatever generation wrote a summary. A summary job still reads its own
   generation's row only (`fallback=False`), so a redo is never skipped for, or discards, an earlier model's summary.
2. **An activation is classified against the generation the database records** (`generations.classify`): `same`,
   `new`, `model` (the spec differs only in `model` or `endpoint`) or `version`.
   - `same` and `new` queue only what no generation serves: a recent-window turn no non-discarded extraction matches
     (`schedule_generation(uncovered=True)`, `OLDER_SERVES`), a due window no summarizer wrote, a canon text no canon
     generation read whole (`canonfacts.WANTED_ANY`; a read the active generation stopped between parts goes on).
   - `model` follows the owner's choice: carry on (the `same` rule), `recent` (the latest `extract_backfill` turns and
     the due windows ending in them, `summaries.schedule_redo`), and `canon` (every chat's canon in force). No choice
     (startup with a changed environment, an older plugin, a script) is carry on without the canon.
   - `version` (a release's version or prompt): facts the latest `extract_backfill` turns as before, summaries the
     windows ending in them, canon every chat's canon (Q5 (a)).
3. **Only the save that chose a redo redoes.** `PUT /v1/config` takes `on_model_change: {"mode": "continue" |
   "recent", "canon": bool}` for that save and stores nothing. Sync-time scheduling (a canon manifest applied, a
   lorebook entry held for the first time) uses the `same` rule; the explicit per-chat actions ("extract all history",
   which now also queues the windows an earlier summarizer serves, "rebuild memory", re-extracting joined turns,
   raising `extract_backfill`) still queue for the active generation.
4. **The panel asks.** `POST /v1/config/preview` works each choice out in a transaction that is rolled back and
   returns `model_change` and the jobs each would queue by kind; the panel shows them when **Save** changes the
   extraction model or endpoint, carry on selected, and sends the answer. A sidecar without the preview saves as before.

## Consequences

- A model change queues nothing by default, then or after a restart; the next packet holds the facts, summaries and
  canon facts it held before. A packet's summaries can come from several models (the Inspector marks a summary written
  by an earlier model, and the coverage counts them, `summaries.older`).
- A chat stays on the old model's reading of its past until the owner asks: "extract all history" per chat, or
  "redo the latest N turns" at the change.
- A release that changes the summarizer now writes the latest turns' windows only, not every window of every chat.
- A replay (ADR 0027) reads summaries as the generations' activation order stands now. A request recorded before this
  change, whose window the active summarizer had not written, replays with an earlier generation's summary there and
  reports `reproduced: false`; a request recorded after it reads what it read.
- The extractor's spec hashes its compiler too; a model whose compiler differs is a `version` change (the latest turns
  again), not a `model` one.
- Tests that relied on a model change re-extracting now ask for it (`on_model_change: {"mode": "recent"}`).
