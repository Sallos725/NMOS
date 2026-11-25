-- Tier 4 (audit B4.3): per-turn persona attribution. Each synced `source_revision` records the host persona active
-- when the message arrived (nullable: legacy revisions before this migration stay NULL and inherit the conversation's
-- current `host_persona_name`, preserving identical reads and replays). When a chat switches personas mid-chat, turns
-- synced under an earlier persona attribute their `{{user}}` mentions to that persona instead of being retroactively
-- reassigned to the new persona. Additive and nullable: no backfill, no existing row rewritten.

ALTER TABLE source_revision ADD COLUMN IF NOT EXISTS persona_name text;
