-- Phase 14 (ADR 0045): canon sources. A canon text of a conversation (a card field, the author's note, the persona,
-- a lorebook entry) is a source_object of kind 'canon' (host_logical_id 'canon:<key>') with immutable revisions,
-- keyed by the hash of the text, like a message.
--
-- A canon manifest is the chat's canon at one time: each key with the hash of its text and what it is (metadata),
-- identified by the hash of its canonical JSON, which the plugin computes too. A request records the manifest its
-- prompt was built with and the keys the prompt held, so it replays with its own canon even when the texts reach the
-- sidecar after it (ADR 0027). canon_applied is the order in which manifests became the conversation's canon.

CREATE TABLE canon_manifest (
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    id              text NOT NULL,
    entries         jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, id)
);

CREATE TABLE canon_applied (
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    manifest_id     text NOT NULL,
    applied_at      timestamptz NOT NULL DEFAULT now(),
    observed_at     timestamptz
);

CREATE INDEX canon_applied_conversation ON canon_applied (conversation_id, applied_at);

ALTER TABLE conversation ADD COLUMN canon_manifest_id text, ADD COLUMN canon_observed_at timestamptz;

ALTER TABLE retrieval_trace ADD COLUMN canon_manifest_id text,
                            ADD COLUMN canon_held jsonb NOT NULL DEFAULT '[]'::jsonb;
