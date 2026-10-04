# extract-v16, focused: the rules come with the lists they are about (2026-10-04)

**The live gate (PHASE-28 Q5 (d)) on `7b7cc14`, `extract-v16` the default, stopped after S0main ×3: the real-chat
memory cases scored 7, 5 and 8 of 10 (the bar: at least 8 in every run; `extract-v15` on `e13dee7`: 8).** Two cases
failed in all three runs and passed on `e13dee7`: a tenancy between two characters (turn 37) and the first thing two
characters made together (turn 0). The extractions had no wrong ending, no false join and more rows than
`extract-v15`'s (423–443 against 391), but fewer roles (5, 4 and 2 against 11) and, at turn 0, no shared-activity event.
Fixed-input probes on the same turns found the cause in the prompt, not the order: every `extract-v16` turn carried
the role-ending rules and the alias check twice, and the model stopped writing ordinary new facts. This note records
the probes and the change. S0main is the owner's real chat: aggregates and turn numbers only. S1 is the synthetic story.

**High risk:** extraction generations (a new `extract-v16` generation), current versus historical role state,
identity through aliases.

## Probes

Each probe sends one turn's prompt, built by the worker's own functions from a read-only copy (S0main: the gate's
run 1, `nmos_age24_7b7cc14_s0main_1`; S1: Phase 30's first connection, `first_p30_1388ea2_s1`), to `gemma4:31b-cloud`
several times. The cloud model varies between batches (S1 turn 155's nickname: `extract-v16` 4/4 in one batch, 0/4 in
the next), so a single small batch shows a direction only; the decisive rows were repeated.

| Prompt | S0main 37: tenancy written | S0main 0: shared-activity event | S1 233: resignation ended "now" |
|---|---|---|---|
| `extract-v15` | 4/4, 6/6, 5/5 | 3/4, 3/6 | (lists no roles) |
| `extract-v16` as merged | 0/4, 0/6, 0/6 (4/5 once) | 0/4, 2/6, 1/6 | 4/4 |
| v16 without the role-ending rules | 4/4 | 1/4 | — |
| v16 with v15's alias rule, no alias check | 4/4 | 3/4 | — |
| F1: role-ending rules in the user prompt; alias check once, always | 1/6 | 2/6 | 0/4 ("planned") |
| F2: as F1, alias check only with NAME PAIRS | 6/6 | 3/6, 1/6 | 0/4 ("planned") |
| F3: as F2, the unlisted-pair guidance in the system prompt | 6/6 | 4/6 | 0/4 ("planned") |
| F4: v16's system without the alias check; the check only with NAME PAIRS | 0/6 | 3/6 | 4/4 |
| **F5 (adopted)**: F3, and the role-ending rules in the system prompt at their place only when CURRENT ROLES are listed | 6/6 (= F3: no role listed) | 4/6 (= F3) | **4/4** |

Moving the role-ending rules into the user prompt turned the resignation into "planned" (F1–F3), the failure of the
`c0b0a5b` run; keeping them, and the full alias text, in every system prompt lost the new roles (v16, F4). F5 keeps both.

F5 against `extract-v15` and v16's corrections on other turns (4 runs each; S0main 6):

| Turn | What it tests | Result |
|---|---|---|
| S0main 31 | a new role while a role is listed | 6/6 (v15 6/6) |
| S0main 72 | a new role, none listed | 1/6 (v15 2/6) |
| S1 1 | a free alias (오봉순 / 오 사장) | 4/4 (F3, same system) |
| S1 18 | a listed NAME PAIR (강무진 / 무진) | 4/4 by number |
| S1 87, 159, 233 | the move, the attic, the resignation | ended "now" 4/4 each |
| S1 88 | settling in: kept | no ending 4/4 (v15 restated the listed attic role; F5 does not, the role stays current) |
| S1 149, 159 | a new role while roles are listed | 4/4 each (v15 4/4) |
| S1 155, 193 | a nickname with no NAME PAIRS (윤하람 / 람이) | 0/4 (v15 0/4; v16 4/4 and 0/4 in two batches) |
| S1 193, 200 | v16's wrong 도도 aliases (held by the confirmation) | none |

What F5 gives up: a nickname on a turn with no NAME PAIRS, which `extract-v15` never wrote either and `extract-v16`
wrote unreliably. S0main 31 also proposed ending the listed student role with two passages joined by "...", which the
worker's quote check does not accept; the live gate's review counts every applied ending.

Calls: 466 probe calls (10 + 48 + 160 + 120 + 40 + 88), all `finish_reason` `stop`, no HTTP error; the gate's three
S0main runs 249. Owner-local evidence: `/home/grantkim725/nmos-eval/age24-v16-7b7cc14/` (`probe37/`, `ablate/`,
`ablate2/`–`ablate5/` with every reply and `summary.json`; the scripts `probe_turn37.py`, `ablate_roles.py`,
`ablate2.py`–`ablate5.py`; the gate's `run/S0main-{1,2,3}/`).

## Change

`extract-v16` (a new generation; `extract-v15` unchanged):

- `SYSTEM_V16`: `extract-v15`'s system prompt with the part-name alias rule and the guidance for unlisted pairs
  (`ALIAS_RULE`) and v16's answer shape. `SYSTEM_V16_ROLES` adds the role-ending rules at their place; the worker uses
  it only when CURRENT ROLES are listed (`prompt_of(compiler, roles)`). `PROMPTS["extract-v16"]` is the full form.
- The NAME PAIRS answer (`PAIRS_RULE`) and the alias check come once, at the end of the user prompt, only when NAME
  PAIRS are listed.
- The generation names both system prompts, the NAME PAIRS rule and the alias check.

Next: a fresh sequential S1 on the merged change (roles 7/7, names 3/3), then the live gate from the start.
