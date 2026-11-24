-- NMOS PHASE-61 S6 (ADR 0089): a log of model calls. One row per call the worker or the sidecar makes to a model
-- outside the request path (extraction, reveal checks, summaries, canon facts, embeddings, the author's note, the
-- settings test). Operational data, like `job`: never archived, pruned with the traces (NMOS_TRACE_RETENTION_DAYS).
-- Metadata only: no prompt, reply, chat text or credential. `endpoint` is scheme, host and path (never userinfo or a
-- query); `error` is the provider's error for an HTTP fault, the exception's class for a timeout or a transport fault,
-- and the kind of fault alone for a reply that could not be read.
-- `job_id` has no foreign key: finished jobs are pruned after 7 days and a row outlives them. Deleting a conversation
-- deletes its rows; the foreign key cascades, so an image from before this phase still deletes a chat cleanly.
-- Additive: no existing row is read or rewritten.

CREATE TABLE model_call (
    id              uuid PRIMARY KEY,
    at              timestamptz NOT NULL DEFAULT clock_timestamp(),
    kind            text NOT NULL CHECK (kind IN ('extract', 'reveal', 'summarize', 'canon', 'embed', 'note', 'test')),
    conversation_id uuid REFERENCES conversation (id) ON DELETE CASCADE,
    job_id          bigint,
    generation      text,
    model           text NOT NULL,
    endpoint        text NOT NULL,
    outcome         text NOT NULL CHECK (outcome IN ('ok', 'http', 'timeout', 'transport', 'bad_reply')),
    http_status     integer,
    ms              integer NOT NULL,
    usage           jsonb,
    error           text CHECK (error IS NULL OR char_length(error) <= 300)
);

CREATE INDEX model_call_at ON model_call (at DESC);
CREATE INDEX model_call_conversation ON model_call (conversation_id) WHERE conversation_id IS NOT NULL;
