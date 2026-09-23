-- NMOS: the owner may delete one conversation with everything recorded for it (ADR 0009).
-- Raw evidence is still never deleted by NMOS itself: the guard lets a source_revision row go only
-- inside the delete of its own conversation, which sets nmos.delete_conversation for its
-- transaction (SET LOCAL). Any other DELETE is refused as before.

CREATE OR REPLACE FUNCTION source_revision_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('nmos.delete_conversation', true) IS NOT NULL
       AND current_setting('nmos.delete_conversation', true) <> ''
       AND EXISTS (SELECT 1 FROM source_object so WHERE so.id = OLD.source_object_id
                     AND so.conversation_id = current_setting('nmos.delete_conversation', true)::uuid) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'source_revision rows are never deleted';
END $$;

-- Deleting rows checks every foreign key that points at them, one lookup per row. Without an index
-- on the referencing column each lookup scans the whole table (every chat's rows), which made the
-- delete of a 5,000-message chat take seconds and grow quadratically (docs/perf/scale.md). The
-- unique extraction index is partial since 0011, so the key check cannot use it.
CREATE INDEX extraction_revision ON extraction (source_revision_id);
CREATE INDEX assertion_extraction ON assertion (extraction_id);
CREATE INDEX active_membership_revision ON active_membership (source_revision_id);
CREATE INDEX state_observation_revision ON state_observation (source_revision_id);
CREATE INDEX source_revision_lineage_parent ON source_revision (lineage_parent_revision_id);
CREATE INDEX worldline_commit_observation ON worldline_commit (host_observation_id);
CREATE INDEX retrieval_trace_commit ON retrieval_trace (commit_id);
