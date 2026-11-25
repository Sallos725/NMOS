-- PHASE-64 part 1 (`extract-v20`): the typed ontology's own marks on an assertion, as the extraction that wrote the
-- row read them. `condition`: when the fact holds (in public or in private, before whom, under which guise, in which
-- situation), an object of at most four known keys on a conditioned predicate (`addresses`, `relationship`,
-- `role_toward`, `feels_toward`, `identity`, `cover_identity`, `has_status`, `promised`). `guise`: the guise name a
-- fact is held under or toward. `item_kind`: whether an item is one of a kind or one of many (`possesses`,
-- `located_in` of an item, `destroyed`, `contained_in`). `knowledge_scope`: the knowledge scope with
-- `public_except` (everyone but `hidden_from`), next to `knowledge`, which keeps public|limited|unknown so every
-- earlier reader reads the row as before. Nullable: every earlier generation, every other predicate and a mark the
-- model did not give keep null. No backfill. Each CHECK rides on its own ADD COLUMN, so a re-run skips both. The
-- condition's size bound is a backstop above the worker's own 512-byte cap on its compact JSON (`predicates.condition`):
-- jsonb's text form adds a space after each separator.

ALTER TABLE assertion
    ADD COLUMN IF NOT EXISTS condition jsonb
        CHECK (condition IS NULL OR (jsonb_typeof(condition) = 'object' AND octet_length(condition::text) <= 1024)),
    ADD COLUMN IF NOT EXISTS guise text
        CHECK (guise IS NULL OR char_length(guise) BETWEEN 1 AND 80),
    ADD COLUMN IF NOT EXISTS item_kind text
        CHECK (item_kind IS NULL OR item_kind IN ('unique', 'fungible')),
    ADD COLUMN IF NOT EXISTS knowledge_scope text
        CHECK (knowledge_scope IS NULL OR knowledge_scope IN ('public', 'public_except', 'limited', 'unknown'));
