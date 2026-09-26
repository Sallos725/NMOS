# 0031 — Retire the per-message extraction window

Status: accepted, 2026-09-26. Owner decision on audit A-15 (`docs/audits/NMOS-AUDIT-2026-09-26.md`, review
option A). Amends ADR 0008 (the per-message `window_hash` stays) and ADR 0014 item 2 (the fallback matches
`turn_hash` or window hash). Amends D17.

## Context

Since `extract-v4` (ADR 0008, 0.1.0-beta.8) extraction is per turn and keyed by the anchor's `turn_hash`.
The earlier per-message key was kept for generations compiled before turns:
- every head membership row still computed and stored `active_membership.window_hash`, from the previous
  `NMOS_EXTRACT_WINDOW` members;
- the fact read, the older-generation fallback and the Inspector's coverage joined extractions on
  `turn_hash` **or** that window hash;
- the append fast path loaded extra members before the tail's first turn only to recompute those hashes.

The owner's database has no extraction from a per-message generation (`extract-v3`: 0 rows). A database
written before 0.1.0-beta.8 that still serves per-message extractions is the only one affected.

## Decision

1. Membership rows no longer get a window hash; `active_membership.window_hash` stays as a column (NULL for
   new rows) so that no migration and no rollback step is needed.
2. Extractions are matched on `turn_hash` only: the fact read (`facts.ACTIVE_ASSERTIONS_TEMPLATE`), the
   older-generation fallback (`extraction.OLDER_SERVES`), eligibility and the Inspector's coverage.
   `extraction.window_hash` keeps its name and holds the turn hash, as it has since ADR 0008.
3. `NMOS_EXTRACT_WINDOW` and `reconcile.window_hashes` are removed. The fast path's tail starts at the
   first turn it needs.

## Consequences

- A per-message extraction no longer serves its turn. After upgrading such a database, those turns show
  no facts until the current generation extracts them: the recent window at first sight, older turns
  through "Extract all history". The upgrade test shows it with the `v0.1.0-beta.7` fixture
  (`apps/sidecar/tests/test_upgrade.py`).
- One condition fewer in every fact read and coverage query, and no per-row window hash on each sync.
- `NMOS_EXTRACT_WINDOW` left in an `.env` is ignored.
