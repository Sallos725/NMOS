# 0041 — One numbering for `turn` in the packet (`packet-v7`)

Status: accepted, 2026-09-28. Found in the Phase 11 real-host smoke. Read side only: a new default packet policy
`packet-v7`, no migration, no extractor change. A new default changes what the model sees, so the owner was asked
first and chose `packet-v7` as the default (2026-09-28, the recommended option).
`NMOS_PACKET_POLICY` keeps `packet-v6` and earlier.

## Context

Since ADR 0008 a fact's `turn` in the packet is the **turn index** (a user message and the replies that answer it are one
turn; the greeting is turn 0); ordering and supersession use the message position. Claims, threads, secrets and the
"; before, turn N:" and "; but turn N:" text of facts use the same index.

Excerpts and parser state never moved: an excerpt's `turn` and a state item's `as_of_turn` are the message's **head
position**, as Phase 0 (`<Excerpt turn="148">`, before turns existed) and Phase 1 (`as_of_turn`) wrote them. No ADR
chose positions for them. ADR 0008 changed facts only; ADR 0027 records each ledger line's `turn` as the line has it,
and ADR 0035 gives a Secret line the turn of the line it replaces.

In the Phase 11 real-host smoke one packet held a Thread `turn="26"` for a goal message and an `Excerpt turn="56"` for a
message sent right after it. The model gets two scales under one attribute name, and a "before, turn N" or a secret's
turn cannot be compared with an excerpt's. On M0 (28 requests of the owner's chat, `docs/perf/m0-baseline.md`) the 16
excerpt lines were numbered 22 to 68 higher than the turn of their message.

## Decision

1. **`packet-v7` (default)** is `packet-v6` with an excerpt's `turn` and a state item's `as_of_turn` taken from the turn index of
   their message (`active_membership.turn`). The ledger records the same number, so the trace, the Inspector's
   "Last packet" and the packet agree.
2. **Excerpts stay in story order.** A turn's user message and its reply now share a number, so excerpts are ordered by
   position (`Excerpt.position`) under every policy; before `packet-v7` the position was the number, so the order is
   unchanged there.
3. **A message without a turn gets no turn attribute.** Comments, disabled messages and everything up to an
   `allBefore` cut belong to no turn (ADR 0008). Recall skips exactly those messages (D15), so an excerpt always has a
   turn; a state item parsed from a comment can lack one, and its `<Item>` then has no `as_of_turn`. The fallback the
   fact fold uses, `-1 - position` (`facts._unit`), is an ordering key that never equals a real turn; shown to the model
   it would be a third numbering. A Secret line already leaves `turn` out when its line has none.
4. **Recorded packets replay under their own policy** (ADR 0027). `packet-v6` and earlier still number excerpts and
   state by position, so their traces reproduce; `GET /v1/trace/{id}/replay?policy=packet-v7` shows the new numbers.
5. **The Inspector's state table** ("As of turn") shows the turn index under every policy, as its fact tables do.
   `GET /v1/conversations/{id}/state` gains `turn` beside `position`.

## Consequences

- **Memory evaluation** (`tools/eval_memory.py`, 154 packets over lexical, hybrid and full): the same gold, stale and
  irrelevant outcome for every case under `packet-v6` and `packet-v7`. No gold string depends on an excerpt's number;
  the three that hold a turn are fact lines. About a hundred of 199 excerpt lines get another number, and a packet's
  estimate falls by up to 2 tokens (a turn index never has more digits than the position). Cases with twelve equally
  scored excerpts pick different ones from run to run under either policy (score ties), so filler text was seeded to
  compare them.
- **M0** (28 owner cases, restored copy with `extract-v13` facts, budget 800, no vectors): 26 of 28 pass, 7 of the 9
  that need memory, 0 of 16 forbidden phrases placed, mean 774 tokens, under both policies. All 16 excerpt lines are
  renumbered; nothing else in any packet differs, and two packets are 1 token smaller. The M0 scorer
  (`tools/eval_rp.py`) is unchanged: none of its 63 phrases holds a turn number or markup, and its `before` rule reads
  fact turns, which were already indices.
- **Not measured:** whether a response model answers differently. The change removes a contradiction in the packet;
  it adds no memory.
- **Default:** `packet.DEFAULT_POLICY` is `packet-v7`. The compose files pass `NMOS_PACKET_POLICY` empty since this
  change, so they follow the image's default (they had kept `packet-v4` through two new defaults). Nothing is
  re-extracted; a sidecar picks the new default up when it restarts on the new image.
