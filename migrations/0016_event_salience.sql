-- NMOS: event salience (Phase 7, docs/phases/PHASE-7.md Q4; ADR 0020).

-- `extract-v7` labels each `event` assertion major or minor. NULL: any other predicate, and every row of
-- an older generation (unlabeled; ranked as before inside the event cap).
ALTER TABLE assertion
    ADD COLUMN salience text CHECK (salience IN ('major', 'minor'));
