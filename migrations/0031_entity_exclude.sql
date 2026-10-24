-- Phase 47 (S1): the owner leaves a name out of the cast, or out of memory: `entity_exclude`, owner input like every
-- repair (ADR 0044). `target` names the entity by its type and the name the owner saw, with a `scope` (`cast` or
-- `memory`); the read resolves the name, so a name the story joins to it follows and a split name does not. Undo sets
-- `removed_at`, as for every repair. Nothing is deleted: the read leaves the entity out.

ALTER TABLE owner_repair DROP CONSTRAINT owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock', 'fact_restore', 'state_dismiss', 'entity_exclude'));
