# Role endings: what NMOS may apply alone, and what the owner sees

Status: **proposal for the owner's decision** (2026-10-03). Nothing here is implemented or approved. Written on
Codex's recommendation after the v4 re-measurement (`0e5978e`): stop, and decide by design which endings are applied
automatically and which a person checks, starting from the gap that a held ending needs one of two calls to say no.

## What the evidence says

- **The two calls are not independent.** The extraction and the confirmation are the same model reading the same
  TARGET; they share its blind spots. At S1 turn 227 both accepted the patronage's end under v3 (quote: the patron
  loses her office) and the confirmation did again under v4 (quote: she is in prison). The answer stayed; only the
  quote moved. A third call of the same model, or another paragraph, samples the same belief.
- **Wording moves other cases.** v4's one paragraph left 227 accepted and withheld an unrelated normal resignation
  (S2 turn 233): 30/32 against v3's 31/32. Prompt edits are not a reliable way to remove one error class.
- **`pending` is a disagreement detector, not a safety net.** It holds an ending only when a call says no (turn 88
  is the one case it caught). Two wrong yeses pass, and nothing shows them to anyone.
- **The volume is small.** S1 (240 turns) sent 7 confirmations: 7 listed endings past the deterministic checks.
  A person looking at each ending costs about one look per 35 turns on this story.
- **No deterministic, language-neutral signal separates 227 from a normal ending.** Its quote is in the TARGET, has
  no `LATER` cue, and names one of the two parties (`role_party_named`). Any word-overlap rule between the quote and
  the role text would be per-language (NMO-34).

So no class of ending can be called safe to apply unseen on this evidence. What can be designed is how an ending
is seen and undone.

## Proposal

Keep every check that exists (numbering, `when`, `quoted_in`, `LATER`, counterpart, v3 confirmation). Change what
happens after them:

| Case | Today | Proposed |
|---|---|---|
| Both calls yes | applied, unseen | **applied and listed**: "Needs attention → role ended automatically", with the role, turn and both quotes, and one action to keep the role (undo) |
| Calls disagree, invalid or failed call | `pending`, trace only; the role stays current with no way to apply it | **held and listed**: same list, one action to apply the ending, one to dismiss |
| Owner does nothing | — | applied stays applied; held stays held (both stay listed until acted on or the role ends again) |

- This is the pattern NMOS already uses where it cannot be sure: ambiguous names, thread endings that match no open
  thread, facts lost on re-extraction and disputed
  facts are listed under the Inspector's "Needs attention" with their repair (PHASE-13 Q6, ADR 0044; K8 was closed
  on "the panel is the fix"). Owner repairs are stored input applied at read time, so a rebuild or a new generation
  keeps the owner's choice (ADR 0044 item 2: matched by what the item says, not by row id).
- It closes both gaps at once: a wrong double yes (227) becomes visible and undoable; a correct ending that was held
  (the cost recorded in ADR 0064 item 4) gets a way to be applied.
- No extra model call, no prompt change, no per-language rule.

### What it needs (to be confirmed in a spec)

1. A listing of a chat's automatic and held endings: both are already stored (the ending's assertion and
   `extraction.raw["confirmations"]`), so this is a read.
2. Two owner actions. Either new repair kinds (`role_keep`, `role_end`: `owner_repair.kind` has a CHECK constraint,
   so a migration), or `fact_retract` / `fact_restore` if an automatic ending already shows as a fact the owner can
   act on. **Unverified**: which of the two fits is the first thing the spec must check.
3. Inspector rows in "Needs attention" (existing section) and their tests.

High risk (AGENTS §14): current versus historical state, owner repair, migration if new kinds are needed.

## Acceptance changes this implies

The PHASE-28 stop condition "a wrong role ending on any measured chat" assumes automatic endings can be made exact.
On this evidence they cannot with one model. Proposed instead, for the owner to decide:

- every automatic ending and every held one is listed and reversible in one action (tested);
- wrong automatic endings are counted and reported per run, with a ceiling the owner sets (S1 today: 1 of 7);
- a wrong ending of a kind not seen before still stops a run, as now.

## Considered and not proposed now

- **A third call, or a v5 paragraph.** Same model, same belief (227 under v3 and v4).
- **A second, different model as verifier** (another LLM, or a multilingual entailment model). The only way to get
  errors that are not correlated, but it adds a dependency, a cost and its own language coverage to measure. Worth a
  bounded experiment after the review flow exists, not before: without the flow, its errors would be unseen too.
- **A reranker.** Reranking orders retrieval candidates; it does not judge whether a turn ends an arrangement, and
  the failures here are extraction judgments, not retrieval.
- **Never applying endings automatically** (all held). Safe, but every normal ending waits on the owner, and an
  owner who does not look keeps every ended role current (the turn-73/87 class this phase set out to fix).
- **Showing "possibly ended" in the packet** with the quote, so the narrator weighs it. Packet policy is outside
  Phase 28 (Q6); a later option once the review flow exists.

## Next

1. Owner: accept or change this direction, and the acceptance change above.
2. Claude: a spec (phase step or amendment) that verifies item 2 above against the repair code first, then
   implementation with tests; no model call.
3. Then, with the owner's approval, the fresh S1 from turn 0, reporting automatic endings, held endings and wrong
   ones separately.
