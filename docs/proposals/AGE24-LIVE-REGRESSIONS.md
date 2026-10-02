# AGE-24: improvement investigation after the live benchmark

2026-10-03. **Investigation proposal; no new phase or implementation authorized.** The [completed live run](../perf/age24-live-2026-10-02.md) meets the repeated real-chat target but fails the combined no-regression gate. Preserve those scores as the baseline for follow-up work.

## What to improve first

| Priority | Observed failure | Smallest useful experiment | Success means |
|---|---|---|---|
| 1 | Full/given names occupy different entities and retain different current histories (S2, S4b) | Existing owner-link preview, then inspect where explicit identity evidence was lost or never extracted | The intended identities share their history, without merging namesakes, changing persona boundaries unexpectedly or leaking secrets |
| 2 | Old guest and employment roles survive their ending (S1/S2) | Classify missing role-end extraction separately from an extracted negative that fails to match its earlier positive | Explicit endings close the intended role; unrelated roles, temporary travel and historical questions remain correct |
| 3 | Current-state questions select old location/address passages (S1/S2) | Fixed-candidate comparison of current-state support and excerpt selection, with before/first/why queries as controls | Current questions receive supported current evidence while history remains available on historical questions |
| 4 | Retrieved source/chunk contains the book title but its selected sentence omits it (S3) | Compare sentence/neighbor selection and fact ranking on held-out questions, preserving candidate sets and budget | Answer-bearing text survives selection without degrading other cases or increasing irrelevant content |

This order puts state correctness before retrieving more text. A larger packet alone can expose more stale evidence. Product changes to identity, versioning or packet selection are **high risk** for identity/provenance, current-versus-historical state, knowledge boundaries and fail-open behavior (AGENTS.md §14). This documentation PR changes none of those paths.

## Name linking: measured benefit and remaining problems

Two read-only diagnostics used the existing Phase 20 `facts.memory_view(..., what_if={"add_links": ...})` path. PostgreSQL connections enforced `default_transaction_read_only=on`. No links were saved, no successful extractions rerun, and no model or embedding requests made. [Aggregate diagnostic outcomes](../perf/age24-live-2026-10-02/owner-link-diagnostics.json) record the conditions and script hashes.

**S4b birthday:** the fixed selected candidates and uniquely reconstructed vector spans reproduced the original v11 packet ledger before the experiment. The unchanged given-name question did not receive the edited birthday. Assuming an owner link between the two names made the correct birthday appear, without the superseded birthday. Packet size changed from 5,275 characters / 2,576 estimated tokens to 5,808 / 2,810, within the same 4,000-token budget. This is one packet diagnostic, not a new live scenario score.

**S2 full-history state:** assuming only the given/full-name link for the clerk replaced four current facts and changed thread resolution. Specifically, the old polite address (assertion 950, turn 96) stopped being current; the later familiar address (220, turn 199) remained. Assuming all three tested protagonist/clerk/friend links changed the current-fact count from 438 to 415. These are reconstructed memory views at the recorded time, not complete packet replays or rescores.

The protagonist link also changes persona classification; the combined preview changes threads. Treat those changes as effects requiring review, not automatic wins. The preview does not itself prove that two names should be joined. Phase 24 deliberately refuses a read alias already occupied by another entity, and suffix similarity alone must not authorize an identity merge.

Crucially, after those three links the old guest role (517) still remains current. An employment-ending negative (45, turn 233) and the older positive employment role (103, turn 222) also both remain in the current view. The tested protagonist names now resolve together, so this surviving pair cannot be explained by that name split alone.

**Recommended next slice:** inventory explicit identity evidence in the failed scenarios; compare it to the extracted `also_called` evidence and resolver inputs. Use the existing owner preview for confirmed pairs. If the source explicitly identifies both spellings but the pipeline loses that information, propose a bounded correction with provenance. Otherwise preserve ambiguity and expose a reviewable candidate rather than silently guessing. Test each link independently before combined links.

## Roles: two separate failure modes

1. **No matching role end was extracted.** The guest role has one history entry. Leaving the room was extracted as negative `located_in`, which cannot automatically close `role_toward`. Locate the source evidence for ending the stay, and check whether the extraction context and prompt could express it. Do not infer that every departure ends tenancy, employment or another relationship.
2. **An end was extracted but its description differs.** `facts.version_key` groups a single per-object role by predicate and resolved subject/object; `facts.relation` additionally requires normalized value equality for the negative to end a positive. The employment descriptions differ (roughly, “worked on the named vessel” versus “works on the captain's ship”). The name-link diagnostic leaves this pair unresolved.

Do not drop value matching for all negatives: that could end the wrong role when the same people have several relationships. Compare bounded candidates such as separating role identity from descriptive evidence, or tying an explicit ending to a proven earlier role. Either needs a phase/spec and an architecture decision if the existing reconciliation rule changes. Prompt/registry changes need a new extractor generation; they cannot rewrite existing derived rows under `extract-v15`.

Start with the recorded positive/negative pair and source spans. Cover distinct simultaneous roles, explicit role changes, repeated descriptions, temporary absence, negation of a different role, and historical before/first questions. A successful identity fix must not be reported as fixing this separate lifecycle defect.

## Selection: distinguish finding a source from showing its answer

S3 retrieves the source and a vector chunk containing the title. The fact loses to standing relationship facts (rank 24, 16 selected); sentence anchoring favors a nearby name match. `memory_cut=0`, so increasing final token capacity alone does not explain or resolve the omission. Fixed-candidate v10 also misses the answer; disabling name variants also misses it. A blanket policy rollback is unsupported by these two-case S3/S4b controls.

Compare bounded selection candidates: less weight for name-only sentence matches when question content is available; retain an answer-bearing neighboring sentence within the same chunk; or adjust fact selection so broad standing relationships do not crowd out question-specific evidence. Avoid a rule specialized to the exact book question. Evaluate paraphrases and unrelated questions, and preserve the 320-character excerpt bound unless a separately approved spec changes it.

For S1/S2 current-state questions, inspect the current fact and old excerpt together. Test temporal support only where the trace and stored provenance establish it. Do not remove every old source: an early one-off fact and the “at first”/“why” cases need that evidence. Negated old titles and explicitly labeled history also require a different interpretation from obsolete facts served as current.

## Measurement before another expensive run

1. Keep the original raw rubric and all measured result files unchanged. Add a separate per-match classification: obsolete current assertion, irrelevant old excerpt, correctly labeled history, negation, or duplicate overlapping pattern. Do not convert that annotation into a retroactive pass.
2. Replay preserved extraction snapshots and candidates first. Require an exact baseline ledger reproduction before reporting a packet counterfactual; otherwise label it a memory-view diagnostic. Freeze query, previous reply, visible context, policy, budget, source membership and known-at time.
3. Test name handling, role reconciliation and selection independently before combining them. Check complete cases, forbidden matches and packet size, including edits/rerolls, branch/new-chat, first/why questions, persona/name collisions and knowledge boundaries.
4. If a proposed implementation needs new extraction, compare new-generation outputs on an isolated copy with fixed input, recording missing ends, unmatched negatives, token use and provenance. Do not overwrite this run or silently re-extract its baseline.
5. Only after the local controls pass, specify the next live run and budget. Repeat the changed failure scenarios to estimate extraction variability and retain the real-chat S0main repetitions. A changed packet score is not generated-answer accuracy.

The separate harness display-wait candidate can shorten future runs. It was not applied here and has only isolated browser checks; verify it in the real host before adopting it. Do not mix its wall-clock improvement with memory-quality claims.
