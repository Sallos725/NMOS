-- Phase 64 (`extract-v20`, `canon-v2`, ADR 0091): conditional forms of address.
-- On an `addresses` assertion, `address_condition` is a JSON object
-- `{"scope": "public|private|situational|all", "when": "<short phrase or null>"}`
-- when the turn or canon settles a situation-specific form of address (or explicitly
-- unifies a prior split with `all`). Nullable: every other predicate, every earlier
-- generation and every unconditional default address keep null. No backfill.

ALTER TABLE assertion ADD COLUMN address_condition jsonb
    CHECK (
        address_condition IS NULL
        OR (
            jsonb_typeof(address_condition) = 'object'
            AND coalesce(address_condition->>'scope' IN ('public', 'private', 'situational', 'all'), false)
            AND (
                address_condition->>'scope' <> 'situational'
                OR coalesce(
                    jsonb_typeof(address_condition->'when') = 'string'
                    AND char_length(btrim(address_condition->>'when')) BETWEEN 1 AND 60,
                    false
                )
            )
            AND (
                address_condition->>'scope' <> 'all'
                OR address_condition->'when' IS NULL
                OR jsonb_typeof(address_condition->'when') = 'null'
            )
            AND (
                address_condition->'when' IS NULL
                OR jsonb_typeof(address_condition->'when') = 'null'
                OR coalesce(
                    jsonb_typeof(address_condition->'when') = 'string'
                    AND char_length(btrim(address_condition->>'when')) BETWEEN 1 AND 60,
                    false
                )
            )
        )
    );
