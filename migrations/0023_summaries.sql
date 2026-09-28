-- NMOS Phase 12 (ADR 0041): scene summaries and the story so far, a `summarize` projection.

ALTER TABLE projection_generation DROP CONSTRAINT projection_generation_kind_check;
ALTER TABLE projection_generation ADD CONSTRAINT projection_generation_kind_check
    CHECK (kind IN ('extract', 'embed', 'summarize'));

-- A scene summary covers one fixed window of turns; its key is the window's member revisions in order, so an edit,
-- delete, swipe or disable inside the window gives the window another key and the summary stops being current.
-- The story so far is keyed by the scene summaries it was made from, in order. Derived and rebuildable; raw text is
-- never replaced (invariants 1, 2). `members` is the provenance (invariant 10): revisions for a scene, scene
-- summaries for the story.
CREATE TABLE summary (
    id              uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    generation      text NOT NULL REFERENCES projection_generation (key),
    level           text NOT NULL CHECK (level IN ('scene', 'story')),
    window_key      text NOT NULL,
    members         uuid[] NOT NULL,
    first_turn      integer,
    last_turn       integer,
    text            text NOT NULL,
    held_back       text,  -- why the packet may not use it (NULL: it may)
    raw             jsonb NOT NULL,
    coverage        jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    discarded_at    timestamptz
);

CREATE UNIQUE INDEX summary_window ON summary (conversation_id, generation, level, window_key)
    WHERE discarded_at IS NULL;
