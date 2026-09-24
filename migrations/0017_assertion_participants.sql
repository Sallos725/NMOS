-- NMOS: typed participants of an assertion (Phase 8, docs/phases/PHASE-8.md Q2, Q3).

-- `extract-v8` lists the other characters or groups an `event`, `goal`, `knows` or `destroyed` value
-- involves, as a JSON array of {"name", "type"} objects. NULL: none, another predicate, or a row of an
-- older generation (recalled through its subject and object only, Q5).
ALTER TABLE assertion
    ADD COLUMN participants jsonb CHECK (participants IS NULL OR jsonb_typeof(participants) = 'array');
