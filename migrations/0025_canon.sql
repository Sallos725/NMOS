-- Phase 14 (ADR 0045): canon sources. A canon text of a conversation (a card field, the author's note, the persona,
-- a lorebook entry) is a source_object of kind 'canon' (host_logical_id 'canon:<key>') with immutable revisions,
-- like a message. canon_state says which revision of each key was in force when: a sync that finds a key changed
-- or gone closes its row (until) and opens the new one, so a read as of an earlier request sees that request's canon
-- (ADR 0027). A request records the canon keys its prompt held (canon_held).

CREATE TABLE canon_state (
    id                 uuid PRIMARY KEY,
    conversation_id    uuid NOT NULL REFERENCES conversation (id),
    canon_key          text NOT NULL,
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    since              timestamptz NOT NULL DEFAULT now(),
    until              timestamptz
);

CREATE INDEX canon_state_conversation ON canon_state (conversation_id, since);
CREATE UNIQUE INDEX canon_state_current ON canon_state (conversation_id, canon_key) WHERE until IS NULL;

ALTER TABLE retrieval_trace ADD COLUMN canon_held jsonb NOT NULL DEFAULT '[]'::jsonb;
