# `extract-v9`: salience by change, revealed names, owner links — evidence

Date: 2026-09-25. Branch `salience-reveal` (ADRs 0024, 0025). Models through Ollama at
`http://127.0.0.1:11434/v1`, temperature 0: `gemma4:31b-cloud` (the owner's extraction model) and
`deepseek-v4.1-flash:cloud` (the model of the Phase 5–8 tiers).

## 1. The owner's chats (read-only, chat text not committed)

The owner's two chats were read from the production database with a read-only session and never
changed. A scratch script (not committed) built each prompt exactly as the worker does
(`build_prompt`, `entity_hints`, `promise_hints`, `normalize`) from the chat's normalized messages and
its `extract-v8` facts before the target turn, and sent it with the `extract-v8` prompt (a worktree of
`1340f61`) and with the final `extract-v9` prompt, 3 runs per turn. Only counts are reported here.

Production state before (`extract-v8`, one run): 5 of 46 events `major` in the 61-turn chat; the
missed turning points are the rows below.

| Turn kind (turns) | `extract-v8` runs with a major event | `extract-v9` |
|---|---|---|
| Speech level changed (t13) | 0/3 | 3/3 |
| New form of address (t39) | 0/3 | 2/3 |
| Relationship allowed (t41) | 0/3 | 3/3 |
| Speech level changed (t46) | 0/3 | 3/3 |
| Admission of responsibility (t27) | 0/3 | 2/3 |
| Device destroyed, rank test suspended (second chat, t1) | 0/3 | 3/3 |
| Already major with v8 (t28, t31, t36, t50, t58) | 3/3 each | 3/3 each |
| Routine: meals, chores, errands (t17, t21, t47, t55; second chat t3) | 0/3 each | 0/3 each |
| First kiss on the ear (t52) | 0/3 | 0/3 |
| Borderline gifts or gestures (t12, t60) | 0/3 | 1/3 each |
| Mixed turn: chores plus switching to informal speech (t15) | 0/3 | 1/3 (the speech change) |

No routine event was labeled major in any run. The admission is major in 2 of 3 runs; in the others
the model records the past act ("signed the list 4 years ago") as a minor event. The ear kiss stays
minor after a turn that was already major (t50).

**Revealed name.** A character first shown without a name (t19) and named in the next turn (t20). The
rabbit ears that identify her sit at character 3,636 of a 3,834-character reply, beyond the 2,000
characters a context message is cut to (D21). Chained runs: t19 extracted with `extract-v9`, then t20
extracted with those facts as history.

| Variant | t20 `also_called` linking the name to the `?` description |
|---|---|
| `extract-v8` (description never listed) | 0/3 |
| `extract-v9`, UNNAMED CHARACTERS listed by name only | 6/9 (3 chains × 3; 0/3 when the latest row about her was dialogue only) |
| `extract-v9`, final: each unnamed character with the rows that describe it (trait, identity, status) and its latest row | **12/12** (6 chains × 2) |

t19 named her with a `?` description in every chained run (`?토끼 귀의 인물`).

## 2. Synthetic scenes (`tools/eval_v9_model.py`, committed)

New Korean scenes written for this evaluation (not a user's chat), 3 runs each. Raw runs and summaries:
`fixtures/model/v9/2026-09-25-*`. `v8` columns: the same scenes with the `extract-v8` prompt, in the
same run.

| Scene | gemma v8 | gemma v9 | deepseek v8 | deepseek v9 |
|---|---|---|---|---|
| major: admission | 0/3 | 0/3 | 0/3 | 3/3 |
| major: speech level | 0/3 | 3/3 | 2/3 | 3/3 |
| major: form of address | 0/3 | 0/3 | 0/3 | 3/3 |
| major: relationship allowed | 0/3 | 0/3 | 1/3 | 2/3 |
| major: device explodes | 3/3 | 3/3 | 3/3 | 3/3 |
| routine ×3 (no major event) | 3/3 ×3 | 3/3 ×3 | 3/3 ×3 | 3/3 ×3 |
| unnamed: first sight (a `?` name) | 0/3 | 3/3 | 0/3 | 2/3 |
| unnamed: reveal (valid `also_called`) | 0/3 | 3/3 | 0/3 | 3/3 |
| no reveal ×2 (no `also_called` on the description) | 3/3 ×2 | 3/3 ×2 | 3/3 ×2 | 3/3 ×2 |

gemma's three misses extract **no event at all** in those short dialogue scenes (it records feelings
or relationships instead), so no label is given; on the owner's longer turns it did extract and label
them (section 1). No false reveal in 24 control runs.

## 3. Phase 6–8 bars with `extract-v9`

Baselines: the same scenes with the `extract-v8` prompt, run the same day
(`fixtures/model/v9/*-v8-baseline`). Differences of one run in three are within the variance these
tiers showed before (PHASE-8 "minor-repeat").

| Set | deepseek v8 → v9 | gemma v8 → v9 |
|---|---|---|
| Phase 6 end, damaged, whereabouts | 3/3 ×8 → 3/3 ×8 | 3/3 ×8 → 3/3 ×8 |
| Phase 6 lost map | 1/3 → 1/3 | 0/3 → 0/3 |
| Phase 7 promises open, kept, broken, controls, reported | 3/3 ×15 → 3/3 ×15 | 3/3 ×14, kept: lighthouse 0/3 → 3/3 ×15 |
| Phase 7 released (letter, daily letters) | 3/3, 3/3 → 2/3, 3/3 | 3/3, 0/3 → 3/3, 0/3 |
| Phase 7 major ×4 | 3/3 ×4 → 3/3 ×4 | 3/3 ×4 → 3/3 ×4 |
| Phase 7 minor walk, meal, chores | 2/3, 3/3, 2/3 → 2/3, 3/3, 0/3 | 3/3 ×3 → 3/3 ×3 |
| Phase 8 participants ×10 | 3/3 ×9, destroyed 2/3 → 3/3 ×9, destroyed 1/3 | 3/3 ×7, giving ×2 and destroyed 0/3 → same |
| Phase 8 controls ×4 | 3/3 ×4 → 3/3 ×4 | 3/3 ×3, absent householder 0/3 → same |
| Phase 8 secret about a shared event | 2/3 → 2/3 | 0/3 → 3/3 |

Every failing Phase 7 minor-scene run extracted no event (as in PHASE-8); none labeled a minor scene
major. gemma's Phase 8 misses are the same with both prompts: it records a handover as two `possesses`
facts and a burned diary as `destroyed` without an event carrying the other person, and it names the
householder of an empty house as a participant. No bar got worse with `extract-v9` on gemma; on deepseek
three scenes lost one run (released letter, destroyed by another) or extracted no event (chores), within
the variance of the earlier tiers.

## 4. Prompt cost

Mean prompt tokens on the Phase 6 control scenes: gemma 1,843 → 2,195, deepseek 1,824 → 2,170
(+≈350, +19 %), from the longer salience rule and the unnamed-character rule. The UNNAMED CHARACTERS
block and its closing line appear only while an unnamed character is listed.

## 5. Real host (PocketRisu v1.12.0, isolated)

An isolated PocketRisu (`ghcr.io/pocketrisu/pocketrisu:latest`, own save directory, port 6125), the
branch's sidecar and worker, the plugin built from the branch, and a deterministic extraction stub
(scratch, not committed) that answers from the prompt it receives. The owner's stack was not touched.
This run predates the "seen in turn" lines of the final hint block; the path it checks is the same.

- A turn showing someone without a name produced a participant `?흰 토끼 귀의 여자`. The next turn's
  prompt listed it under UNNAMED CHARACTERS with the closing line; the stub's `also_called` was stored
  valid, and the entity list showed one entity **라디아** with both names and the alias turn.
- A second unnamed participant (`?검은 망토의 남자`), never revealed, was joined to **카이** in the panel:
  Inspector → the conversation → character picker → the entity page → "같은 대상으로 합치기" → 카이 →
  "합치기". The panel moved to 카이's page; the profile showed both names and "?검은 망토의 남자 = 카이"
  under "소유자가 합친 이름"; 카이's mentions went from 1 to 2 and the event he took part in appeared.
  "해제" split them again at the next read.

## 6. Tests

`apps/sidecar/tests/test_reveal_and_links.py` (prompt rules, hint block, alias evidence, resolver
rules for reveals and owner links, the API, rebuild keeps links, delete removes them), the updated
`test_participants.py`, and `adapters/pocketrisu-plugin/test/inspector.test.ts` (entity page helpers).
Full suites: sidecar 296 passed, plugin 88 passed.
