# ADR 0090: A long reply read to its end — the cap on each message as a setting

Date: 2026-11-24. Status: accepted (PHASE-62, owner 2026-11-24: Q0 (a), Q1 (a), Q2 (a), Q3 (a), Q4 (b), Q5 (a)).
Amends ADR 0014 and ADR 0078 (what a generation change queues) with one more class, and K13's accepted limit. No
migration.

## Context

Extraction showed the model the first 6,000 normalized characters of each message of a turn, scene summaries the
first 6,000 of each message of their window, and the reveal check the same as extraction (#13, K13). K13 recorded it
as accepted because the first chat measured stayed within it. Measured again on the owner's production (2026-11-24,
`docs/phases/PHASE-62.md`): 432 of 685 character replies are longer (mean 15,105 normalized characters), and 51.2 % of
the target characters of 643 extracted turns were not shown to the model. What lies past the cut is story.

The cap is a constant in the code and already a field of three generations' specs (`target_chars` in an extractor's
and a reveal check's, `message_chars` in a summarizer's), so any other value is another generation, which until now
meant a version change: the latest turns of every chat extracted and summarized again at the owner's cost.

## Decision

1. **The cap is a setting, `NMOS_EXTRACT_TARGET_CHARS`, default 6,000** (`Settings.extract_target_chars`; 6,000 to
   36,000, checked at startup; environment only, as the compiler is). It is the value of `target_chars` and
   `message_chars` in the three specs. At the default every key, prompt and stored row is what it was.
2. **A job reads at its generation's cap, not at the settings'.** `extraction.with_cap` puts the generation's
   `target_chars` on the loaded context, and everything that reads a TARGET turn reads `target_cap(ctx)`: the prompt,
   the listed quotes, the role and alias confirmations (which show two earlier turns at the same cap), the evidence
   check's text (`shown_target`) and the coverage. A scene summary reads each message at its generation's
   `message_chars`. So what the evidence check accepts is what the model was shown, whatever the settings are when
   the job runs. CONTEXT keeps 1,000 characters per message; canon keeps its own parts.
3. **A row says the cap it was read at only when that is not 6,000** (`coverage.target_cap` on an extraction or a
   reveal check, `coverage.cap` on a scene summary). A row without it was read at 6,000, as every earlier row was;
   rows at the default do not change shape.
4. **A change of the cap alone queues nothing.** `generations.classify` names an activation whose specs differ only
   in `target_chars` or `message_chars` — alone, or together with a compiler change among `ADDS` — `reads`. Activation
   queues for it what a carry-on queues (ADR 0078): turns no generation serves, windows no summarizer wrote. What was
   read at the earlier cap keeps serving (ADR 0014); what comes due afterwards is read at the new cap. With the model
   or how it is called changed too, it is a model change and the owner's choice applies. Any other difference is a
   version change, as before.
5. **"Read the cut turns again", per chat, on request.** `GET /v1/conversations/{id}/cut-turns` counts, and `POST
   /v1/conversations/{id}/read-cut` queues for the active generation, the turns of the head whose serving extraction
   (chosen as a read chooses it) was shown less than the turn holds at a cap under the active one: one whole
   extraction call each, at background priority, oldest first. With `{"summaries": true}` the scene summaries cut the
   same way are written again too. Nothing is discarded: the earlier extraction serves until the new one is stored
   and stays afterwards. The count comes with a range of input tokens (the recorded input of the earlier reading plus
   0.7 to 1.3 tokens per added character), an estimate. The panel's button shows only where the sidecar counts such
   turns, and asks for a second click after saying what it would read.
6. **Vectors are not part of it.** Their cap was already a setting (`NMOS_EMBED_MAX_CHUNKS`, ADR 0062).

## Consequences

- A long turn costs more input from the change on: on the owner's record about 33 % to 61 % more input per turn at
  24,000, and a scene summary's input about doubles. A failed call is retried at its full input.
- A re-read turn is read by a newer generation: its facts are worded anew, and the dropped-fact comparison of ADR
  0044 amendment 3 does not run across generations (as after any generation change). The earlier extraction's reveal
  check stops counting with it; the new extraction lists the open secrets itself.
- "Extract all history" after a change of the cap reads every older turn again at the new cap, not only the cut ones.
- **Going back to an image without this decision:** such an image classifies a database whose active generations
  were made at another cap as a version change and extracts the latest turns again. Set the cap back to 6,000 on an
  image that has this decision first (that queues nothing, and the 6,000 generations serve again), then change the
  image. The same holds for an archive made at another cap and restored into such an image.
- The sidecar and the worker each build their generations from their own environment: the setting must reach both
  (the compose files pass it to both), or the worker's handlers do not match the active generation and its jobs wait.
- Not decided here: the default (6,000 until the owner decides, with the other defaults, at or after `1.0.0`), and
  the cut of CONTEXT messages, which shows a long earlier reply from its beginning.
