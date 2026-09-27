-- NMOS Phase 11 (`extract-v13`, ADR 0039): how a `resolved` assertion ends a thread, and a cause the story states.
-- Nullable, filled by extract-v13 and later; earlier rows keep null.

ALTER TABLE assertion ADD COLUMN outcome text;
ALTER TABLE assertion ADD COLUMN because text;
