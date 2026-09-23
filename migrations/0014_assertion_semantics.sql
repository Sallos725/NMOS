-- NMOS: assertion semantics (Phase 5, ADR 0013) and extraction name hints (ADR 0012).

-- Rows written before this migration are legacy: positive, actual, and no source. Readers treat a
-- missing source as narration (how those rows were always read) and never as a claim.
ALTER TABLE assertion
    ADD COLUMN polarity    text NOT NULL DEFAULT 'positive' CHECK (polarity IN ('positive', 'negative')),
    ADD COLUMN modality    text NOT NULL DEFAULT 'actual'
        CHECK (modality IN ('actual', 'hypothetical', 'dreamed', 'unknown')),
    ADD COLUMN source      text CHECK (source IN ('narration', 'character_claim')),
    ADD COLUMN asserted_by text;

-- The entity names an extraction was shown (ADR 0012). NULL: none (older generations, hints off).
ALTER TABLE extraction ADD COLUMN hints jsonb;
