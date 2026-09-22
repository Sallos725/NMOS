# 0004 — Raw recall scoring and inactive ranges

Status: accepted, 2026-09-22 (Phase 0B implementation choice within PHASE-0 "Raw recall").

## Context

PHASE-0 asks for `pg_trgm` similarity against the last user message "plus the previous AI
message". In manual testing on a 250-message chat, taking the maximum of the two scores (previous-AI
weight 0.7, threshold 0.3) filled the packet with near-duplicate filler that resembled the previous
AI turn, while the out-of-context fact the user asked about scored 0.81 on the user message alone.

PocketRisu excludes `disabled: true` messages from the prompt, and at `disabled: 'allBefore'` it
drops that message and everything before it (`makeMs` in `src/ts/process/index.svelte.ts`).

## Decision

- A candidate must satisfy `word_similarity(user message, content) ≥ NMOS_RECALL_THRESHOLD`
  (default **0.4**, applied through the `<%` operator so the trigram GIN index can be used).
- Ranking score = user score + 0.2 × `word_similarity(previous AI message, content)`; the previous
  AI turn is a tiebreaker, not a filter.
- Candidates: `accepted` revisions in the head membership, after the last `allBefore` cut, not
  `disabled`, not comments, and not in the outgoing prompt (D3). Top 5, then fitted into the
  budget, emitted chronologically.
- Token estimate for the budget: ⌈ASCII chars / 3.5 + non-ASCII chars × 1.5⌉. This is
  conservative for CJK.

## Consequences

- Messages the user hid from the model are never recalled (invariant 7), including ranges cut with
  "Cut Messages for AI".
- Very short user turns ("go on") usually retrieve nothing, which is acceptable for raw recall.
- The threshold and weight are configuration, not schema. They should be retuned on real RP chats.
