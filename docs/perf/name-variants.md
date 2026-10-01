# A name as the story says it: given names and romanized names (Phase 24)

`docs/phases/PHASE-24.md`, ADR 0058, D68. Numbers only: the cases stay outside the repository (the owner's chats are
private; the synthetic set is not published yet).

## Setup

- **Replays only, no model call** (Q6): recorded requests compiled again with `audit.replay` (read-only), the probe in
  place of the request's message, packet policy `packet-v10` at 4,000 tokens, **vectors off** so only what the packet
  selects differs. `name_variants` off is the ranking before this phase, on is ADR 0058; `first_cue` and
  `history_marks` on in both, as on `main`. Every set ran **three times** with each setting (a replay's packet size
  moves by about 1 % between runs of the same code); the three runs gave the same counts.
- **Synthetic chat** (240 turns, Korean): its 15 first-cue cases (scored on the packet alone) and its 25 cases at the
  240 cut and after a first connection (scored with the window). Its characters are written in full and asked about
  by the given name.
- **M0 main**: the owner's M0 main chat, 40 cases; "needs memory" are the 10 whose answer the window does not hold.
- **Sample 2**: the owner's second M0 chat, window B (the last 11 messages), lexical, 17 cases; and five probes asking
  for one fact each, by the full name and by the given name.
- **Restored production copies** (`extract-v13`; the same re-extracted with `extract-v14`), the chat window cut to the
  last 20 messages: generated who- and first-cue probes (Phase 21).
- **Hangul probes for romanized characters**: on the restored copy whose two chats tell their story mostly in English,
  each character held only under a Latin name, with at least two facts outside the window and a Hangul spelling the
  chat itself writes, asked about twice in Hangul ("<name>는 어떤 사람이야?", "…지금 어디에 있어?"); a probe passes
  when the packet holds one of that character's values.

## Results (2026-10-01)

| Set | `name_variants` off | on |
|---|---:|---:|
| Synthetic, 15 first-cue cases | 5/15 | **8/15** |
| Synthetic, 25 cases at the 240 cut / after a first connection | 23/25, 24/25 | 23/25, 24/25 |
| M0 main, all cases / cases that need memory | 36/40, 7/10 | 36/40, 7/10 |
| Sample 2, window B (cases that need memory) | 9/17 (5/13) | 9/17 (5/13) |
| Sample 2, full-name / given-name probes | 3/5, 3/5 | 3/5, 3/5 |
| Restored copies, first-cue probes (`v13`, `v14`) | 5/5, 7/8 | 5/5, 7/8 |
| Restored copies, who-probes (`v13`, `v14`) | 7/7, 4/4 | 7/7, 4/4 |
| Hangul probes for romanized characters (two chats) | 8/24, 0/6 | **10/24, 2/6** |
| Forbidden phrases placed (M0 main, synthetic ×3, sample 2) | 1, 0, 0, 1, 0 | 1, 0, 0, 1, 0 |

- The three synthetic cases gained ask how a character first addressed the protagonist, by the character's given
  name. Sample 2's given-name probes were already found through its lorebook's keys (ADR 0046).
- **Packet size.** M0 main −0.4 %, sample 2 +1.2 %; the synthetic sets +8 % to +16 % (characters each message names by
  the given name now bring their facts). The budget and the fitter are unchanged.

Every acceptance criterion of `PHASE-24.md` is met: the synthetic first-cue cases +3 (at least +2), the Hangul probes
more than before on each chat, no other set worse, no new forbidden phrase; the deterministic cases in
`test_name_variants.py`; recorded requests without `name_variants` replay as they were.

## What the measurement changed on the way

- **Exclusions for given names** (spec): a first version split every three-syllable name. A place's name was split,
  and the persona's given name became a mention: the persona's facts filled the slots and two stale values were placed.
  Characters only, without the persona's given name, nothing got worse.
- **Everywhere names are matched** (spec review): counting the variants in fact selection only would have brought a
  character's facts while not seeing that character in the scene, so a fact kept from them was not marked private.
- **The character asked about keeps its `<Cast>` group** (step 2): replaying the implementation gave 7/15, not the
  draft's 8/15. A given name in the previous reply brought two more characters into the scene, and the character the
  message named in full lost its group to them. With the option on, `<Cast>` lists the characters the message names
  first.
- **Names only in knowledge marks, an open thread's included; one owner across both rules** (step 2 and its review).

## Limits seen

- The spelling key folds `eo` and `u` together, so 서연 and 서윤 meet (Seo-yeon, Seo-yun). When a given name and a
  spelling meet like that, neither counts (one owner per variant): in the latency bench's 40 names one given name
  counted for no one for this reason.
- A given name that is also a common word or contraction counts when the message has the word (ADR 0058,
  Consequences).
- K32 (a persona narrated in the third person) is unchanged; two rules were measured with the spec and left out
  (`docs/KNOWN-ISSUES.md`).

## Latency (`tools/bench_story.py`, 10,000 messages)

Retrieve p50 and p95, the median of five rounds, each round running `main` before step 2 and after it, without and
with `BENCH_NAMES=1` (20 three-syllable Hangul names and 20 romanized ones; every question starts with a given name or
the Hangul spelling of a romanized name), in turn; budget 4,000, pinned to two cores.

| | before, p50 / p95 | after, p50 / p95 | p50 difference |
|---|---:|---:|---:|
| Questions of the bench | 138.2 / 230.0 ms | 137.6 / 224.8 ms | −0.6 ms |
| Every question names a character (`BENCH_NAMES=1`) | 142.7 / 433.5 ms | 145.2 / 431.7 ms | +2.5 ms |

The rounds spread by ±5–10 ms; neither difference is measurable. With `BENCH_NAMES=1` the packets after the change
average 627 tokens, 575 before: the named characters' facts now come in.
