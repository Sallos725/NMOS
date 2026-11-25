-- PHASE-67 part 4 (audit D7, owner decision 11b): an owner repair is anchored to the message it was made on, not to a
-- turn number. `anchor` is {"target": {"message", "revision", "turn_revisions"}, "apply": {"messages": [...]}}: the
-- host message id (`source_object.host_logical_id`) of the target's turn anchor with its revision hash and the hash of
-- its own turn's revisions, and the ids of the first and last message of the turn the repair applies from. A read maps
-- the anchor onto the head's numbering (`repairs.rebase`), so deleting an earlier message or editing another turn no
-- longer detaches it, and a repair made on a continuation the chat abandoned does not fire on a new one.
-- `anchored_at` is when the anchor was recorded: a repair written by an earlier release has none and keeps its legacy
-- target until a live read records one (one idempotent write a repair); a replay as of an earlier time reads the legacy
-- target (ADR 0027). Additive and nullable: no backfill, nothing is rewritten. The kind check gains the owner's new
-- repairs (fact_add, told_retract, fact_hidden, attention_dismiss); an older reader ignores them.

ALTER TABLE owner_repair ADD COLUMN IF NOT EXISTS anchor jsonb;
ALTER TABLE owner_repair ADD COLUMN IF NOT EXISTS anchored_at timestamptz;

ALTER TABLE owner_repair DROP CONSTRAINT IF EXISTS owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock', 'fact_restore', 'state_dismiss', 'entity_exclude', 'entity_pin',
                    'fact_add', 'told_retract', 'fact_hidden', 'attention_dismiss'));
