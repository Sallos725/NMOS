# Phase 62 step 4 — the cap changed on a copy of production

2026-11-24, on branch `docs/phase62-long-replies`. No model call. Production's database was only read (`pg_dump`);
the checks ran on a throwaway copy on the test PostgreSQL (:5436, `nmos_p62_check`, its stored API keys blanked), with
production's sidecar settings (its `app_config` rows and its container's `NMOS_*` environment, secrets left out) and
no worker. The sidecar was started in-process against the copy; counts, key prefixes and sizes only were read.

## What production holds

- Schema `0039`; the active extractor is `extract-v19`; 61 chats with a head, 57,676 assertions, 6,703 extractions,
  270 summaries; no queued job.
- The sidecar's and the worker's `NMOS_*` environments are the same 27 variables with the same values.
- **The harness first**: at 6,000 the branch computes, from those settings, the five generation keys the copy records
  as active (extract, reveal, summarize, canon, embed), so the changes below are compared against the generations
  production really runs.

## The change, and the change back

| Step | Classified | Queued jobs | Active generations | Rows (assertion, extraction, summary, source revision, owner repair, vectors: count and id hash; discarded extractions) |
|---|---|---|---|---|
| As restored | — | 0 | production's | — |
| Started at 6,000 | all `same` | 0 | unchanged | identical |
| Started at 24,000 | extract, reveal, summarize `reads`; canon, embed `same` | 0 | extract, reveal, summarize new; canon, embed unchanged | identical |
| Started at 6,000 again | extract, reveal, summarize `reads` | 0 | production's again | identical |

At each step the worker's handlers, built from the same settings, carry the active keys. Acceptance criterion 4 holds
on production's data.

**What memory serves does not change with the switch** (criterion 6): for each of the 61 chats, the memory view read by
the 24,000 generation (which has extracted nothing yet) is identical, section by section, to the one read by the 6,000
generation, and so are the summaries served.

## Going back to an image without this phase

Worked out with `origin/main`'s code against the copy, in a transaction that was rolled back:

| The copy's active generations | An image without this phase classifies | It would queue |
|---|---|---|
| made at 24,000 | extract `version`, summarize `version` | 643 extractions, 56 summaries |
| set back to 6,000 by this branch first | `same`, `same` | nothing |

So the order in the spec's stop conditions is needed, and enough: the cap back to 6,000 on an image that has this
phase, then the older image.

## What "read the cut turns again" would read

With the copy at 24,000:

| | Count | Estimated input tokens |
|---|---|---|
| Turns an earlier cap cut (32 of the 61 chats) | 424 of 658 served turns | 7.9 to 10.1 million (18,600 to 23,900 a turn) |
| Scene summaries cut the same way | 51 windows | 3.5 to 6.5 million |

A direct count of served turns whose extraction was shown less than the turn holds gives the same 424.

## Prompt sizes (criterion 7)

The prompt each of those 424 turns would get, built as the worker builds it, without sending it:

- 32,630 characters on average at 6,000 and 41,389 at 24,000 (the longest 56,927): **8,759 characters added per cut
  turn**. The estimate assumed about 8,900 (9,211 unread, 1.3 % still past 24,000).
- In tokens: the estimate's 0.69 to 1.26 tokens per added character gives 18,500 to 23,500 input tokens for the mean
  cut turn (these turns recorded 12,474 at 6,000), a little under the spec's 18,900 to 24,100. Scaling each turn's recorded input by its prompt's
  growth (0.38 tokens per prompt character, most of the prompt being its fixed English part) gives 15,800, which is
  lower still: Korean text costs more per character than the prompt's average, so this is a floor, not a correction.
  The estimate stands; if it errs, it errs high.
- The largest role or alias confirmation prompt at 24,000 is 73,944 characters (two earlier turns and the target, each
  at the cap).
- The largest scene-summary window at 24,000 is 188,154 characters (the mean window 58,972), about 130,000 input
  tokens in one call at 0.69 per character: the stop condition on the extraction model's context applies to it.

## Vectors (Q5)

The vector step timed with stand-in chunks for a cap of 35 (each a copy of one of the message's own vectors; no
embedding call), 20 searches for each of the five chats with the most chunks:

| | Chunks in the projection | The largest chat | Vector step, median |
|---|---|---|---|
| Today (8 chunks) | 6,351 | 871 chunks | 7 to 13 ms |
| 35 chunks | 12,483 | 1,718 chunks | 13 to 22 ms |

About 9 ms more on the largest chat. Whether the added chunks change what recall finds is not measured here.

## Not checked here

No extraction was made at 24,000: what the model writes from a whole reply, and whether long turns fail or time out,
is step 5's (the owner's use on the test install, then production).
