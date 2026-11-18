-- Phase 58 (`extract-v18`, ADR 0081): how a feeling feels. On a `feels_toward` assertion, the strength (faint, clear,
-- strong), the sign (positive, negative or null) and a second feeling the turn shows beneath the first, as the
-- extraction that wrote the row read them. Nullable: every other predicate, every earlier generation and a feeling the
-- model did not weigh keep null. No backfill.

ALTER TABLE assertion ADD COLUMN feeling jsonb CHECK (feeling IS NULL OR jsonb_typeof(feeling) = 'object');
