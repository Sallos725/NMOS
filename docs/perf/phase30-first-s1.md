# PHASE-30 measurement (b): S1 first connection in story order (2026-10-04)

**Passed: role scenes 7/7, names 3/3 at turn 239, no false join, no technical error.** The newest-first first
connection on PHASE-28 Q5 (c) scored 4/7 and 1/3 (`extract-v16-q5c-s1.md`). Measured on `1388ea2` (#260; the product
code is the same at the PR's head, which changes only tests and docs after it), generation
`extract-409d69e00030e6052c6125fa4520d5db` (`extract-v16` as merged in #251), owner-approved (budget $1). Not a release
or default-switch verdict; `extract-v15` remains the default.

**High risk:** extraction order and generations, current/historical role state, identity and provenance.

## Lane

The PHASE-28 Q5 (c) first-connection envelope, the order the only change: the synthetic S1 (240 turns) synced at once
into a fresh database with all 240 turns in the window, extracted by the real worker, one worker, main `max_tokens`
8,192, confirmations under one 64-call ceiling, input stop 4.2M, a cost stop at $0.95, no retry; graded by prefix reads
before and after each declared scene and the names at the end, every alias and negative role reviewed afterwards.
The worker took the turns in order: 0, 1, 2, … 239.

| Declared scene | Newest first (`cc1f6e9`) | Story order (`1388ea2`) |
|---|---|---|
| 74 mentorship | kept | kept |
| 86 eve of the move | kept | kept |
| 87 move | **not ended** | ended |
| 88 settling in | kept | kept |
| 99 promotion elsewhere | **no role before the scene** | kept |
| 144 shop closure | kept | kept |
| 233 resignation | **not ended** | ended (the employee's side applied; its reverse held for the owner, ADR 0064 item 4) |
| Names: 강무진/무진, 윤하람/하람, 백이안/이안 | 1/3 | **3/3** |

The two lanes ran on different `extract-v16` generations (`b88669ca…` then, `409d69e0…` now, the review fixes of #251
between them). The backfill lane on the current generation (sequential S1 on `6e4ca05`) scored 7/7 and 3/3 as well.

## Review of every alias and negative role

Aliases served: 서도윤/도윤 (the persona), 오봉순/오 사장, 서정호/정호, 강무진/무진, 백이안/이안, 윤하람/하람,
추오월/오월, 윤하람/람이 (155, 193, 212, 217): each correct. Held: `윤하람 → 도도` at 200 (the confirmation said no:
도도 is how 하람 addresses 도윤, PHASE-29), and the persona's `서도윤 → 도도` (182, 185, 193, 217) and two non-character
aliases as not stated in the turn. No name is ambiguous at the end.

Endings applied: 87 (the inn stay), 159 (the attic), 219 (the inn help), 233 (the navigator), 234 (the captain's side):
the story's real endings. Held: 89 (the attic, confirmation no; correct, the stay continues) and 233's reverse.

**One wrong timing, outside the declared scenes.** At 134 the sponsor cancels the 300펠 commission ("300펠 약속은 이걸로
끝이에요"); the extraction recorded it as a broken promise (`promised`, negative) and not as the end of the listed
sponsorship, so the sponsor role stayed current until 227, where the arrest and the guild's dissolution ended it (the
extraction and its confirmation agreed). The final state is right; the role was current wrongly between 134 and 227.
This is PHASE-28's 227 class (one model, both calls wrong together), not the order: the sequential S1 on `6e4ca05`
ended the sponsorship at 134 under the same generation.

## Cost and time

252 calls (240 main, 12 confirmation), input 2,923,508 (cached 1,399,904), output 256,255: **$0.51 uncached** (약
700원; newest first $0.47: the lists add about 2,000 input tokens per call). 15.4 min with one worker; the newest turn's
facts were written last, at the end of the run (newest first: in the first seconds). No HTTP error, length or unparsable
reply.

## Evidence

Owner-local: `/home/grantkim725/nmos-eval/phase30/2026-10-04/first-s1-1388ea2/` (`PLAN.json` `275f6e10…`,
`run_first.py` `54f272c7…`, `result.json` `bae8ff15…`, `gold.json` `38eebd55…` (the Q5 (c) gold), every request and
body under `calls/`; database `first_p30_1388ea2_s1` on the bench Postgres; source worktree `/tmp/nmos-p30-1388ea2`).
