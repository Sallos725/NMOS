-- PHASE-60 S8 (ADR 0087): the owner pins a character: `entity_pin`, owner input like every repair (ADR 0044). `target`
-- names the entity by its type and the name the owner saw, as `entity_exclude` does (migration 0031); the read resolves
-- the name, so a name the story joins to it follows and a split name does not. Undo sets `removed_at`, as for every
-- repair. An excluded entity is not pinned: the read lets `entity_exclude` win. No backfill: no earlier row is a pin.

ALTER TABLE owner_repair DROP CONSTRAINT owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock', 'fact_restore', 'state_dismiss', 'entity_exclude', 'entity_pin'));
