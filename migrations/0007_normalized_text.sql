-- NMOS: versioned normalized-text projection (#9, #13). Rebuildable from source_revision.content,
-- which stays immutable. Lexical recall, embedding, extraction and excerpting all read clean_content.

CREATE TABLE revision_text (
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    normalizer         text NOT NULL,
    clean_content      text NOT NULL,
    original_chars     integer NOT NULL,
    clean_chars        integer NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_revision_id, normalizer)
);

CREATE INDEX revision_text_trgm ON revision_text USING gin (clean_content gin_trgm_ops);

-- Lexical recall no longer searches raw content (reasoning/markup must not create hits).
DROP INDEX source_revision_content_trgm;
