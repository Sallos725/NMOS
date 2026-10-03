# extract-v16: an alias on first introduction, and a conflicting short name

2026-10-03, PR #251. **High risk: identity/provenance and current versus historical role state.**
The owner approved correction, sequential verification, then a fresh comparison with at most three
simultaneous model calls after the failures recorded in `extract-v16-fixed-hints-and-glass.md`.
The v15 default and its generation remain unchanged. This is not completion of Q5(c) or the live gate.

The independent glass-garden probe has no stored entity hints. On the old prompt it missed an alias even
when a newcomer explicitly gave both names and the narrator showed that person answering to the short
name. Numbered NAME PAIRS do not cover this first introduction. The v16 rule now distinguishes the two
paths: a listed pair uses `same_names`; an unlisted, evidenced pair uses `also_called`, even when the model
also writes an `addresses` fact or an event. An identity stated only by a character remains a claim.
The same check closes the input. It is also included in the system prompt fingerprint, so its change
creates a new generation. The worker and both evaluation tools pass the selected compiler to the input
builder; v15 gets no new reminder.

## Measured model results

The existing 14 authored synthetic cases and their gold checks were unchanged; no entity hints were
added. Three independent repeats, temperature 0, `gemma4:31b-cloud` through the owner's existing endpoint
`http://127.0.0.1:11500/v1`. Provider replies and usage were captured before parsing. No retries.

| Candidate | Actual calls | Observed result | Input / output tokens |
|---|---:|---|---:|
| System rule alone | 27 | First eight role cases 24/24; first name case 1/3, then stopped | 136,350 / 19,803 |
| System rule and closing check | 42 | All 14 cases pass in each repeat, 42/42 | 219,120 / 30,966 |

The successful candidate's system SHA-256 is
`4ffec3cbf0e891b0b9508162a90a39337a91d909e0f34ef86da3603a5d42a410`;
its extraction source SHA-256 is
`193941e253e96234a1f4f1cef31f45c6783b0701c2848f12c1f26e31aab175ed`.
Its full sidecar suite passed 947 tests (651.47 s, two dependency warnings).
The raw model run preceded `16c23e6` and must not be presented as a fresh model run of that commit.

## Integrating the counterpart change

`16c23e6` also allows a counterpart's given name without a stored alias when no other known full name
shares it. Replaying a negative control exposed a regression: when two characters explicitly own the
alias `무진`, the new name-part path re-added it after the existing ambiguity check removed it. This also
occurred when only the other character owned that alias. Both tests failed at the expected rejection.

The integrated check treats another character's explicit alias ownership as a blocker too. A bare
short-name entity still allows the unresolved split, as `16c23e6` intended. A distinct namesake known only
by that bare short name therefore remains a limitation; the check is a prerequisite, not identity proof.
It does not create an alias or join entities.

On the integrated source (`b054d160ac1730637fafd966da1aaf8d4e9c4ed74ac6ab470a805a9c6cb85d60`):

- Related tests: 59 passed, including the v15 pin, worker prompt delivery, real worker/API state checks,
  full-name collisions, persona handling, and both newly rejected alias-owner controls.
- **Offline replay only:** all 42 glass-garden replies still pass. The three preserved S1 resignation
  replies close the employment with their original hints; adding the conflicting alias owner blocks all
  three. No model calls or persistent sequential worker success are counted for this replay.
- A full-suite attempt from a flattened source snapshot could not locate migrations, causing 297
  failures and 118 setup errors. That runner setup is invalid evidence about product behavior. Its log
  is retained; the corrected run from the repository source layout passes **950 tests** (648.45 s,
  two dependency warnings).
- The actual sequential S1 extraction stopped at **88/240** after the move check failed. The earlier
  mentorship and eve-of-move checks passed. Input 863,423 / output 91,638 tokens; no errors or retries.
  The new generation had already joined the captain's names at turn 18 and both original split pairs
  by turn 33, confirmed by stored state readback. These alias successes did not make the move succeed.

## The sequential title omission and its correction

At turn 87 the model correctly reported R5 as ended now, with a TARGET quote. The stored counterpart
was `오봉순`, while the scene used `오 사장님`; earlier extraction had omitted the distinctive title alias.
The guard therefore rejected the ending. This is a missing alias upstream of the counterpart check,
not a wrong model ending or a packet-budget issue. In-memory replay with the previously measured v15
alias `오 사장` keeps the ending. That counterfactual is not a new model or worker success. The failed
copy, replies, stored readbacks and a complete archive are preserved.

At 88 calls this is within the owner's automatic-correction window. The v16 free-alias rule and closing
check now explicitly include a distinctive name-like title when the TARGET identifies that same person.
Shared generic titles are excluded; a character's unconfirmed identity claim stays a claim. The guard,
quote check and resolver do not change for this correction.

The new source SHA-256 is `13dd7d9d5028872a0051b638d4d7e958b63b6fc0e36d5350a2e4ad2b8117ee8e`,
the system SHA-256 is `6eea98fd21e8a0ad8cb40194b4b5d0bd47cefc2f791aca1b6f733675951d3548`, and the
generation is `extract-a5425536646f8cc3cc6fb6d80686bcbf`.

A fresh **54/54** probe passes: the unchanged original 14 cases x 3 plus four separately authored
follow-ups x 3 (`tools/scenarios/glass-garden-followup.json`). The follow-ups check a distinctive title,
a title shared by two people, an unconfirmed identity claim, and explicit employment termination when
a business closes but friendship continues. That last control passes 3/3; implicit closure without
an explicit ending remains outside its evidence. Input 283,320 / output 40,881 tokens, no errors,
retries or missing usage. Related tests pass 59/59; its full suite passes 950 tests (707.55 s,
two dependency warnings).

Sequential S1 restarts from its original input on a new isolated copy, 240 planned calls and initially
3,403,981 estimated input tokens (hints change as extraction proceeds). The fresh fixed-v15-hints
comparison is prepared for 1,440 new calls, 20,474,331 estimated input tokens, at most three concurrent
calls, no reused outputs. Both scenarios' known role cases now come first; inputs and gold stay fixed.
That comparison waits for sequential verification. A copied database runs the actual extraction
worker, stores assertions, and reads back the API and the read model through the scene. Reveal and
summary jobs and a live host are not run. That restart stopped at **87/240**, as described below.

## Preparing a move is still not moving out

The title correction's actual S1 worker stored the innkeeper's alias, but at turn 86 the model marked
packed luggage and a stripped bed as a completed ending. The same guest role was positive before the
turn and negative afterward in persistent readback. The accepted quote had no future word, so the
existing quoted-time check did not block it. The ending is premature: the character still spends that
night in the room and moves in the next turn. This is the model's time judgment, not an alias failure.
All 87 calls and the stopped copy's archive are preserved: input 853,016 / output 91,421 tokens, no
format errors or retries.

The system rule and final input check now explicitly distinguish packing, a stripped bed or farewell
gifts from completed checkout, and ask for the completed departure/termination itself. The same
`ROLE_COMPLETION_CHECK` is fingerprinted in the v16 system prompt and delivered by the actual worker.
It adds no parser heuristic. The new source SHA-256 is
`39a35eeba4f34edd919550271b89fd8aa3b5a49b7840e4ad65beaec0a9e9dcc0`, system SHA-256
`cc14ac3b8040d149408974baa31d430a8e73104fe8f7eb067a1ead7282ca8298`, generation
`extract-1ea447351329c1e64ab7e9f664e907b1`.

- The actual failed turn 86's context and stored hints, unchanged except for the new prompt: **3/3**
  fresh replies keep the guest role under the real normalizer/reconciliation check. Input 31,866 /
  output 3,096 tokens. This bounded comparison does not advance the stopped worker database.
- Original 14 glass cases plus four follow-ups, three fresh repeats: **54/54**, input 289,464 /
  output 41,682 tokens. Combined: 57 calls, no errors or retries.
- Related tests: **60 passed**. The final worker reminder regression failed at its missing-input
  assertion before the change; the v15 pin and the existing state checks pass afterward.
- The full sidecar suite passes **951 tests** (650.58 s, two dependency warnings); plugin tests pass
  196, typecheck and build pass. The fresh sequential S1 restart stops after 62 completed jobs, below.
  The 1,440-call comparison still waits for sequential verification.

The probe also needed a measurement correction: it previously removed every character claim before
entity resolution, while the product lets the resolver evaluate self-alias claims. It now passes all
valid rows to the real resolver and grades its accepted alias rows. A synthetic bad self-identification
wrongly passed the old probe and fails the corrected one; a valid self-introduction succeeds. Regrading
the title candidate's preserved 54 replies still passes all 54, without new model calls. The new 57-call
measurement uses the corrected grader. Product identity rules were not changed by this tool correction.

The diff-scoped self-review checked the identity/provenance risk, explicit conflict rejection, the
generation fingerprint, v15 isolation, compiler delivery, and unchanged quote and role reconciliation
rules. No schema, host, request path, default, or worker-order change is made.

## An address is not necessarily a name

The completion candidate (`6636ef3`) stops after **62 completed jobs / 64 attempts**. Turn 62 returns
an object with a comma after its last member twice, including its one retry. Code fences are tolerated
by the product parser and are not the cause. Input 631,905 / output 68,650 tokens; two format failures,
one retry. Both provider replies and the stopped database archive are retained.

Auditing that run also finds an identity defect at turn 34: Haram jokingly addresses Doyun as
`바다 박사님`, but the model records it as Haram's own alias. Production accepts self-alias claims;
the mistaken subject therefore matters. Persistent readback through turn 35 marks Haram ambiguous
and loses the previously established full/given-name join. Other bare titles were also over-extracted.
This is a wrong extracted fact, not a packet omission, and not evidence of an actual false merge.

The next v16 prompt distinguishes stable introduced names from casual or teasing addresses and bare
job/relationship titles, even when only one person is mentioned. A title alias must include a personal
name and be explicitly introduced as what that person is called. An honorific variant reuses the
existing alias spelling; the alias's subject is the person named, not the speaker. The closing check
also asks for valid JSON without a trailing comma. These prompt changes create a new generation;
the parser, identity resolver, schema, v15 and the role-ending checks remain unchanged.

The candidate source SHA-256 is `dcbbc3781156266a26a2fbcb3714834997a8d7b1a8e411f34eb7e53401364f04`,
system SHA-256 `258f7a43bfe3159f913f9ac2560d18b5bcc5684ab89525b371e2214fe0e22769`.
Related tests pass **60**. Two further synthetic negative controls cover teasing address ownership
and a bare job title; the original 14 cases and prior four follow-ups are unchanged. Bounded model
verification passes **69/69**: 20 independent cases x 3, plus three replies each to the preserved actual
inputs at turns 34, 62 and 86. Turn 34 checks that the teasing address creates no alias; turn 62 checks
JSON syntax only; turn 86 checks that the guest role stays. None writes to the old stopped database.
Input **426,798 / output 54,939 tokens**, zero errors, retries or missing usage. The source/system hashes
above pin this run; generation `extract-7e9f41da3278af76f30d8b6ffa5c646a` is new.

A fresh actual S1 backfill starts from turn 0 on its own copy, **240** planned calls and initially
**3,515,497** estimated input tokens. It remains in progress. The 1,440-call fixed-hint comparison
waits for that result; no full comparison or Q5(c) pass is claimed. The scoped review checked the
unchanged v15 path, fingerprinted worker input, preserved original probe cases and unchanged parser/
resolver rules. This remains high risk for identity/provenance and historical/current role state.

Local evidence stays under `/home/grantkim725/nmos-eval/pr251/2026-10-03/`:
`alias-fix-system-v1/`, `alias-fix-closing-v2/`, and `alias-fix-integrated-v3/` retain the distinct
candidates, hashes, raw replies, negative controls and logs. `RESULTS.md` links to actual files.
`sequential-alias-v3/` holds the stopped worker run; `full-alias-v3/` was prepared but made no calls.
`alias-fix-titles-v4/`, `sequential-alias-v4/` and `full-alias-v4/` separate the next generation's evidence.
`alias-fix-completion-v5/` preserves the final bounded checks; `sequential-alias-v5/` and `full-alias-v5/`
hold that candidate's executions. All three stopped sequential runs retain their original archives and
diagnoses. `alias-fix-scope-v6/` and `sequential-alias-v6/` separate the narrowed alias candidate.
