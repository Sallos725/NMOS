# Proposal — Stage 4: who knows what

> Status: decided 2026-09-27: the owner chose the recommended answer to every question; spec `docs/phases/PHASE-10.md`.
> Evidence: `docs/perf/stage4-leak-pilot.md`. Roadmap: `docs/ROADMAP-1.0.md`, Stage 4. A phase document with
> acceptance criteria follows once the questions are answered.

## Problem

The owner's chats have both shapes: one character, and several characters voiced in one reply. The failure that
matters most to the owner is a **leak**: a character revealing in words or action what they should not know or
say. Omniscient narration showing thoughts is not a leak.

One generation writes every character, so NMOS cannot hide a secret from one character while giving it to
another (the fixed limit, original §30, K11). The pilot shows the limit matters less than the data:

- the packet already works when it says **who must not know** (A′: the holder remembers, the secret stays
  unsaid, 3 of 3 with Opus);
- the knowledge marks usually do not say it: `limited` mostly records who was present, `hidden_from` is often
  missing on real secrets and set on trivia, and a secret stays "hidden" after the character found out;
- withholding content (B′) prevents leaks only by making the holder forget (0 of 4);
- with a large host context, the secret is in the transcript anyway.

## Proposal

1. **Knowledge data first** (next extractor generation).
   - The extraction separates *present* (saw or heard it) from *kept from* (someone deliberately does not know:
     a secret, a lie, a surprise). `hidden_from` is set only for the second, with the character it is kept from.
   - A secret **ends** when the story shows the hidden character learning it: a later fact that the character
     knows it, or a reveal in the scene. The earlier fact's `hidden_from` stops applying from that turn; its
     history stays (invariant 5). Deterministic where the later fact names the same content; otherwise the
     extraction is shown the chat's open secrets, as it is shown open promises (ADR 0019).
   - Private feelings and plans that nobody else is shown knowing stay `limited` to their holder without
     `hidden_from`.
2. **Packet: A by default.** Facts every present character knows stay as they are. The rest go under
   `<Private>` with their holders and, when set, whom they are kept from. The note tells the model: holders may
   act on them; nobody says them in front of the characters they are kept from unless the story reveals them.
   The holder never loses the content.
3. **Strict mode (B′), per chat, off by default.** For a chat where any leak is worse than a forgetful
   character: lines not known to everyone present are replaced by "something X know and Y does not". Needs who
   is present: the characters acting in the last turns (participants, Phase 8), plus the persona.
4. **First person, per chat.** When the chat is narrated in a character's first person (a preset POV toggle),
   the packet keeps only what the narrator knows. Set in the panel; a default read from the preset is a later
   option, since the toggle's name and values differ per preset.
5. **Measure it.** A case set built from real chats, replayed offline like this pilot: leak, near-miss, and
   whether the holder remembers, per response model. Stage 4 is done when the Stage 4 criteria in the roadmap
   hold on it.

Tentative owner decision (2026-09-27, not final): a character blurting their own secret, or a child's slip, is
direction, not a failure.

## Not in scope

Separate model calls per character (needs host orchestration, Stage 8 or later); hiding what the host itself
sends (card, lorebook, recent transcript); belief states beyond knows / kept-from (believes, suspects,
misremembers) until a case needs them.

## Questions for the owner (recommended answer first)

- **Q1 — secret end.** (a) End `hidden_from` when a later fact shows the character knows it (recommended);
  (b) also let the owner end it by hand in the Inspector (Stage 6 repair).
- **Q2 — strict mode.** (a) Per chat, off by default (recommended); (b) global switch; (c) leave it out.
- **Q3 — first person.** (a) A per-chat panel setting (recommended); (b) read the preset's POV toggle
  automatically where the known presets expose it.
- **Q4 — blurts.** (a) Count a holder's own slip as direction, not a leak, and report it separately
  (recommended, matches the tentative decision); (b) count it as a leak.
- **Q5 — measurement models.** (a) The owner's two response models, Opus 5.5 and Gemini 3.1 Pro, with a spend cap
  agreed per run (recommended); (b) one model only.
