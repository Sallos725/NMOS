-- NMOS Phase 3: revision embeddings (pgvector). Requires the pgvector extension
-- (compose uses the pgvector/pgvector:pg16 image).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE revision_embedding (
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    model              text NOT NULL,
    chunk              integer NOT NULL,
    dim                integer NOT NULL,
    text_start         integer NOT NULL,
    text_end           integer NOT NULL,
    embedding          vector NOT NULL,
    PRIMARY KEY (source_revision_id, model, chunk)
);
