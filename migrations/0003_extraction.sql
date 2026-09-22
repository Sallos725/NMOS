-- NMOS Phase 2: bounded extraction (D7), job queue, assertions with provenance.

-- Hash of the revision plus the previous K members of the head. An extraction is only valid while
-- the head still presents the revision with the same window (D8: synchronous masking).
ALTER TABLE active_membership ADD COLUMN window_hash text;

CREATE TABLE job (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind            text NOT NULL,
    dedupe_key      text NOT NULL UNIQUE,
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    payload         jsonb NOT NULL,
    priority        integer NOT NULL DEFAULT 100,
    status          text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'obsolete', 'dead')),
    attempts        integer NOT NULL DEFAULT 0,
    run_after       timestamptz NOT NULL DEFAULT now(),
    locked_at       timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX job_ready ON job (priority, id) WHERE status = 'queued';

CREATE TABLE extraction (
    id                 uuid PRIMARY KEY,
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    window_hash        text NOT NULL,
    compiler_version   text NOT NULL,
    model              text NOT NULL,
    raw                jsonb NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_revision_id, window_hash, compiler_version)
);

CREATE TABLE assertion (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    extraction_id      uuid NOT NULL REFERENCES extraction (id),
    source_revision_id uuid NOT NULL REFERENCES source_revision (id),
    subject            text NOT NULL,
    subject_type       text,
    predicate          text NOT NULL,
    object             text,
    object_type        text,
    value              text,
    epistemic          text NOT NULL DEFAULT 'stated',
    confidence         real,
    evidence           text,
    status             text NOT NULL CHECK (status IN ('valid', 'pending')),
    reason             text
);

CREATE INDEX assertion_revision ON assertion (source_revision_id);
