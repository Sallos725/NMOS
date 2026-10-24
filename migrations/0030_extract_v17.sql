-- extract-v17 (Phase 45 and Phase 51, one generation).
--
-- Phase 45 (S2): who says each quoted line of the extracted turn, as extract-v17 names them:
-- [{"q": "<the quoted words>", "speaker": "<name, or {{user}} for the persona>"}]. A line whose speaker the turn does not
-- show is not listed. NULL for every other compiler and for rows written before it, which read as before.
-- Derived data like the rest of the row: an export carries it with the extraction, and a re-extraction writes it again.

ALTER TABLE extraction ADD COLUMN speakers jsonb;

-- Phase 51 (S2, amendment 1): a thread's horizon is stored in `assertion.salience`, whose vocabulary is by predicate
-- (`major`/`minor` for an event, `scene`/`arc`/`lasting` for a predicate that opens a thread). Migration 0016 allowed
-- the event words only; existing rows keep their values.

ALTER TABLE assertion DROP CONSTRAINT assertion_salience_check;
ALTER TABLE assertion ADD CONSTRAINT assertion_salience_check
    CHECK (salience IN ('major', 'minor', 'scene', 'arc', 'lasting'));
