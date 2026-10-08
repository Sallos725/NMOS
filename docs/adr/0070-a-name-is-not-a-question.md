# 0070 — A name in the message is not a question about everything (`packet-v16`)

Status: accepted, the default since 2026-10-08 (the owner, on the replay, PHASE-36 Q3); proposed the same day
(`docs/phases/PHASE-36.md` Q1–Q3, approved by the owner as proposed, Q1 amended twice on the replay; AGE-10). Adds the
policy `packet-v16` on top of `packet-v15` and replaces it as the default. No prompt,
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
`hidden_from`), when the message's words point at it (overlap with the fact's words at least `LEXICAL_BAR`), or when the
question asks for its kind (`facts.ASKS`, a fixed list of cues: "무슨 일을 해", 직업 or 정체 for an identity, 소속 for a
membership, 성격 or 생김새 for a trait, "무슨 일이 있었어" for an event, 알고 있어 for what someone knows), or when it
holds one of the question's one-syllable nouns (`facts.asked_nouns`: 달, 빵; PHASE-35's nouns). The cues were
added on the bench replay, where a real-chat question asking what a character does for work ("…는 무슨 일을 해?") lost
its answer: the identity fact shares no word with the question, so it rested; the nouns, where a question about the
red moon lost the place's fact that holds 달 (`docs/perf/phase36-replay.md`). Any other
fact the name alone brings is supportive: offered exactly as before (ranking, limits and the Cast unchanged), it rests
when no reply used it. Claims follow the same rule.

## Consequences

- On the trial chat's 37 recorded requests replayed in order (no vectors): required lines 76 % → 67 % of the placed
  lines, supportive repeats 0.561 → 0.519, their stale tokens 0.126 → 0.067, the whole packet's repeats not higher; on
  S1's 241, required lines 63 % → 57 %. The bench answers as `packet-v15` does: 289 of 314 by the majority of three, no
  case lost (`docs/perf/phase36-replay.md`).
- A trait or past event the next reply needs, named only by the character's name, may be out for two requests after
  two placements no reply used. A question about it in its own words, a history cue, or a reply that uses it keeps it.
- Rejected: leaving out a fact the canon in the prompt states (1.6 % of the required tokens on the trial chat; a
  translation to compare); demoting every named fact (relationship and address lines set the speech of every reply).
