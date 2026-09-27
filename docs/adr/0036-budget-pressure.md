# 0036 — Budget pressure: say what did not fit, and stop saying things twice

Status: accepted, 2026-09-27. Phase 10 (`docs/phases/PHASE-10.md`), owner request after step 5 ("B+C first").
New default packet policy `packet-v4`; no migration, no new extractor generation. Follows ADR 0027 (ledger and
policies), 0034 and 0035.

## Context

On the owner's recorded requests a 600-token packet placed about 60% of the memory lines retrieval offered;
800, the default since ADR 0035, about 87% with the facts as extracted then. With `extract-v12`'s knowledge marks
the lines are longer: re-read with them, 800 places 74% and every request needs 900–1100
(`docs/perf/budget.md`). The user cannot see this: the Status tab shows the packet, not what was left out, and
Inspector → Retrievals shows fact counts only. The owner asked for the fix to be easy to understand, and chose
two of four options: a notice with a suggested budget (B) and removing lines that say the same thing twice (C).
A more compact line format (D) waits for the response-model evaluation (step 7).

## Decision

1. **What did not fit.** A request counts the memory lines (state, promises, facts, claims, Secret lines) its
   packet left out for the budget (`why = budget`), and, when there are any, finds the smallest budget in steps
   of 100 up to 2000 at which none are left out (`fits_at`), by compiling the same lines again (bisection:
   about 1 ms on the owner's requests, and nothing when nothing is left out). The `/v1/retrieve` answer carries
   `memory: {offered, cut, fits_at}`; the trace records `memory_cut` and `fits_at`; Inspector → Retrievals
   shows "all at N" next to the fact count.
2. **The notice.** When the last request left memory out, the panel's Status tab says how many lines of how
   many did not fit, the budget that holds them all (or that 2000 holds more but not all), and that PocketRisu's
   max context must go down by the same amount (D2). One button sets the plugin's memory budget to it; the
   notice goes away once the budget is at least that. Nothing pops up: on dense chats it would fire on every
   reply.
3. **`packet-v4`** is `packet-v3` without a line that says again what an earlier offered line says: the same
   head (the text before the value) and the same content, such as a fact extracted at two turns, or a
   character's claim whose head a fact has with content this close (trigram overlap ≥ 0.6, ADR 0019's
   match; the narration's line stays, ADR 0013). The ledger keeps such a line as `why = restates` with the
   line it repeats, and costs nothing. Opposite directions are different facts ("A feels toward B" and "B
   feels toward A") and both stay.
4. **Default** `packet-v4`, in the code and both compose files. `packet-v3` stays available and its recorded
   traces replay as before.

## Evidence

`docs/perf/budget.md`.

## Consequences

- Restatements are few: 6 of 135 offered lines on the owner's requests. Most of the gap is closed by the
  budget, which the notice now shows.
- The suggestion is for the last request only. A quiet scene may suggest less than a crowded one.
- A claim that adds a nuance to a fact of the same head ("정말 좋아함" beside "좋아함") is left out as a restatement.
