-- NMOS Phase 13 (ADR 0044): what the owner says memory got wrong, as owner input.
-- Like the owner's name joins (entity_link, ADR 0025) this is input, not a derived projection: a rebuild and a new
-- extractor generation keep it, and every read applies it. `target` is the item as the Inspector showed it (its
-- turn, the turn's hash, its kind or predicate, its maker or subject, its text); a read finds the item by what it
-- says, never by an assertion id, which a new generation replaces. `value` is what the repair sets (an outcome, a
-- character, the turn it takes effect). No assertion or message is ever edited (invariants 1, 2). Undo sets
-- `removed_at`; the row stays for audit. Deleting the conversation deletes its repairs (ADR 0009).

CREATE TABLE owner_repair (
    id              uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversation (id),
    kind            text NOT NULL CHECK (kind IN ('thread_close', 'thread_reopen', 'secret_found_out', 'secret_keep',
                                                  'fact_retract', 'fact_correct', 'name_split')),
    target          jsonb NOT NULL,
    value           jsonb NOT NULL DEFAULT '{}',
    note            text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    removed_at      timestamptz
);

CREATE INDEX owner_repair_conversation ON owner_repair (conversation_id) WHERE removed_at IS NULL;
