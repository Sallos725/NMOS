# 0070 — A name in the message is not a question about everything (`packet-v16`)

Status: proposed, 2026-10-08 (`docs/phases/PHASE-36.md` Q1–Q3, approved by the owner as proposed; AGE-10). Adds the
policy `packet-v16` on top of `packet-v15`; the default is the owner's decision on the measurement. No prompt,
generation key, stored row or migration changes.

## Context

ADR 0068 rests a supportive line no reply used and never rests a required one. A fact is required when the question
names it (PHASE-34 Q1), and `facts.relevant_facts` took that as "the message holds a name of its subject or object": a
message mentioning a character made every fact about it required. In role-play nearly every message names a scene
character, so the rest had little to act on: on the owner's trial chat 27 % of the required tokens were a named
character's past events, traits, membership and identity that the message's words did not touch (PHASE-36, "Why now").

## Decision

Under `packet-v16` (`packet.NAMED_POLICIES`), a fact whose names the message holds is named (required, never resting)
when it is how its character stands now (`facts.NOW`: located_in, has_status, feels_toward, possesses) or with another
(`facts.STANDING`: relationship, role_toward, feels_toward, addresses), when it carries a knowledge mark (`known_by`,
`hidden_from`), or when the message's words point at it (overlap with the fact's words at least `LEXICAL_BAR`). Any other
fact the name alone brings is supportive: offered exactly as before (ranking, limits and the Cast unchanged), it rests
when no reply used it. Claims follow the same rule.

## Consequences

- On the trial chat's 37 recorded requests replayed in order (no vectors): required lines 76 % → 67 % of the placed
  lines, supportive repeats 0.561 → 0.510, their stale tokens 0.126 → 0.067, the whole packet's repeats not higher
  (`docs/perf/phase36-replay.md`).
- A trait or past event the next reply needs, named only by the character's name, may be out for two requests after
  two placements no reply used. A question about it in its own words, a history cue, or a reply that uses it keeps it.
- Rejected: leaving out a fact the canon in the prompt states (1.6 % of the required tokens on the trial chat; a
  translation to compare); demoting every named fact (relationship and address lines set the speech of every reply).
