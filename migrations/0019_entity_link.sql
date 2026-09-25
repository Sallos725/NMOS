-- NMOS: the owner's statement that two names of one conversation are the same entity (ADR 0025).
-- Owner input, not a derived projection: a rebuild keeps it and read-time resolution applies it on every
-- read. The names are stored as the Inspector showed them; a name no longer mentioned on the head links
-- nothing until it is mentioned again. Removing a link keeps the row with `removed_at` (audit).

CREATE TABLE entity_link (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversation(id),
    entity_type text NOT NULL CHECK (entity_type IN ('character', 'place', 'item', 'group', 'concept')),
    name text NOT NULL,
    same_as text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    removed_at timestamptz
);

CREATE INDEX entity_link_conversation ON entity_link (conversation_id) WHERE removed_at IS NULL;
