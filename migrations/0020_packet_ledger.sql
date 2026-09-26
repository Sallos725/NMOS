-- NMOS Phase 9: packet ledger (ADR 0027). Every retrieval records each line it offered to the packet,
-- whether it was placed and why not, its provenance, and the inputs needed to compile the same packet
-- again (replay). Derived data: pruned with the trace after NMOS_TRACE_RETENTION_DAYS.
-- Never edit this file after it has been applied; add 0021_*.sql instead.

ALTER TABLE retrieval_trace
    ADD COLUMN policy          text,     -- packet compiler that built it (packet-v0, packet-v1, ...)
    ADD COLUMN budget_tokens   integer,
    ADD COLUMN upto_position   integer,  -- last head position when the request was answered (the query)
    ADD COLUMN previous_ai     text,
    ADD COLUMN in_context      jsonb,    -- host ids the prompt already held (D3)
    ADD COLUMN extractor_key   text,
    ADD COLUMN embed_projection text,
    ADD COLUMN rules_version   text,
    ADD COLUMN recall_options  jsonb,    -- top_k, thresholds and limits the request used
    ADD COLUMN lines           jsonb;    -- [{kind, ref, turn, tok, placed, why, text, ...}] in offer order

-- When a vector became searchable, so a replay "as of" a trace ignores vectors written after it.
-- Rows written before this migration stay NULL: known before any Phase 9 trace.
ALTER TABLE revision_embedding ADD COLUMN created_at timestamptz;
ALTER TABLE revision_embedding ALTER COLUMN created_at SET DEFAULT now();
