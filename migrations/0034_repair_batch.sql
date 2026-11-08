-- Phase 57 B1 (ADR 0080): the owner applies or retracts several rows of "Needs attention" at once. The repairs one
-- such action writes share a batch id, so the repairs table shows them as one line and undoes them together; each
-- stays an ordinary repair, undoable on its own. No backfill: earlier repairs have none.

ALTER TABLE owner_repair ADD COLUMN batch_id uuid;

CREATE INDEX owner_repair_batch ON owner_repair (conversation_id, batch_id) WHERE batch_id IS NOT NULL;
