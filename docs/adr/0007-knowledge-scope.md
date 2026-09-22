# 0007 — Knowledge scope: public, limited, unknown

Status: accepted, 2026-09-22. Issue #10. Revises D19.

## Context

The beta.2/beta.3 extraction prompt said to use `known_by = []` "when everyone present knows **or it
is unclear**", while the packet Note said "characters not listed as knowing a fact do not know it".
An empty list therefore meant either "public" or "unknown", and the packet turned both into "nobody
knows". That contradicts two invariants: unknown is a valid state, and character knowledge is not
world knowledge.

## Decision

- Every assertion stores `knowledge ∈ {public, limited, unknown}` (migration 0009), plus the
  existing `known_by` / `hidden_from` name arrays.
  - `public`: openly known. No list is needed, and `known_by` is dropped as redundant.
  - `limited`: `known_by` names characters shown to know or witness it; `hidden_from` names
    characters it is explicitly kept from. Anyone not listed is **unknown**, not unaware.
  - `unknown`: the evidence does not show who knows. This is the default for a missing or empty answer.
- Validation normalizes model output: `public` + `hidden_from` → `limited` ("public except X");
  `limited` with nobody named → `unknown`; names in `known_by` without a scope → `limited`.
- **Contradictory evidence:** a name in both lists is removed from both, so that character's awareness
  is unknown, and `assertion.reason` records `contradictory knowledge for: <names>`. Contradictions
  *across* assertions (a later fact says the secret leaked) are ordinary fact versions: the newest
  assertion for the same version key wins, and history keeps both.
- The packet renders the stored state exactly: `knowledge="public"`, or `known_by` / `hidden_from`
  for limited facts, or no mark. The Note reads: public is openly known; known_by characters know it;
  hidden_from characters do not know it; whether anyone else knows it, or anyone knows an unmarked
  fact, is unknown — do not assume either way.
- **Compatibility:** rows with names become `limited`. Rows with empty lists become `unknown`, since
  the old meaning cannot be recovered and unknown is the conservative reading. `COMPILER_VERSION`
  moves to `extract-v3`, so history is re-extracted with the new prompt under the ADR 0006 coverage
  policy.

## Path to principal identity

Names stay free-text strings (as the story spells them, `{{user}}` for the persona) during the soft
phase. They are not a schema identity. When hard POV isolation (D9 `character_pov`) is authorized,
introduce a principal/entity table with aliases and resolve these strings to principal ids in a
projection. The stored strings stay as evidence, so no existing data needs to be rewritten.
