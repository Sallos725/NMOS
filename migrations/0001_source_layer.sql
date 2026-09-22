-- NMOS Phase 0B: source layer, host observations, retrieval traces.
-- Never edit this file after it has been applied; add 0002_*.sql instead.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE conversation (
    id                            uuid PRIMARY KEY,
    host                          text NOT NULL,
    host_character_ref            text,
    host_chat_ref                 text NOT NULL,
    created_at                    timestamptz NOT NULL DEFAULT now(),
    branched_from_conversation_id uuid REFERENCES conversation (id),
    branched_from_host_chat_ref   text,
    branched_from_message_ref     text,
    head_commit_id                uuid,
    head_manifest_hash            text,
    UNIQUE (host, host_chat_ref)
);

CREATE TABLE host_observation (
    id              uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    kind            text NOT NULL CHECK (kind IN ('manifest', 'output')),
    manifest_hash   text,
    idempotency_key text NOT NULL UNIQUE,
    observed_at     timestamptz NOT NULL DEFAULT now(),
    raw_manifest    jsonb NOT NULL
);

CREATE TABLE source_object (
    id              uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    host_logical_id text NOT NULL,           -- PocketRisu Message.chatId, verbatim (H6)
    source_kind     text NOT NULL DEFAULT 'message',
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, host_logical_id)
);

CREATE TABLE source_revision (
    id                         uuid PRIMARY KEY,
    source_object_id           uuid NOT NULL REFERENCES source_object (id),
    revision_hash              text NOT NULL,
    content                    text NOT NULL,
    metadata                   jsonb NOT NULL,
    recorded_at                timestamptz NOT NULL DEFAULT now(),
    lifecycle                  text NOT NULL CHECK (lifecycle IN ('provisional', 'accepted', 'retracted', 'superseded')),
    lineage_parent_revision_id uuid REFERENCES source_revision (id),
    UNIQUE (source_object_id, revision_hash)
);

CREATE INDEX source_revision_content_trgm ON source_revision USING gin (content gin_trgm_ops);

-- Invariant: raw evidence is immutable. Only lifecycle (and a first-time lineage link) may change.
CREATE FUNCTION source_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.content IS DISTINCT FROM OLD.content
       OR NEW.revision_hash IS DISTINCT FROM OLD.revision_hash
       OR NEW.source_object_id IS DISTINCT FROM OLD.source_object_id
       OR NEW.metadata IS DISTINCT FROM OLD.metadata
       OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
       OR (OLD.lineage_parent_revision_id IS NOT NULL
           AND NEW.lineage_parent_revision_id IS DISTINCT FROM OLD.lineage_parent_revision_id) THEN
        RAISE EXCEPTION 'source_revision % is immutable except lifecycle', OLD.id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER source_revision_immutable
    BEFORE UPDATE ON source_revision
    FOR EACH ROW EXECUTE FUNCTION source_revision_guard();

CREATE FUNCTION source_revision_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'source_revision rows are never deleted';
END $$;

CREATE TRIGGER source_revision_append_only
    BEFORE DELETE ON source_revision
    FOR EACH ROW EXECUTE FUNCTION source_revision_no_delete();

CREATE TABLE worldline_commit (
    id                  uuid PRIMARY KEY,
    seq                 bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    conversation_id     uuid NOT NULL REFERENCES conversation (id),
    parent_commit_ids   uuid[] NOT NULL,
    reason              text NOT NULL CHECK (reason IN (
                            'import', 'branch', 'edit', 'delete', 'swipe', 'reroll',
                            'disable', 'reconciliation', 'manual')),
    manifest_hash       text NOT NULL,
    delta               jsonb NOT NULL,   -- {"ops": [...], "changes": [...]}; head commit gains append ops (D4)
    created_at          timestamptz NOT NULL DEFAULT now(),
    host_observation_id uuid REFERENCES host_observation (id)
);

CREATE INDEX worldline_commit_conversation ON worldline_commit (conversation_id, seq);

ALTER TABLE conversation
    ADD CONSTRAINT conversation_head_commit_fk FOREIGN KEY (head_commit_id) REFERENCES worldline_commit (id);

-- Materialized membership of each conversation's current head commit only. Rebuildable.
CREATE TABLE active_membership (
    commit_id          uuid NOT NULL REFERENCES worldline_commit (id),
    position           integer NOT NULL,
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    PRIMARY KEY (commit_id, position)
);

CREATE TABLE retrieval_trace (
    id                  uuid PRIMARY KEY,
    conversation_id     uuid NOT NULL REFERENCES conversation (id),
    commit_id           uuid REFERENCES worldline_commit (id),
    query               text NOT NULL,
    candidates          jsonb NOT NULL,
    selected            jsonb NOT NULL,
    excluded_in_context jsonb NOT NULL,
    token_estimate      integer NOT NULL,
    latency_ms          jsonb NOT NULL,
    freshness           text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);
