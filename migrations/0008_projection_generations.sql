-- NMOS: derived projections are bound to an explicit generation (#6, #7, #8).
-- A generation key hashes everything that changes the derived output (compiler/prompt/registry/
-- normalizer/chunker versions, endpoint, model, settings) and never credentials.

CREATE TABLE projection_generation (
    key          text PRIMARY KEY,
    kind         text NOT NULL CHECK (kind IN ('extract', 'embed')),
    model        text NOT NULL,
    endpoint     text NOT NULL,
    spec         jsonb NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz NOT NULL DEFAULT now()
);

-- Extractions: rows written before generations existed keep extractor_key NULL. They remain for
-- audit but never enter the current fact projection.
ALTER TABLE extraction ADD COLUMN extractor_key text REFERENCES projection_generation (key);
ALTER TABLE extraction DROP CONSTRAINT extraction_source_revision_id_window_hash_compiler_version_key;
CREATE UNIQUE INDEX extraction_generation_window ON extraction (source_revision_id, window_hash, extractor_key);
-- #13: how much of the target/context the model actually saw.
ALTER TABLE extraction ADD COLUMN coverage jsonb;

-- Embeddings: identity is the projection, not the model name. Existing rows get a legacy
-- projection; the sidecar adopts them once into the first registered projection for that model.
ALTER TABLE revision_embedding ADD COLUMN projection text;
UPDATE revision_embedding SET projection = 'legacy:' || model;
ALTER TABLE revision_embedding ALTER COLUMN projection SET NOT NULL;
ALTER TABLE revision_embedding DROP CONSTRAINT revision_embedding_pkey;
ALTER TABLE revision_embedding ADD PRIMARY KEY (source_revision_id, projection, chunk);

-- Jobs queued before this migration do not say which generation they ask for; the sidecar
-- re-queues current-generation work at startup.
UPDATE job SET status = 'obsolete', updated_at = now()
WHERE kind IN ('extract', 'embed') AND status IN ('queued', 'running');
