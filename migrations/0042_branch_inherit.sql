-- PHASE-67 part 2 (audit G6.1, design decision 11c): a branched chat inherits its origin's memory.
--
-- On a branch's first applied sync, the common prefix with its origin (matched by content, position by position, up to
-- the branch point) is served from copies of the origin's extractions, reveal checks, summaries and embeddings, written
-- for the branch's own source revisions (`branch.py`), and the owner's settings of the origin as of the branch point
-- are copied once. Copies of derived rows record their origin in their own jsonb (`coverage.reused_from`,
-- `usage.inherited_from`); owner input rows record it here. No foreign key: deleting the origin deletes its rows and
-- must leave the branch's copies, which are the branch's own, untouched.
--
-- `conversation.branch_inherit` is the marker of the copy: written once per conversation (status, origin, prefix
-- length, counts, time), also when the copy failed or found nothing, so a later sync never tries again by itself. NULL
-- for every conversation before this migration: no backfill on deploy (the explicit entry point is
-- `POST /v1/conversations/{id}/branch-inherit`). Additive and nullable; re-run safe.

ALTER TABLE conversation ADD COLUMN IF NOT EXISTS branch_inherit jsonb
    CHECK (branch_inherit IS NULL OR jsonb_typeof(branch_inherit) = 'object');
ALTER TABLE owner_repair ADD COLUMN IF NOT EXISTS inherited_from uuid;
ALTER TABLE entity_link ADD COLUMN IF NOT EXISTS inherited_from uuid;
ALTER TABLE conversation_carry ADD COLUMN IF NOT EXISTS inherited_from uuid;
