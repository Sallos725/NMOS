# Owner repair — measurements (Phase 13, Stage 6 part 1)

Phase 13 (`docs/phases/PHASE-13.md`) lets the owner repair memory: close or reopen a thread, retract or correct a
fact, mark a secret found out, split two names. This file records what it is measured against. Numbers only: what
the chat says stays outside the repository (the owner's lists and the scripts that use them are with the M0 cases).

## The owner's lists (step 2, 2026-09-28)

The restored copy of the owner's backup (PHASE-11 Q1; read-only), its longest chat (74 turns, 147 messages), as
`extract-v13` read it. NMOS drafted a decision for every open thread and every secret still kept from someone, with
the turns that suggest it; the owner confirmed the draft as it was.

| | Open or kept now | The owner's decision |
|---|---:|---|
| Threads (37 goals, 10 questions, 12 promises) | 59 | 50 ended in the story (closed at the turn that ends them), 9 still under way |
| Secrets (of 19; 5 already ended) | 14 | 6 found out by the character they were kept from, 2 never kept (the character was only away), 6 still kept |

- Of the 50 ended threads, one is the "end matching no open thread" of that chat that has a thread to match (the
  closing turn named the thread's counterpart as its maker); the other 8 unmatched ends have no open thread.
- The 9 still under way are daily or repeated plans, plans for later the same day, a secret still being kept and a
  wish not yet met.

## Baseline on `main` (step 2, 54f896a)

`packet-v8`, budget 2,000, no vectors, the chat's recorded requests with the M0 cases' messages (40 cases:
`docs/perf/m0-baseline.md`, `docs/perf/summaries.md`).

| | `main` |
|---|---:|
| M0, 28 cases (need memory) | 26 (7 of 9) |
| M0, 12 cases outside the prompt window | 5 |
| Secret gate: scenes with no forbidden word in `<Story>` | 6 of 6 |
| Secret gate: scenes with `<Story>` at all | 0 of 6 |
| Packets carrying a thread the owner closed | 40 of 40 |
| Lines of threads the owner closed, in all 40 packets | 113 (16 distinct threads) |
| Lines of threads the owner kept open, in all 40 packets | 64 |

Every packet carries at least one thread the story ended long before; the step's measure is that none does once the
owner's repairs are applied. `<Story>` is held in all six gate scenes: with the stricter check in front of a character
a secret is kept from (ADR 0042 amendment 3), secrets the story already told still hold it; marking them found out
should let it back where no secret remains, with no forbidden word.
