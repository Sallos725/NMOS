# 0085 — A chat that carries another chat's memory (`conversation_carry`)

Status: accepted, 2026-11-23, PHASE-60 (S6). Builds on ADR 0002 (a branch is a new conversation), ADR 0012 (identity
at read time), ADR 0047 (canon facts fold before turn 0), ADR 0027 (as-of replay). Migration `0036`.

## Context

A conversation's memory is its own (D14). The owner starts a new chat to continue a story, or to restart it with one
character who remembers (a regression story), and the new chat knows nothing. Copying assertions between chats would
break provenance (a row's revision belongs to the other chat) and rebuildability.

## Decision

1. **A link, not a copy.** `conversation_carry` records that a target chat carries a source chat's memory. It is
   owner input like `entity_link`: archived, kept by rebuilds, deleted with either chat. Nothing derived is written
   for it; the target's read asks the source's read.
2. **Frozen at a commit and a position.** The source is read as of `(cutoff_commit_id, cutoff_position)`: a commit id
   alone is not a cutoff, because an append extends the head commit in place (D4). What the source says later, or an
   edit of it, does not reach the target; the owner links again to move the cutoff. This is a deliberate reading of
   invariant 7: within a conversation an inactive revision never influences a packet; across the link, the owner
   froze a point of another chat, and that point's own membership decides what is active.
3. **Carried by name.** Entity ids are per conversation (D26). Carried rows enter the target's resolution as
   mentions, so the target's own aliases, links and splits apply; the source's persona maps to the target's.
4. **`continue` folds like canon.** Carried current facts are from before turn 0 and the target's story supersedes
   them (ADR 0047's fold), marked `source="carried"`. Open threads continue and can be closed by the target's story
   by text, as any thread is (ADR 0019).
5. **`regression` is memory, not truth.** The restarted world does not hold the earlier timeline's facts. Carried
   rows involving the named characters are offered only as limited knowledge of those characters, in their own
   group, and never enter current facts, cast, gone pins or open threads. Soft marks only (D19); hard isolation
   stays out of scope (D9).
6. **One level, one link.** One link in force per target; a source's own link is not followed. Chains would make a
   read depend on an unbounded number of chats.
7. **A request records the link it read.** Its replay reads that link, removed since or not.
8. **The target's extraction does not see carried memory** in this phase: its prompt inputs stay a function of the
   target alone, so extraction rows stay valid whatever is linked.

## Consequences

- Provenance holds: a carried line's evidence is a revision of the source chat, reached through the link.
- Deleting the source removes what the target carried (the owner's delete, D23); the delete's answer counts links.
- A carried open thread is not listed to the target's extractor, so its closing depends on the text match alone.
- Raw excerpts of the source are not recalled in the target.
