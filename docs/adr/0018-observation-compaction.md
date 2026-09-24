# 0018 — Lossless compaction of full-manifest host observations

Status: accepted, 2026-09-24. Implements the rest of owner decision O5 (`docs/phases/PHASE-6.md`, Q5:
compact full-manifest observations losslessly, keep everything else). Decision D31. Known issue K17.
Migration 0015.

## Context

Every sync that creates a commit (an edit, reroll, swipe, delete or disable) stores the host manifest
it observed as a `host_observation`, one row per message. Appends store only the appended tail with
the base manifest hash (ADR 0010). At 10,000 messages a full observation takes ≈1.1 MB on disk
(1.7 MB as text); the commit itself is under 1 KB. A hundred rerolls add ≈110 MB. Observations are
evidence of what the host sent. They are not derived data, so they must not be dropped, and nothing
may be lost when they are shrunk.

## Decision

1. **A full observation may be stored as a difference.** The compact form keeps every key of the
   observation except `entries` and adds `base_observation` (the id of a full observation of the same
   chat), `length` (the manifest's row count) and `changed` (`[index, row]` for every row that differs
   from the base at that index or lies beyond the base's end). The rows are the base's first `length`
   rows with `changed` applied (`retention.apply_diff`, read by `retention.observed_rows`).
2. **Bases.** Per chat, in id order, each full observation not yet decided is either kept full as the
   chat's next base, or stored against the latest base before it. It stays full when it is the chat's
   first, when its columns differ from the base's, or when more than 25 % of its rows differ. The rows
   differ that much after a large divergence, or after many messages were appended since the base.
   A base is never compacted, so rebuilding an observation reads at most two rows. The decisions go
   to `observation_base` (bookkeeping, not evidence; it is removed with its observation, and
   re-running compaction from an empty table reaches the same state).
3. **Only if exact.** A difference is written only when applying it to the base gives exactly the
   original rows. Otherwise the observation stays full.
4. **Off the request path.** The worker does it in its 10-minute maintenance pass (200 observations per
   pass, one transaction each). Sync, reconcile and their latency are unchanged, and existing
   databases are compacted by the same pass.
5. **Everything else is kept.** Appended observations, output observations, abandoned revisions and
   their vectors and extractions stay as they are. This closes O5.

## Consequences

- `tools/bench_observations.py` (synthetic chat, 20 non-append actions alternating a reroll and a deep
  edit) measured this:
  - at 10,000 messages, observations drop from 23.3 MB to 1.1 MB (one full base plus twenty
    differences of ≈1.4 KB);
  - the first pass takes ≈0.5 s, and an idle pass under 1 ms;
  - rebuilding one observation takes ≈17 ms;
  - all 21 observations rebuild exactly.

  At 1,000 messages: 2.3 MB → 0.14 MB.
- An appended observation still names its base by manifest hash (ADR 0010). Its rows are that
  observation's rows (full or rebuilt) plus the tail.
- PostgreSQL reuses the freed space after autovacuum. The files shrink only after `VACUUM FULL`.
