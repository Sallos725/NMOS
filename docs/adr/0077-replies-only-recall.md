# 0077 — Remember AI replies only: a per-chat flag, recall first

Status: accepted, 2026-10-24, PHASE-48 step 2 (owner's Q1–Q6 of 2026-10-15; implementation approved by R8 on
2026-10-23). Extraction and summaries under the flag (step 3) are decided separately.

## Context

In full impersonation the AI writes the persona's lines and actions too, so the user's own message is mostly a
direction to the model ("write it long", "next scene", out-of-character lines, wishes a reroll replaced). Today such a
message is a recall candidate like any other: on the trial install's data, 210 of 817 recorded excerpts (26 %) were
user messages (`docs/perf/phase48-user-messages.md`). The owner asked for a switch per chat that makes memory come
from the AI's replies only.

## Decision

`conversation.replies_only` (migration `0032`, default false), set by `GET`/`PUT /v1/conversations/{id}/replies-only`
and by a toggle in the panel's "this chat" card. It is owner input read by every request of the chat, recorded in each
request's options, so a replay reads the flag its request had (ADR 0027).

With the flag on, no user message of the chat is a recall candidate on any route: one clause, `REPLIES_ONLY`, beside
the eligibility predicates of the lexical scoring, the keyword route's rows, the quote route's own search, the turns a
question names, the turn by which named characters had met, and vector candidates. It sits where each route picks its
rows, before their limits, so a user message takes no reply's place. With the flag off the clause is true for every
row: every route returns what it did.

Switching queues nothing and re-embeds nothing: embeddings and their projection key, the recall query and gating, the
packet policy, raw rows and the Inspector's message list are unchanged.

## Consequences

- Facts and summaries still come from both sides until step 3 (an extractor variant per chat, PHASE-48 S3–S4) is
  built: a direction the extractor read as a fact can still reach the packet (K51).
- One chat's flag changes no other chat (tested).
