# 0056 — "At first": how it started, when the message asks

Status: accepted, 2026-10-01 (Phase 21 step 2, `docs/phases/PHASE-21.md` Q1–Q5, approved by the owner; AGE-26). Amends
ADR 0020 (a `minor` event's lexical bar) and the event cap of PHASE-7 Q4 and ADR 0026 for one kind of message. No
migration, no plugin build, no new packet policy.

## Context

"처음에 둘이 같이 만든 게 뭐였지?", "처음에 뭐라고 불렀지?": the answer is the oldest of several similar things. Fact
selection gave the slots to the newest. The event cap orders events by mention, `major`, score and then the newest
(PHASE-7 Q4, ADR 0026), and a `minor` event stays a candidate only when the message shares 35 % of its words (ADR 0020):
on the owner's M0 main chat the two first-turn events of a first baking were left out for later `major` events of the
same character. And a fact whose source is in the chat window is never sent (D3): when a pair's current form of
address was in the window, its first version, outside it, went with it — the packet prints a standing fact's earlier
versions (ADR 0038), the window does not. Measured on replays (Q6): M0 main 6/10, a restored production copy's
generated first-cue probes 6/8.

## Decision

1. **The cue** (Q1). `facts.FIRST_CUE`, a regular expression on the user's message: 처음 (맨 처음), 최초, 예전, 옛날, 원래,
   초반, 첫 followed by a space, 번 or 째 (첫 만남, 첫번째, 첫째; not 첫눈), and "at first", "first time", "originally",
   "in the beginning". From the message only, like the "why" cue (ADR 0040); no model call (the owner asked that a model
   call classifying the message be reviewed later, outside this phase).
2. **Events and ties** (Q2 a). With the cue, for that request only: the event cap orders events **mentioned first —
   whether, not how strongly — then oldest first**, then `major`, then score; a `minor` event needs no lexical bar;
   among all facts equal scores go to the older one. "Whether": a mention's score also carries a secret's or the
   persona's bonus, which would put a newer event first; ordering by the score left the M0 case failing (6/10), by
   whether it is mentioned it passes (7/10). Facts other than events keep their score order.
3. **History the window does not hold** (Q2 b). With the cue, a fact whose source is in context stays a candidate when
   it is a standing fact (`relationship`, `feels_toward`, `addresses`) and one of its earlier versions (`facts._prior`:
   the same predicate, another value, not a denial) starts before the window — at a head position lower than the lowest
   position of a message in context (`retrieval._window_start`, read only when the cue is there). When every version is
   in the window, the fact stays out as today. An event in the window stays out.
4. **No "last" cue** (Q3). "마지막에 / 최근에" change nothing: ties already go to the newest, and the packet prints the
   current version first.
5. **Replays** (Q4). `first_cue` is a recorded recall option, on for new requests; claims are ranked with it too. A trace
   that did not record it replays with it off, so a request from before this ADR replays as it was. The packet policy
   stays `packet-v10`; the budget and the fitter are unchanged (Q5).

## Consequences

- A message that asks how it started gets the oldest similar events and a pair's first form of address or relationship,
  even when the window holds the current one.
- With the cue, newer events of a mentioned character can lose their slots to older ones; a cue word used in another
  sense ("원래 그래") does the same. Measured on the synthetic chat's 25 cases at two cuts: no change (23, 24).
- A request with the cue makes one more indexed read (the window's lowest position).
- Evaluation, latency and the remaining misses (mostly a given name without the family name, AGE-28): Phase 21 step 3.
