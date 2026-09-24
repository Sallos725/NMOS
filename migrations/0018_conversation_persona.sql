-- NMOS: the name of the user's persona in a conversation, as the host last reported it (ADR 0023).
-- Read-time entity resolution treats it as the persona (`{{user}}`). Like the labels of 0010 it follows
-- the host: a later report replaces it, and a sync without one leaves it as it is.

ALTER TABLE conversation ADD COLUMN host_persona_name text;
