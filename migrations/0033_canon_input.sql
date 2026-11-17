-- Phase 57 A1 (ADR 0079): a canon part is read once for every chat that sends the model the same input. Each canon
-- extraction records the fingerprint of that input in its coverage (`input`); a read looks for a match of the same
-- canon generation and copies it into its own chat instead of calling the model. Earlier extractions recorded no
-- input and are no source. No backfill, no rewrite.

CREATE INDEX extraction_canon_input ON extraction (extractor_key, (coverage->>'input')) WHERE coverage ? 'input';
