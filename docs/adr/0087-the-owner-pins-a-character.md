# 0087 — The owner pins a character (`entity_pin`, `@name`)

Status: accepted, 2026-11-23, PHASE-60 (S8). Builds on ADR 0044 (owner repairs), ADR 0076 (`entity_exclude`, the
opposite switch), ADR 0043 (`<Cast>`), ADR 0070 (what a name makes required). Migration `0038`.

## Context

A character enters the packet when the message or the scene names it. The owner sometimes knows better: a character
who matters to every scene without being named, or one the next reply should keep in mind.

## Decision

1. **A pin is an owner repair.** Kind `entity_pin`, naming its target by name and type as `entity_exclude` does, so it
   survives rebuilds and new generations, is archived, undone like any repair, and deleted with the chat. No new
   table.
2. **A pin makes a character present, not louder.** Under `packet-v20` a pinned character gets a `<Cast>` group and
   its now and standing facts are `required`, as if the message had named it (ADR 0070). Its other facts are ranked as
   before. At most 3 groups beyond the cast's 4, most recently pinned first; the budget bounds the rest.
3. **`@name` is a pin for one request, opt-in.** With `pin_at_mentions` on, an `@` at the start of a word followed by
   a known name or alias of a character of the chat. Exact after normalization, a trailing Korean particle allowed.
   An `@` inside a word, or before an unknown name, does nothing, so an address or a handle is left alone. Nothing is
   stored for it.
4. **Recorded.** A request records the names its pins resolved to (`recall_options.pins`); its replay uses them.
5. **An excluded name is not pinned.** `entity_exclude` wins: the owner said the name is not a character.

## Consequences

- A pin costs budget on every request of that chat; the panel shows the pins of a chat so they can be removed.
- `@name` does not change what is stored or extracted: the message is kept as typed.
