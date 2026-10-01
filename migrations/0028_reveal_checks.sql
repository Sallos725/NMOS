-- Phase 22 (ADR 0057): reveal checks, and the owner's restore of a fact a re-extraction dropped.
--
-- A reveal check needs no table of its own: like a canon read (migration 0026), it is an extraction with its
-- assertions, here against the turn's anchor revision under the window 'reveal:<turn hash>', of a generation of kind
-- 'reveal'. Its hints name the extraction it checked; a read serves its rows while that extraction serves the turn.

ALTER TABLE projection_generation DROP CONSTRAINT projection_generation_kind_check;
ALTER TABLE projection_generation ADD CONSTRAINT projection_generation_kind_check
    CHECK (kind IN ('extract', 'embed', 'summarize', 'canon', 'reveal'));

-- `fact_restore` (PHASE-22 Q7) is an owner repair: a narrated fact a re-extraction dropped, read again at its turn.

ALTER TABLE owner_repair DROP CONSTRAINT owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock', 'fact_restore'));
