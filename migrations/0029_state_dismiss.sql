-- Phase 39 (Q4): the owner's dismissal of a status flag, a change without a cause in the reply ("Needs attention").
--
-- A flag is not stored: each read compares the watched keys' neighbouring values (`statewatch.py`). Its dismissal is
-- owner input, an owner repair: `target` names the flag by what it says (its turn, key, reason, item, old and new
-- values), so a reroll or an edit that changes the flag shows it again. Undo sets `removed_at`, as for every repair.

ALTER TABLE owner_repair DROP CONSTRAINT owner_repair_kind_check;
ALTER TABLE owner_repair ADD CONSTRAINT owner_repair_kind_check
    CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep', 'fact_retract', 'fact_correct',
                    'name_split', 'fact_lock', 'fact_restore', 'state_dismiss'));
