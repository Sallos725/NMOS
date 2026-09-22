-- NMOS: human-readable labels for a conversation, as the host last reported them (bot name, chat
-- name). Display only: identity stays host_chat_ref. Names can change in the host at any time.

ALTER TABLE conversation ADD COLUMN host_character_name text;
ALTER TABLE conversation ADD COLUMN host_chat_name text;
