# 0094 — Status windows in more shapes, and keys that stay where they were

Status: accepted, 2026-11-25, PHASE-65 (S9). The owner's decision of 2026-11-25 on keys (existing pins, watches and
stored state must keep matching). Amends ADR 0071 (a status window over time) and PHASE-43 (status windows by their
shape). Recorded as built at `361130c`.

## Context

A status window was read from one-line `[key: value | …]` bars and a few block shapes. Windows the owner's bots write
were missed or misread (G2): two characters' bars in one reply wrote one `HP` that flipped between them; HTML cards
glued their cells (`80MP: 40`); 【】 and Markdown tables were not windows; a `|` inside a nested list cut the value.
Telling the two characters apart needs a key per character, but pins, watches and the state history are stored by
key, so a prefix on every window would have moved every existing key.

## Decision

1. **More shapes.** A nested-aware `|` split (falling back to every `|` when that reads more keys); 【】《》『』
   brackets; a short bare segment continues the field before it unless that field holds a number; multi-line windows
   (a bracket, a header line, a status-word header, a fence); two-column Markdown tables; HTML cards read through an
   offset-mapped text pass with `<style>` and `<script>` dropped and block and cell boundaries kept. Dialogue and
   speech-like values are no window. A one-line `[..]` window wins any overlap with a newer shape, and a key a
   one-line window set in a reply is not overwritten by a newer shape's block in the same reply, so what the earlier
   rules read is read the same way.
2. **A prefix only for two characters.** A block's leading name (`Block.entity`) is a candidate. Candidates become
   characters only when one reply holds windows of two or more different candidates that share a key not about the
   scene (`statusshape.characters`); then their keys are `<character>.<key>` (`서연.HP`). Scene keys (clock, place,
   weather, season, weekday; `SCENE_ONLY`) are never prefixed. A window for one character keeps its bare keys.
3. **Pins and watches by last part.** A bare pin or watch covers a key by its last part (`statechange.covered`: `HP`
   covers `서연.HP` and `민지.HP`), a full one only itself; `core_keys` and `statewatch.detect` use it, and
   `statewatch.flags_of` reads the chat's whole history when a watched key is bare.
4. **The rules version does not change.** The parse is deterministic and derived per reply; no stored row is
   rewritten.
5. **A status question about every window** is `packet-v21`'s (ADR 0092 item 12); earlier policies keep PHASE-39 Q3b.

## Consequences

- Measured on recorded inputs (every parse input of the status, state, parser, pin, watch and clock tests and the
  example rules, replayed at `5260794` and at the change): 145 inputs had keys at the base, 450 keys compared; 25 base
  keys in 10 inputs are missing after (9 replies with two or more named windows, prefixed by design and covered by bare
  pins and watches; 1 a `<style>` rule the base read as a key); 6 values differ, each a base misread.
- On the reply where a bare `HP` becomes `서연.HP` and `민지.HP`, the model is told both values with no link to the bare
  key before it.
- A value the earlier rules misread is read right from the next reply on and shows once as a change on that turn.
- A place is told from a character only by its keys: two places' windows in one reply sharing a non-scene key are
  prefixed like two characters' (K56). The owner's decision said a place is never an entity.
- `flags_of` with a bare watch reads the whole state history of the chat (the Inspector's flags, not the request path);
  not measured at size.
- Not built: binding a window's rules to a card id (PHASE-67).
