# 0085 — A chat that carries another chat's memory (`conversation_carry`)

Status: accepted, 2026-11-23, PHASE-60 (S6). Builds on ADR 0002 (a branch is a new conversation), ADR 0012 (identity
at read time), ADR 0047 (canon facts fold before turn 0), ADR 0027 (as-of replay). Migration `0036`.

## Context

A conversation's memory is its own (D14). The owner starts a new chat to continue a story, or to restart it with one
character who remembers (a regression story), and the new chat knows nothing. Copying assertions between chats would
break provenance (a row's revision belongs to the other chat) and rebuildability.

## Decision

1. **A link with a frozen reading.** `conversation_carry` records that a target chat carries a source chat's memory.
   It is owner input like `entity_link`: archived, kept by rebuilds, deleted with either chat. At link time the
   source is read once, with the readers a request uses, and the rows to carry are stored with the link as plain data
   (`snapshot`): each row with what the target's read needs (names and types, predicate, value, polarity, knowledge
   marks, participants, `because`, `feeling`, `when_happened` when present, a thread's kind and status, the turn it
   came from) and its provenance (the source conversation, the assertion, its source revision, the generation that
   served it); the story so far with its summary id. Nothing is re-read later. (Amended 2026-11-23, architect's
   decision: this replaces "the target's read asks the source's read".)
2. **Taken at the source's head and a position.** At link time the source's head is the cutoff: the reading is taken
   as of `(head, cutoff_position)`, the head's end or the last message of a turn the owner chose on the current head.
   `cutoff_commit_id`, `cutoff_position`, `cutoff_turn` and the generation keys read are kept on the link as its
   record. What the source says later, an edit, a rebuild or a new extraction of it does not reach the target; the
   owner links again (a new link; the old one gets `removed_at`) to take a newer reading. Not a pointer to the
   cutoff: only a head commit keeps `active_membership` rows (a divergence deletes the old head's, a rebuild every
   commit's), and keeping a non-head commit's membership would change reconciliation and every membership query.
   This is a deliberate reading of invariant 7: within a conversation an inactive revision never influences a packet;
   across the link, the owner froze a reading of another chat, taken from that chat's active membership at the time.
3. **Carried by name.** Entity ids are per conversation (D26). Carried rows enter the target's resolution as
   mentions, so the target's own aliases, links and splits apply; the source's persona maps to the target's.
4. **`continue` folds like canon.** Carried current facts are from before turn 0 and the target's story supersedes
   them (ADR 0047's fold), marked `source="carried"`. Open threads continue and can be closed by the target's story
   by text, as any thread is (ADR 0019).
5. **`regression` is memory, not truth.** The restarted world does not hold the earlier timeline's facts. Carried
   rows involving the named characters are offered only as limited knowledge of those characters, in their own
   group, and never enter current facts, cast, gone pins or open threads. Soft marks only (D19); hard isolation
   stays out of scope (D9). Nobody remembers what they never knew (amended 2026-11-23, coordinator's decision): a
   row's rememberers are, by its marks at the cutoff, all named for a public row, the named in `known_by` for a
   limited one, and only the named the row involves otherwise, always minus `hidden_from`; a row with none is left
   out. A kept row is stored `knowledge = limited`, `known_by` = its rememberers, `hidden_from` as stored, with its
   original marks beside them.
6. **One level, one link.** One link in force per target; a source's own link is not followed. Chains would make a
   read depend on an unbounded number of chats.
7. **A request records the link it read.** Its replay reads that link, removed since or not.
8. **The target's extraction does not see carried memory** in this phase: its prompt inputs stay a function of the
   target alone, so extraction rows stay valid whatever is linked.

## Consequences

- Provenance holds: each carried row records the source conversation, assertion, source revision and generation it
  was read from.
- The reading is not re-derived: a better extraction of the source, or a correction of it, reaches the target only
  when the owner links again. It is rebuildable from the ledger only while the source's head still holds the cutoff.
- Deleting the source removes what the target carried (the owner's delete, D23); the delete's answer counts links.
- A carried open thread is not listed to the target's extractor, so its closing depends on the text match alone.
- Raw excerpts of the source are not recalled in the target.

## Amendment (2026-11-25, PHASE-65 S5, audit F1–F4)

- **Regression.** May name the persona (`{{user}}` or any of its spellings), alone or with characters; it maps to the
  target's persona. A row's rememberers follow its knowledge marks for every row: all named for a public row, those in
  `known_by` for a limited one, otherwise those it involves, minus `hidden_from`; so world facts, item places and told
  third-party secrets are kept. Closed regression threads are returned by `carry.regression_threads` and offered by
  `packet-v21` only (ADR 0092 item 11).
- **Reading.** `MAX_ROWS` is 5,000 (was 2,000). Owner entity links and the named regressors' aliases are carried; a
  persona alias maps by spelling; a source's own `continue` link is read (a chain of chats, with the first chat's
  provenance, never the target's own memory back); the story is held at `LEAK_NEAR`.
- **In the target.** Carried rows fold as secrets (ADR 0033 amendment 4). Previews, joins, repairs, the repair list,
  the author's note and the memory map read the link in force; the link is part of a preview's fingerprint. A fact
  repair tells a carried fact from canon's (ADR 0044 amendment 4). Under `packet-v21` a death carried by a `continue`
  link stays pinned as gone.
- **Archive.** The manifest lists the links it leaves out and the chats they point to, by id; a single-chat export is
  still not self-contained (the link's foreign keys are `NOT NULL`).
- Limits: a repair of a carried row is tied to its link and orphans on relink; regression aliases are stored but only
  `continue` rows feed resolution.
