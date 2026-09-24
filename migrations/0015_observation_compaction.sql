-- NMOS: lossless compaction of full-manifest host observations (O5, owner decision 2026-09-24; ADR 0018).

-- Observations that still hold every manifest row ("entries"): the only ones compaction reads.
CREATE INDEX host_observation_full ON host_observation (conversation_id, id)
    WHERE kind = 'manifest' AND raw_manifest ? 'entries';

-- Bookkeeping, not evidence: full observations compaction decided to keep full, as the base that later
-- ones are stored against. Rebuildable by re-running compaction from an empty table.
CREATE TABLE observation_base (
    observation_id  uuid PRIMARY KEY REFERENCES host_observation (id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL
);
CREATE INDEX observation_base_conversation ON observation_base (conversation_id, observation_id);
