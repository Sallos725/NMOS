-- NMOS: appends are rows of their own (Track A, A1).

-- An append extends the head commit without a new commit (D4). Until now its ops and changes were
-- concatenated onto the head commit's `delta`, which rewrote the whole jsonb on every generation:
-- 2.2 MB and ≈117 ms at 10,000 messages, growing with each append (docs/perf/scale.md). A commit's
-- full delta is now its `delta` followed by its appends in `seq` order. Deltas written before this
-- migration keep their inline append ops; replaying them first and these rows after is the same order.
CREATE TABLE worldline_append (
    seq                 bigserial PRIMARY KEY,
    commit_id           uuid NOT NULL REFERENCES worldline_commit (id),
    ops                 jsonb NOT NULL,
    changes             jsonb NOT NULL,
    host_observation_id uuid REFERENCES host_observation (id),
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX worldline_append_commit ON worldline_append (commit_id, seq);
-- Conversation delete (ADR 0009) checks this key per deleted observation.
CREATE INDEX worldline_append_observation ON worldline_append (host_observation_id);
