-- PHASE-70 (ADR 0096): the owner attaches a short canonical description/note to any entity (item, place, character,
-- group or concept): `entity_note`, owner input like every repair (ADR 0044, ADR 0087). `target` names the entity by
-- its type and the name the owner saw, resolved on every read so aliases follow and splits separate; `value` holds
-- {"text": "..."} (up to 300 chars). Undo sets `removed_at`; saving a new note for the same entity supersedes the
-- previous row with `removed_at = now()`. Additive constraint change only, no backfill; older images ignore unknown
-- repair kinds.

ALTER TABLE owner_repair DROP CONSTRAINT IF EXISTS owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock', 'fact_restore', 'state_dismiss', 'entity_exclude', 'entity_pin',
                    'fact_add', 'told_retract', 'fact_hidden', 'attention_dismiss', 'entity_note'));
