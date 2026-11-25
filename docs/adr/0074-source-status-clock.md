# 0074 — The status-window clock on a recalled source

Status: accepted for the owner's bounded pre-release correction, 2026-10-10,
PHASE-42 (AGE-78). Verification and adoption status are in docs/STATUS.md.

A source revision can retain its status-window date/time while its selected
excerpt omits it. Current state is a different clock; the last six state changes
are not necessarily the date of an old scene. Do not infer an event timestamp.

For explicit temporal questions under packet-v18, read date/time observations on
eligible excerpt/quote revisions, with the request's exact rules version, active
membership, acceptance, cut and position bounds. One batched lookup has at most
25 ms, respects any shorter caller timeout, and discards late results. Values
are literal and capped at 160 characters. Supported keys are date/날짜 and
time/시간/시각, case-insensitive; unrelated keys are ignored. Multiple stored
aliases for one category abstain. The original parser's last-match-wins rule for
an identical key remains unchanged; incorrectly configured parsers are not fixed
by this read-side supplement.

After the existing packet has been compiled, append clocks for at most two of
its already placed source revisions, in retrieval priority order, only if the
remaining token budget holds them. Preserve original packet lines and selection.
A note explicitly distinguishes a source's status clock from an event's occurrence
time. No clock for an unplaced, hidden, missing or different revision. Strict and
first-person narrator modes abstain; known secret overlap in the added values
also abstains. No current clock or neighboring turn is substituted.

Record source_clock in recall options. Fresh requests enable it, while missing
historical values replay false. v16/v17 ignore it. The audit ledger records source
revision, turn, parser rules/version and exact added token cost. There is no
schema, normalizer, extraction generation, provider or plugin change.

This does not implement calendar arithmetic, date normalization, source recovery
when retrieval missed, facts-only clock enrichment, or a guarantee of final
answer correctness. Unknown dates remain unknown.

## Amendment (2026-11-25, PHASE-65 S4, audit G2)

A clock key is matched by its last part (`Status.Date` is a date key), in SQL (`source_time.BASE_SQL`) and in Python
(`base()`). `now`, `datetime`, `day`, `weekday` and `season` keys are categories of their own, so date and time read as
before. More temporal cues start the read (일차, 무슨 요일, 어느 날, 무슨 계절, 얼마나 지났, 며칠째). The extractor's
`story_clock` (ADR 0086 item 3) strips the prefix too and never joins fields from two turns.
