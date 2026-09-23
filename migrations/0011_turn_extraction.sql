-- NMOS: extraction per turn (ADR 0008).

-- Turn index of each head member (NULL: comment, disabled, before an allBefore cut) and, on a turn's
-- anchor (its last reply), the hash of the turn plus the previous K turns. The per-message
-- window_hash stays for generations compiled before turns. Filled by the sidecar at startup.
ALTER TABLE active_membership ADD COLUMN turn integer;
ALTER TABLE active_membership ADD COLUMN turn_hash text;
CREATE INDEX active_membership_turn ON active_membership (commit_id, turn);

-- Member revisions of an extracted turn, oldest first (provenance, invariant 10). NULL for
-- per-message extractions.
ALTER TABLE extraction ADD COLUMN members uuid[];

-- A per-chat rebuild discards extractions instead of deleting them: they stay for audit, never
-- count as coverage and never produce facts. Only one live extraction per (revision, window, generation).
ALTER TABLE extraction ADD COLUMN discarded_at timestamptz;
DROP INDEX extraction_generation_window;
CREATE UNIQUE INDEX extraction_generation_window ON extraction (source_revision_id, window_hash, extractor_key)
    WHERE discarded_at IS NULL;
