-- Phase 60 (`extract-v19`, ADR 0086): when an event or promise happened apart from when the turn told it, and the
-- story clock shown to the extraction. On an `event` or `promised` assertion of `extract-v19`, `when_happened` is a
-- short phrase as the story gives it when the turn places what it states at another time than the turn itself; every
-- other row keeps null. On `extraction`, `story_clock` records the literal status-window clock shown as of the target
-- turn (a recorded input, never part of validity); null otherwise. Nullable, no backfill.

ALTER TABLE assertion ADD COLUMN when_happened text CHECK (when_happened IS NULL OR char_length(when_happened) BETWEEN 1 AND 80);

ALTER TABLE extraction ADD COLUMN story_clock text;
