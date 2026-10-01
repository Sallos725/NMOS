-- Phase 26 (ADR 0060): the owner moves a repair that matches nothing now to the item it means after a new extractor
-- generation. A move removes the old repair (`removed_at`) and stores the same repair for the new item, naming the old
-- one here, in one transaction; nothing else changes. Older repairs and repairs made directly have none.

ALTER TABLE owner_repair ADD COLUMN moved_from uuid REFERENCES owner_repair (id);
