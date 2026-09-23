# 0014 — New extractor generations: recent window, older turns read from the previous one

Status: accepted, 2026-09-23, with `docs/phases/PHASE-5.md` (owner approval, PR #34).
Owner decisions behind it: Track B §4 "Owner decisions" item 5 (recent window automatic, older
history on request) and the Phase 5 design question of 2026-09-23 (apply it to every extractor
generation change, not only Phase 5's).

## Context

D20 / ADR 0006: when the extractor generation changes (a new model, endpoint, prompt, registry or
compiler version), readers use only the new generation, and activation queues the recent window, then
every older turn an earlier generation covered, at background priority. Until the worker catches up,
older turns have no facts (the Inspector shows partial coverage). Every such change re-pays the whole
covered history: about 15M tokens for a 10,000-message chat with the model in
`docs/perf/turn-extraction.md` (Track B §7). Known issue K18.

Phase 5 changes the extraction prompt (`extract-v5`, ADR 0012, ADR 0013), so upgrading would trigger
exactly this for every user with an LLM configured.

## Decision

1. **Activation queues only the recent window.** For every extractor generation change, the new
   generation is scheduled for the latest `NMOS_EXTRACT_BACKFILL` turns of each chat (default 100), as
   first sight already does (D22). Older turns are queued only on request: the Inspector's "extract
   all history" (`POST /v1/conversations/{id}/extract-history`), unchanged.
2. **Older turns are read from the newest generation that has them.** Per turn, the fact read uses
   the active generation's extraction when one exists, otherwise the extraction of the most recently
   active earlier generation that still matches the head (same anchor revision and `turn_hash` or
   window hash, not discarded). Exactly one generation serves a turn; within a turn, generations are
   never mixed.
3. **Coverage shows both.** Per chat: turns compiled by the active generation, turns served by an
   older generation (named), and turns with no extraction. "Extract all history" moves the second
   group to the first. The Inspector marks facts from an older generation.
4. **Rebuild discards all generations for that chat.** "Rebuild memory" (D22) marks every
   extraction of the chat discarded, not only the active generation's, so no older generation's facts
   reappear while the chat is re-extracted.
5. **Embeddings are unchanged.** Embedding generations keep D20's policy (re-embed everything covered).
   Re-embedding is cheap next to extraction, and mixed vector spaces cannot be compared (#17).

## Consequences

- D20 is amended: "readers use only the active generation … never mixed in" becomes "per turn, the
  active generation if it has the turn, otherwise the newest earlier one; never two in one turn".
- Upgrading to Phase 5, or changing the LLM model later, costs at most one call per recent-window
  turn per chat (≈100) instead of one per covered turn. Improving old turns with a better model is an
  explicit per-chat action with a visible cost.
- Facts in one packet can come from different generations (older turns from `extract-v4`, recent ones
  from `extract-v5`). Legacy facts carry no polarity, modality or source (ADR 0013, item 6) and their
  names are not hint-guided (ADR 0012). The Inspector shows which generation served each fact.
- A generation that is switched away from stays readable as a fallback. This relies on the O5 decision
  (Track B §4 item 4): superseded LLM extractions are kept. Pruning them later would turn fallback
  turns into uncovered turns, visibly, not silently.
- A chat whose head changes deep in history gets new turns extracted by the active generation only
  (unchanged), so fallback coverage shrinks naturally as a chat is edited and continued.
