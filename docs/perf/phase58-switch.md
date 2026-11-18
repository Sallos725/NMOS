# Phase 58 step 3 — the switch to `extract-v18` on a copy of production

2026-11-18, on branch `Sallos725/track-affinity-scores-host` (`042e55f`). No model call. Production's database was only
read (`pg_dump`); the check ran on a throwaway copy on the test PostgreSQL (:5436, `nmos_p58_check`), with
production's sidecar settings (its `app_config` rows and its environment, secrets left out) and no worker.

## What production holds

- Schema `0034`; the active extractor `extract-a81b34d7…` (`extract-v16`, `gemma4:31b-cloud`); no queued job.
- 46,019 assertions, 1,864 of them `feels_toward`.
- The branch computes the same `extract-v16` key from those settings (every spec field equal), so the switch is
  compared against the generation production really records. `extract-v18`'s spec differs from it in `compiler` and
  `prompt` only.

## The switch

| Step | Queued jobs | Active extractor | Rows (assertion, extraction, source revision, summary, owner repair: count and id hash) |
|---|---|---|---|
| As restored | 0 | `extract-v16` | — |
| Migration `0035` applied | 0 | `extract-v16` | identical |
| Sidecar started with `extract-v18` | 0 | `extract-v18` (`extract-e446c4c6…`) | identical |
| Sidecar started with `extract-v16` again | 0 | `extract-v16` (`extract-a81b34d7…`) | identical |

Acceptance criteria 2 and 5 (the switch and the switch back queue nothing and change no row) hold on production's
data. Without S3 the switch would have been a version change (PHASE-57 Q5): the latest 100 turns of each chat, about
850 extraction calls on production's 43 chats.

## The prompt

`extract-v18`'s system prompt is 17,533 characters against `extract-v16`'s 16,423 (+6.8 %, under the 15 % stop
condition); each extraction pays it.
