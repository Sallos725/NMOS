# 0042 — `packet-v7`: the story so far and the scene's characters, with a 2,000-token default budget

Status: accepted, 2026-09-28. Phase 12 step 5 (`docs/phases/PHASE-12.md`, Q3, Q4, Q5; the owner's budget decision).
New default packet policy `packet-v7`. Summaries on by default (`NMOS_SUMMARIES`). Default memory budget 2,000 tokens
(was 800). Amends ADR 0035 (the default budget) and ADR 0036 (`FIT_CAP`). ADR 0041 amendment 2 (late secrets) belongs
to the same step.

## Context

- **The budget.** At 800 tokens the Story share of 30 % is 204 tokens. On the owner's longest chat the story so far
  took 285 tokens, and a scene summary took 190–305 (`docs/perf/summaries.md`). Neither fit. The owner noted that
  RisuAI presets usually keep about 50,000 tokens of context, and that memory cut to NMOS's small defaults works
  poorly. The owner chose 2,000 (2026-09-28).
- **The characters.** Facts are ranked for the message (ADR 0026). A character in the scene whose place, condition or
  items the message does not mention can be left out.

## Decision

1. **`packet-v7` (default)** is `packet-v6` with two sections.
   - **`<Story>`** comes first in the packet, and is placed after parser state in at most 30 % of the budget inside
     the frame. It holds the story so far, then the scene summary the message is about. That scene summary is the
     best trigram containment of the message (at least 0.3), among windows that end before the prompt's own first
     turn.
     - A summary held under ADR 0041 (it repeats a secret, or was written before one) is never offered.
     - Narrator mode offers none (PHASE-12 Q3).
     - The line is `<Summary kind="story|scene" turns="a–b">`, with a Note sentence saying that summaries are the
       earlier story in short.
   - **`<Cast>`** comes after state, before threads. For up to 4 scene characters (ADR 0034), the persona left out, it
     groups the lines that are that character's current place, condition, feeling toward the persona, what they carry
     (at most 3), and open goals (at most 2).
     - Goals are grouped only for a character the message names: an open goal can be long over without a turn
       saying so (K23), and the first M0 run carried a finished goal into an unrelated question.
     - Lines only some of the scene know stay in their section, with its Private handling. A narrator's unknowns
       are left out.
     - The lines are the ordinary fact and thread lines, with their provenance in the ledger (section `cast`). They
       are not repeated in `<Facts>` or `<Threads>`.
2. **Recorded requests** keep their policy, and a replay compiles them the same way. The trace records the summarize
   generation it used (`summarize_key`, a recorded recall option). A replay reads summaries and windows as of the
   request.
3. **Default budget 2,000** (plugin `reserved_memory_tokens`, when unset). A value saved in the plugin stays as it
   is. `FIT_CAP` (the largest budget the panel suggests) goes from 2,000 to 6,000.
4. **Summaries are on by default** where extraction is on. `NMOS_SUMMARIES=0` or the `summaries` setting turns them
   off. Turning them on makes the summarize generation active and queues every chat's due windows at background
   priority (ADR 0041, PHASE-12 Q7).

## Consequences

- Each request's prompt can carry up to 2,000 memory tokens, 1,200 more than before. That is about 4 % of a
  50,000-token preset.
- **M0 on the restored copy** (`docs/perf/summaries.md`, `gemma4` extraction):
  - on the owner's 12 cases outside the prompt window, 2 of 12 → 5 of 12 (4 of 12 from the budget alone);
  - on the 28 earlier cases, 26 of 28 as before, with nothing forbidden placed as current.
  - The M0 scorer counts `<Story>` text as past, as it counts "; before, turn N".
- A secret the summaries do not keep in other words can still reach `<Story>`; KNOWN-ISSUES K30.
