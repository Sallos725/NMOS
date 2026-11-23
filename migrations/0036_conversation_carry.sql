-- NMOS Phase 60 S6 (ADR 0085): a chat that carries another chat's memory.
-- Owner input, like entity_link (ADR 0025): archived, kept by rebuilds, not a derived projection.
-- At link time the source is read once and the carried rows are stored in `snapshot` with each row's provenance;
-- `cutoff_commit_id` records the commit the reading was taken from (deliberately no foreign key).
-- At most one link is in force per target; removing a link sets `removed_at` and keeps the row for audit.
-- Deleting either the target or the source conversation deletes its links (ADR 0009).

CREATE TABLE conversation_carry (
    id                     uuid PRIMARY KEY,
    target_conversation_id uuid NOT NULL REFERENCES conversation (id),
    source_conversation_id uuid NOT NULL REFERENCES conversation (id),
    mode                   text NOT NULL CHECK (mode IN ('continue', 'regression')),
    entity_names           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(entity_names) = 'array'),
    cutoff_commit_id       uuid NOT NULL,
    cutoff_position        int NOT NULL,
    cutoff_turn            int,
    generations            jsonb,
    snapshot               jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    created_at             timestamptz NOT NULL DEFAULT now(),
    removed_at             timestamptz,
    CHECK (target_conversation_id <> source_conversation_id)
);

CREATE UNIQUE INDEX conversation_carry_in_force ON conversation_carry (target_conversation_id) WHERE removed_at IS NULL;
CREATE INDEX conversation_carry_source ON conversation_carry (source_conversation_id);
