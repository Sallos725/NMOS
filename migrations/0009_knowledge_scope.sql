-- NMOS: explicit knowledge scope per assertion (#10, D19 revised).
--   public  = openly known; known_by is not needed
--   limited = known_by names characters shown to know it and/or hidden_from names characters it is
--             kept from; anyone not listed is unknown, not unaware
--   unknown = the evidence does not show who knows (never rendered as "does not know")
ALTER TABLE assertion ADD COLUMN knowledge text NOT NULL DEFAULT 'unknown'
    CHECK (knowledge IN ('public', 'limited', 'unknown'));

-- Compatibility: rows with names were limited. Empty lists used to mean "everyone present knows" OR
-- "unclear"; the two cannot be told apart, so they become unknown (the conservative reading).
UPDATE assertion SET knowledge = 'limited' WHERE cardinality(known_by) > 0 OR cardinality(hidden_from) > 0;
