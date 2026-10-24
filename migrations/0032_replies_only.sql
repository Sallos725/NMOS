-- Phase 48 (D1): a chat that remembers the AI's replies only, for full impersonation (the AI writes the persona's
-- lines too, so the user's message is a direction to the model). Owner input, read by every request of the chat, like
-- the memory mode (ADR 0035). Step 2: no user message of such a chat is a recall candidate. No backfill, no rewrite.

ALTER TABLE conversation ADD COLUMN replies_only boolean NOT NULL DEFAULT false;
