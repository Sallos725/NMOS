-- NMOS Phase 1: deterministic state projection (rebuildable from source_revision + parser rules).

CREATE TABLE state_observation (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id    uuid NOT NULL REFERENCES conversation (id),
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    rules_version      text NOT NULL,
    rule_id            text NOT NULL,
    key                text NOT NULL,
    value              text NOT NULL,
    UNIQUE (source_revision_id, rules_version, key)
);

CREATE INDEX state_observation_conversation ON state_observation (conversation_id, rules_version, key);
