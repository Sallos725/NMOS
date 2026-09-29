# 0049 — A packet that fills its budget (`packet-v9`)

Status: accepted, 2026-09-29. Phase 15 step 3 (`docs/phases/PHASE-15.md` Q1–Q4, approved by the owner). A new packet
policy, the default; a new default memory budget and a plugin build. No migration, no generation change.

## Context

`packet-v8` compiles ≈1,800–2,900 tokens at any budget from 2,000 to 20,000 (K33): recall's limits stop it first
(5 excerpts of at most 480 characters, 8 facts, 3 events, 3 threads). On the owner's M0 cases, growing every limit
with the budget answered more cases and, above ≈8,000 tokens, placed stale threads and secrets. Growing only excerpts
and facts kept the gains and held the forbidden phrases steady (`docs/perf/packet-fill.md`). The user already lowers
the host's max context by the budget (D2), so a larger budget trades older raw messages for selected memory; the
prompt keeps its size.

## Decision

1. **`packet-v9` is `packet-v8` whose recall grows with the budget.** With `f = min(max(budget / 2,000, 1), 4)`:
   - excerpts: `floor(top_k × f)` of the request's own `recall_top_k` (the panel's excerpt count), each up to
     `floor(480 × f)` characters, still the two sentences the query matches best (1,920 characters at 8,000);
   - facts: up to `floor(facts_limit × min(f, 2))`; claims follow the fact limit as before (half of it). The
     configured limit selects as `packet-v8` does; the slots the budget adds go only to facts and claims kept from no
     one and not events, in rank order, so secrets, `<Private>` (and strict mode's `<Secret>`) and events do not grow
     (the step's Codex review found the first cut grew them);
   - a limit of 0 stays 0; the candidate pool (50) still bounds the excerpts;
   - threads, events, secrets, `<Cast>` and `<Story>` keep `packet-v8`'s limits and shares.
   At 2,000 and below, `packet-v9` is `packet-v8`: the same lines, the same text.
2. **Recall stops growing at 8,000.** A larger budget is still accepted (the API and stored settings allow 20,000); it
   compiles with 8,000's limits, and the packet still stops at the budget, ranking deciding what fits.
3. **Replays.** A request records its configured limits, as before, and the growth its budget bought (`fill` in its
   recall options); a replay grows the limits again from the budget it compiles at. A request recorded under
   `packet-v8` replays as `packet-v8` (ADR 0027); `tools/replay_packets.py` and `audit.compare` compare the two.
4. **The default.** `packet-v9` is the default policy. The plugin's default budget is 4,000 tokens (from 2,000),
   fixed, not the host's context (owner, 2026-09-29: a share of a 500,000-token preset would be past the measured
   range). The panel saves up to 8,000 (a budget stored above it is still read, up to the API's 20,000), and the
   budget advice (ADR 0036) searches up to the same 8,000 (`FIT_CAP`, 6,000 before). The reminder stays: lower the host's max context by the budget (D2).

## Consequences

- A user who never set the budget gets 4,000 tokens of memory after updating the plugin, and should lower the host's
  max context by 2,000 more; one who set a budget keeps it. Nothing is re-extracted.
- At 4,000 tokens a packet holds up to 10 excerpts of up to 960 characters and 16 facts.
- The budget advice's suggestion is the budget at which what this request was offered fits; at that budget recall
  offers more, so it is a floor, as before.
- Measurements (M0 with both extractions, the owner's traces, latency, a real-host smoke) are PHASE-15 step 5.
