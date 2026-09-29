-- Phase 17 step 2 (ADR 0051, D61): what NMOS's own model calls used, as the provider reported it.
--
-- Written with the row the call produced, so a rebuild or a new generation keeps each old row's own usage:
-- a turn's or a canon part's extraction, a scene or story summary, and each embedded chunk. NULL is a row written
-- before this migration ("not recorded"); `{"calls": 0}` a row written without a model call (too little text);
-- otherwise `calls`, `ms`, the provider's `model`, and `input` / `output` / `cached` / `reasoning` tokens only when
-- the response's `usage` carried them (none of them: "not reported"). Never an estimate.
--
-- Nullable columns without a default: no table rewrite.

ALTER TABLE extraction ADD COLUMN usage jsonb;
ALTER TABLE summary ADD COLUMN usage jsonb;
ALTER TABLE revision_embedding ADD COLUMN usage jsonb;
