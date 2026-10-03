# S1 evidence excerpts for independent review

These five **zero-based** turns (81, 182, 200, 227, 237) come from the approved real
sequential run of commit `4e76c700406d6b42843f65935edb82fa6d2fdf15`, generation
`extract-696ace94a0f2a9485521a51ae001d995`, on 2026-10-03. The corresponding authored
story turns are 82, 183, 201, 228 and 238 (one-based).

The input is the 240-turn synthetic Korean story *윤슬포 해도 / Yunseulpo Chart*, written
by Claude for NMOS benchmarking on 2026-09-29. Its source README states that all people
and settings are invented, with no real people or existing IP. All ten selected source
messages were byte-matched to that authored source and the immutable source-revision
rows. The owner explicitly authorized committing and pushing these excerpts. The model
replies and stored assertion rows are actual measured evidence, not authored expected
outputs. These are development regressions, not a fresh holdout benchmark.

## Files

Each `turn-NNN/` contains:

- `source-original.txt`: original user/character source text, before normalization.
- `target.txt`: exact TARGET block contained in the captured main model request, after
  the existing normalizer. Source markup and model text can differ; both are preserved.
  None of these selected TARGET messages was truncated by the input limit.
- `known-entities.txt`: exact KNOWN ENTITIES block sent for this request, not a list
  reconstructed from the final database.
- `evidence.json`: original `also_called` items (including their verbatim JSON object
  slices), original `same_names`, all stored alias rows, the preceding served character
  alias rows, and separately labeled derived ambiguity before/after the turn. It also
  records the stored entity-hint snapshot, extraction/source identifiers and hashes.

Turn 227 has **no `also_called` item**. Its evidence additionally contains original
`roles_ended`, listed CURRENT ROLES, stored `role_toward` rows and the preserved
confirmation record. `confirmation-prompt.json` and `confirmation-reply.json` are
byte-for-byte copies of that call's captured system/user input and reply, including
its preceding two turns. This permits review of the uncertain sponsorship ending.

`subject`, `subject_type`, `object`, `object_type`, `value`, `source`, `asserted_by`,
`polarity`, `status` and `reason` remain as recorded. Absent original fields remain
absent; null is not converted into a name. In particular, turn 200's original/stored
`subject=추오월`, `object=람이`, `value=도도` must not be rewritten into a tidier edge.
The alias resolver uses subject/value; the independently recorded object is still
retained for attribution review.

## Reading order and limitations

Start with turn 182 and its preceding alias rows to inspect legitimate multiple-alias
resolution (②), then scope attribution failures in 81/200/237 (①). Review 227 as a
separate role-ending question. These files do not authorize changing ADR 0012, weakening
ambiguity protection, selecting a new default or making another model call.

The run completed 240 jobs + 7 confirmation calls; the declared role scenes pass 7/7,
but the final identity gate passes 1/3 and the run exits 1. Details and quote-quality
limits: [measurement report](../../../../docs/perf/extract-v16-alias-reminder.md#fresh-s1-with-worker-confirmation-roles-pass-identity-fails-2026-10-03-2244-kst).

Only this bounded synthetic evidence is published. Full DB archives, application
configuration, request authentication and unrelated real-chat scenarios are excluded.
Review copies never modify source revisions or assertions. No model call was made to
export or verify them.

## Verification

The export used a fresh read-only DB connection, checked current stored hints/raw/rows
against the previously preserved run, checked the captured TARGET and KNOWN ENTITIES,
and matched the original JSON slices to the parsed model items. Source artifact hashes
and the base source commit are in `manifest.json` and each turn's `evidence.json`.
`SHA256SUMS` pins all files in this directory except itself.

From this directory, verify the committed copy with Python 3 (standard library only):

```sh
python - <<'PYTHON'
from pathlib import Path
import hashlib
for line in Path('SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
print('All excerpt hashes match')
PYTHON
```
