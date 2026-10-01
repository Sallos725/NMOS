# 0038 — One relationship history per pair, the persona's full name, and what a standing fact replaced

Status: accepted, 2026-09-28. Phase 11 step 3 (`docs/phases/PHASE-11.md`, Q5 and the M0 finding on the persona's
full name). Read side only: `resolve-v5`, a new default packet policy `packet-v5`; no migration, no new extractor
generation. Amends ADR 0012 (entity identity), ADR 0023 (persona name) and ADR 0028 (per-direction standing facts).
Closes K24's direction case.

## Context

- **K24.** `relationship` and `feels_toward` are versioned per direction (subject → object) and per predicate. When
  the story changes a relationship but extraction records the new one in the other direction ("카이토 → 유이: 연인"
  after "유이 → 카이토: 같은 반 친구"), both stay current. Phase 8 measured it in 2 of 9 runs.
- **M0 (`docs/perf/m0-baseline.md`).** In the owner's longest chat the story writes the persona both as the persona
  name and as a full name ending with it. ADR 0023 joins only the exact name, so the persona was two characters: each
  pair had two current speech levels, and promises made to "both" tied and never closed (K23). The owner chose a hand
  join in production (ADR 0025) and a resolver rule.
- Fixing both leaves "how did they stand before" without an answer: the packet shows current versions only, and a
  past question that the stale version had answered by accident (M0 "past") lost it.

## Decision

1. **One relationship history per pair.** The version key of `relationship` is the unordered pair of entities
   (ADR 0012 keys). Each direction keeps its latest statement, as before. A symmetric relationship, stated either
   way, also replaces the other direction's, and a newer statement of the other direction replaces it. A denial ends
   the relationship it denies in its direction, or either way when that relationship is symmetric, and is current
   itself (rendered negated, ADR 0013); a denial of anything else stands beside. A directed pair ("엄마" and "자녀")
   keeps both directions.
2. **Symmetric** is decided on the value's head noun: in Korean the last word (a parenthetical aside and a trailing
   관계 or 사이 dropped), ending with one of 친구, 연인, 애인, 커플, 부부, 배우자, 형제, 자매, 남매, 쌍둥이, 동급생, 동기,
   동창, 동료, 라이벌, 경쟁자, 원수, 적, 파트너, 동반자, 룸메이트, 이웃, 약혼자, 사촌, 동맹, 팀원, 짝꿍, 단짝, 소꿉친구, 동지,
   and not a possessive ("친구의 동생"); in English any word of the value among the same set in English, unless "of"
   makes it someone else's ("friend of her brother"). The table lives in `facts.py`, outside the registry: it changes
   how stored assertions are read, never what is extracted (the generation fingerprints the registry, D20).
3. **`feels_toward` and `addresses` stay per direction.** A feeling is one side's; a speech level is too (ADR 0028).
   A relationship change never ends a feeling: "lovers" and "angry at him" can both hold (PHASE-11 Q5).
4. **`resolve-v5`: the persona's full name.** A character name of two or more words whose last word is a persona
   name (ADR 0023) is the persona: "아오키 타쿠미" for the persona "타쿠미". Characters only; the name must end with
   the persona's name as its own word ("타쿠미마" and "타쿠미 선배" stay other names). Another character who shares the
   persona's given name and is written with a family name would be joined too; nothing splits entities yet (K8), so
   the rule is narrow and the owner's hand join (ADR 0025) remains the general tool.
5. **`packet-v5` (default): what a standing fact replaced.** `packet-v4` plus, on a relationship, feeling or speech
   level line, the latest earlier statement of the same predicate with another value (for a relationship, either
   direction), with its turn: `카이토 relationship 유이: 연인; before, turn 1: 유이 relationship 카이토: 같은 반 친구`.
   When the earliest earlier value differs from that one, the line names it too ("; first, turn N: …"): "what did
   he call her at first" needs it. A denial is not named as what it was. `packet-v4` and earlier render their lines
   as before.

## Consequences

- K24's direction case is closed. Its predicate case (a reconciliation recorded as `relationship` while the anger
  was `feels_toward`) is not merged by design: both lines show their turns, and the newer relationship names the
  older one.
- M0 on the restored backup (read side only, the current extractor generation): 5 → 7 of the first 12 cases, 13 → 15 of
  the 28 the owner confirmed later; both speech-level cases
  pass and no forbidden phrase is placed as current (`docs/perf/m0-baseline.md`, step 3). The M0 scorer and the
  memory evaluation count a phrase named after "; before, turn N:" as past, not as current or stale.
- A line with a replaced version costs more tokens; M0's mean packet stayed at 775 of 800.
- Entity ids carry the resolver version (ADR 0012): Inspector links to entity pages from before `resolve-v5` point at
  ids that no longer exist. Replays of requests recorded before this read with the current rules: a recorded
  `packet-v4` request is reproduced only where the pair fold and the persona rule change nothing it placed.

## Amendment 1 (2026-10-01, K42): earlier versions only under marks that cover them

Found in review of Phase 21 (ADR 0056), fixed at the owner's request the same day. Item 5 prints a standing fact's
earlier versions in the current version's line, under that line's knowledge marks, which the memory mode (ADR 0035)
also reads; the fact's history kept no marks. A version kept from someone thus read as known to everyone the current one
is known to. Seen in the owner's M0 main chat: a feeling three earlier versions of which only one character knew,
printed under its public current line in every packet.

1. **History entries carry their marks** (knowledge, `known_by`, `hidden_from`), also in `GET …/facts?history=true`.
2. **A `limited` earlier version is printed only under the same marks** (`facts._shown_under`): "before" and "first"
   are the latest and the earliest of the versions the line may print. A public or unmarked version under a limited
   line is printed: treated more narrowly than it was, it leaks nothing. The Inspector (the owner's view) shows every
   version, as before.
3. **Phase 21's first cue** (ADR 0056 item 3) brings a fact back from the window when a version it would print starts
   before the window (instead of requiring every such version to have the current marks).
4. **Replays.** A recorded recall option `history_marks`, on for new requests; a trace that did not record it replays
   with it off, so a request from before this amendment replays as it was. The packet policy stays `packet-v10`.

Measured on replays (vectors off): no case of any set changes (M0 main 7/10, the synthetic sets 23, 24 and 5/15, the
restored copies' probes 5/5, 7/8 and 7/7, 4/4); every M0 main packet names one version fewer (the feeling above); the
synthetic sets' packets change in 2–5 of 15–25 (other versions named, none fewer).
