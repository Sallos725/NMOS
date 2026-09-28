-- Phase 14 step 5 (ADR 0047): canon facts and the owner's lock.
--
-- Canon facts need no table of their own: a canon text's extraction and its assertions are stored like a turn's,
-- against the canon revision (window 'canon:<part>'), under a generation of kind 'canon'. A read tells them apart by
-- the revision's source kind.

ALTER TABLE projection_generation DROP CONSTRAINT projection_generation_kind_check;
ALTER TABLE projection_generation ADD CONSTRAINT projection_generation_kind_check
    CHECK (kind IN ('extract', 'embed', 'summarize', 'canon'));

-- The lorebook entries a chat's prompts held, which the canon generation reads (PHASE-14 Q3): found per chat without
-- reading its other traces.
CREATE INDEX retrieval_trace_canon_held ON retrieval_trace (conversation_id) WHERE canon_held <> '[]'::jsonb;

-- `fact_lock` (PHASE-14 Q7) is an owner repair: the locked version of a fact stays current, and a later story
-- statement of it is kept as a conflict, not a new version. Undo sets `removed_at`, as for every repair.

ALTER TABLE owner_repair DROP CONSTRAINT owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock'));
