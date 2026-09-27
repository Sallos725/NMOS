-- NMOS: per-chat memory mode (Phase 10 step 5, ADR 0035). Owner input, like entity links: a rebuild keeps it.
--   memory_strict:   facts only some characters in the scene know are withheld, their holders named (off by default)
--   memory_narrator: the chat is told in this character's first person; only what they know is placed
--                    (NULL: no narrator; '{{user}}' for the user's character)

ALTER TABLE conversation
    ADD COLUMN memory_strict boolean NOT NULL DEFAULT false,
    ADD COLUMN memory_narrator text CHECK (memory_narrator IS NULL OR length(memory_narrator) BETWEEN 1 AND 60);
