# A join shown before it is made — measurements (Phase 20)

Phase 20 (`docs/phases/PHASE-20.md`, ADR 0055, D65). Measured 2026-10-01 on writable copies of the two restored
evaluation databases (`extract-v14` evaluation copies of the owner's backup; never production), counts only: no chat
text, names or ids leave the copies. Script outside the repository (`~/nmos-eval/phase20-preview/measure.py`), run
with the Phase 20 step 4 code.

## The owner's seven joins

Each of the owner's live joins was, in turn: previewed as an undo and taken back, the preview compared with the
difference read after; previewed as a join again and joined, compared the same way; and counted for the turns the undo
would re-extract (no model call).

| Copy | Join | Messages | Changes | Entities | Lines | Undo = preview | Join = preview | Turns to re-extract | Preview (median / max) |
|---|---|---:|---|---|---|---|---|---:|---|
| main | 1 | 69 | none | 1 → 1 | — | yes | yes | 0 | 12.1 / 18.0 ms |
| main | 2 | 69 | none | 0 → 0 | — | yes | yes | 0 | 9.3 / 19.9 ms |
| main | 3 | 147 | yes | 2 → 1 | 1 fact replaced | yes | yes | 52 | 33.1 / 35.4 ms |
| s2 | 1 | 69 | none | 1 → 1 | — | yes | yes | 0 | 18.4 / 21.5 ms |
| s2 | 2 | 69 | none | 1 → 1 | — | yes | yes | 0 | 14.7 / 16.6 ms |
| s2 | 3 | 147 | yes | 2 → 1 | 1 fact replaced | yes | yes | 53 | 31.1 / 32.5 ms |
| s2 | 4 | 69 | yes | 2 → 1 | — | yes | yes | 20 | 14.1 / 16.3 ms |

- **Every preview equals the difference its action made**, line for line, both ways (14 of 14).
- **Four joins change nothing**: the names are one entity already (1 → 1) or not both on the head (0 → 0). The
  preview says so ("nothing changes") instead of a silent no-op.
- **Two joins replace a current fact** of one name with the other's, by the story's order. Before Phase 20 nothing
  showed it. No join makes a relationship, promise or secret of a character with themself; those lines are covered by
  the deterministic cases (`tests/test_merge_preview.py`) and the real-host smoke.
- **125 turns** (52, 53 and 20) are served by an extraction made while their join held that lists the two names as
  one entity; the undo's preview offers to re-extract them. The spec's evidence said 72: that first count read only the
  active generation's extractions, and one chat's turns are served by an older generation (ADR 0014).
- **Preview time**: two memory reads, the difference and the re-extraction count, in process on the database host.
  At most 35.4 ms on the longest measured chat (147 messages), within the criterion of 200 ms. The request path is
  unchanged: a preview runs only on the owner's click.

## Deterministic cases and the real host

`tests/test_merge_preview.py` (sidecar) covers every line kind in both directions, compares each preview with the
difference read after its join, split or undo, the 409 after a new turn or an extraction on the same head, the
re-extraction against a never-joined twin chat, a job made obsolete while the model answers, and the refusals.
`test/inspector.test.ts` and `test/dom.test.ts` (plugin) cover the wording, the order, the confirm with the
fingerprint, the 409 re-preview, cancel and the re-extraction box.

The real-host smoke (isolated PocketRisu v1.13.0, stub models, a synthetic chat of two names): the join's preview
listed the entities, three warnings (a relationship and a promise with oneself, a secret kept from its holder), a
replaced place and a merged identity; three turns were extracted while joined; the undo's preview mirrored the join
and offered "3 turns (3 calls)", off by default; ticked and confirmed, the three turns were re-extracted and none
listed the names as one afterwards.
