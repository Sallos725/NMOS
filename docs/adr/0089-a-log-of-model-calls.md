# ADR 0089: A log of model calls

Date: 2026-11-24. Status: accepted (PHASE-61 amendment 2, owner 2026-11-24).

## Context

The worker's model calls can fail for hours (a provider's rate limit, a gateway timeout) while the only record is a
job's `last_error`, which the next attempt overwrites and which is deleted with the job, and the container's log,
which is lost whenever the container is replaced. Usage is kept only with the rows a successful call wrote
(ADR 0051). The owner could not tell a slow model from a failing one, and asked for a log on the server.

## Decision

1. **A table, `model_call`** (migration `0039`): one row per model call made outside the request path, with its
   time, kind, conversation and job when known, generation, model, endpoint identity, outcome, HTTP status, duration,
   reported usage and, for a failure, the first 300 characters of the provider's error.
2. **Metadata only.** No prompt, reply or chat text and no credential is ever written. A reply that cannot be read
   is recorded by the kind of fault, never by its text.
3. **Outside the job's transaction, bounded, fail open.** A log row survives the failure it describes; a failure to
   write it never fails or delays a call beyond a short bound.
4. **Not on the request path.** `/v1/retrieve` writes no row; its embedding and rerank times are in the trace.
5. **Operational data.** It is kept as long as traces are, is never archived, and goes with its chat when the chat
   is deleted (`ON DELETE CASCADE`).

## Consequences

- The Status tab and the Inspector can say what the model has been doing over the last hour and list recent calls.
- One more write per worker call; none per request.
- Forward-only like every migration: an older image ignores the table, and its chat delete still works through the
  cascade.
