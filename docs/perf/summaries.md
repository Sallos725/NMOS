# Scene summaries — real-model tier (Phase 12 step 4, ADR 0042)

Measured 2026-09-28. `summarize-v2`: the scene prompt lists the window's OPEN SECRETS and says never to write their
content; whether a stored summary may be used is checked when it is read (`summaries.leaks`).

## Method

`tools/eval_summaries_model.py`: 8 Korean scenes written for this evaluation (6 scenes of 3–4 turns, 2 "story so far"
inputs of 3 scene summaries). Each scene ran 3 times on each model, through the local Ollama, with 2 workers and no
errors. Raw prompts, replies and checks are in `fixtures/model/summaries/`. The scenes' third character was renamed
after these runs (2026-09-28, the name also belongs to a character of a real chat); the raw runs keep the name they
ran with until the next run of this evaluation replaces them. Each reply is checked for:

- **gold:** one word of each group names what the scene shows;
- **invented:** none of the words naming what it does not show;
- **secret:** the listed secret's content, found by `summaries.leaks` (what the packet will enforce) or by listed
  words, including the object the secret is about ("편지" for a forged letter);
- **cap:** the reply fits the stored cap uncut (1,200 characters for a scene, 2,400 for the story).

At temperature 0 the three runs of a scene were mostly the same text: a 3 of 3 says the reply is stable, not that
three different ones passed.

## Result (final prompt, fingerprint `1d83f7e77e627f7b`)

| Category | Scene | `gemma4:31b-cloud` | `deepseek-v4.1-flash` |
|---|---|---:|---:|
| scene | market and the lighthouse | 3/3 | 3/3 |
| secret | a forged letter kept from Kaito | **0/3** | 3/3 |
| secret | the secret is the scene (a kiss kept from a child) | **1/3** | 3/3 |
| secret | a secret listed but not touched | 3/3 | 3/3 |
| ooc | an out-of-character note | 3/3 | 3/3 |
| quiet | a quiet afternoon (nothing invented) | 3/3 | 3/3 |
| story | the story so far | 3/3 | 3/3 |
| story | the story keeps the order | 3/3 | 3/3 |
| **all** | | **18/24** | **24/24** |

**The misses, shown to the owner:**
- **The forged letter, `gemma4` 0/3.** It never wrote the secret's content (the forgery), but it wrote the act it is
  about, 3 of 3 ("…하나는 서랍 속 편지를 확인하고 다시 넣어두었다"). The check counts the object as a leak.
  - Against calling this a leak: the act happened while Kaito was away, and NMOS does not treat something done while
    a character is away as kept from them (ADR 0033, "away is not kept from"). The listed secret was only the forgery.
  - `deepseek` left the moment out, or said that Hana was keeping something from Kaito.
- **The kiss that is the whole scene, `gemma4` 1/3.** Two runs wrote it ("…부엌에서 입을 맞췄다") and one left it out
  ("…부엌에서 만났다"). The read-time check scored the two at 0.76 and holds them, so neither could reach a packet; the
  one that left it out scored 0.59 and stays usable. `deepseek` wrote that the two did something they kept from the
  sleeping character, 3 of 3.

This record replaces an earlier one of the same prompt, in which `gemma4` passed the kiss scene 3 of 3 (21/24). That
scene then used the names of characters from a real chat. They were replaced by synthetic ones before this record, and
the old fixtures were withdrawn.

## What changed before this record

A first prompt (fingerprint `bee481978138f6a8`) had `gemma4` at 18/24. Its fixtures were withdrawn with the others.
Three of its six misses were the check's own:
- the kiss summaries left the kiss out but kept the scene's names and setting, and trigram containment scored them
  0.68, above the 0.6 then set;
- a reworded leak scores about 0.3 and a copied one 0.76, so the check can only catch copies.

Two changes followed:
- `leaks` now leaves the names of the holders and of those kept from out of both texts, and holds a summary back at 0.7.
  On the recorded replies, "left out" scores 0.59 and "copied" 0.76.
- The prompt now also says to leave out "the object or act it is about". `gemma4` still names the letter.

## Limits

- **The prompt is the guard; the read-time check is a backstop for copies.** A summary that rewords a secret passes the
  check. Step 5 has to decide how much a summary may be trusted with a secret's character in the scene.
- **Real chats come in step 5.** The owner's chats are longer and their secrets are extracted as the story goes. Step 5
  measures summaries of the restored copy with M0, including its secret cases.

## The owner's longest chat (step 5, M0)

The restored copy (PHASE-11 Q1), read-only, lexical recall only (`--no-vectors`), the request at turn 73. Numbers only;
what the chat says stays outside the repository. Two extractions of the same chat: `gemma4:31b-cloud` (`extract-v13`)
and `deepseek-v4.1-flash` (`extract-v13`, 73 turns re-extracted through the local Ollama for this comparison). Each
has its own summaries (`summarize-v3`, 8 scenes and the story, written by the same model), and M0 uses both case sets.

| | `gemma4`: 28 cases (memory 9) | `gemma4`: 12 cases outside the window | `deepseek`: 28 (memory 9) | `deepseek`: 12 |
|---|---:|---:|---:|---:|
| `packet-v6`, budget 800 (Phase 11) | 26 (7) | 2 | 24 (5) | 1 |
| `packet-v6`, budget 2,000 | 26 (7) | 4 | — | — |
| `packet-v8`, budget 2,000 | 26 (7) | 5 | 24 (5) | 2 |

Nothing forbidden was placed as current in any `packet-v8` run. What the step added:
- **The budget** brought two of the 12 answers (an early event and a why), from facts and excerpts that 800 tokens
  had no room for.
- **`<Cast>`** brought one more: an item a character carried, from her group.
- The scene summary that holds an answer depends on how the model wrote it. With `summarize-v2` summaries the same
  runs gave 27 of 28 and 6 of 12. One case each way moved on wording alone.
- `deepseek` extraction answered fewer of the owner's cases than `gemma4`'s, although it did better on the synthetic
  tiers. The 28 cases were drafted from the `gemma4`-extracted facts, so their wording may favour it.

**Two faults found here and fixed before this record:**
1. **A finished goal in an unrelated question.** The first `<Cast>` gave every scene character's open goals. An old
   goal, reached in the story long before but never closed (K23), came into a question about arithmetic. `<Cast>` now
   groups goals only for a character the message names.
2. **A secret in the story, reworded.** That an event was kept from one character was extracted one and five turns
   after it, after the summaries of its window were written. The story so far then told the event in other words in
   a scene where that character asks about it; `packet-v6` had it in `<Private>` only. Now (ADR 0042 amendment 2,
   `summarize-v3`):
   - each summary's prompt lists the secrets stated up to 8 turns after its window, and the story's prompt lists
     them too;
   - a summary written before such a secret is held and written again;
   - written again, the story no longer told the event, only a vaguer hint (K30).

## Gates before summaries reach a packet (review, 2026-09-28)

`packet-v8` (after the turn-numbering fix took `packet-v7`), the restored copy, `summarize-v3` summaries.

**M0** (`gemma4` extraction, the production model; `packet-v6` at 800 against `packet-v8` at 2,000): no category of
the 28 cases changed and nothing more was placed as forbidden; the 12 cases outside the prompt window went from 2 to 5
(early events 1 → 3, the why 0 → 1). `deepseek` extraction: 24 of 28 and 2 of 12, as before. **Passed.**

**Secret gate** (`tools/eval_secret_gate.py`, 6 cases the owner confirmed, outside the repository). Each case is a
probe at the chat's recorded request, addressed to a character a secret is kept from (each of the chat's three main
characters has some), with the words that would tell it:

| | cases with none of the words in `<Story>` | `<Story>` present |
|---|---:|---:|
| `gemma4` summaries | 5 of 6 | 6 |
| `deepseek` summaries | 6 of 6 | 2 (held in 4) |

The miss: a `gemma4` story told a character, in other words, a plan still held as kept from her. That secret is stale:
the story had her find the plan out twice, and the facts record her knowing it, but no reveal matched the listed
secrets, so they stay open (the K29 family of misses). None of the words stood outside `<Private>` in the
`packet-v6` packets of the same requests. **Not passed** as the gate is written.

The owner chose a stricter check in front of the character a secret is kept from (ADR 0042 amendment 3):
- a summary is held there at 0.3 instead of 0.7; the story scored 0.34 against the plan;
- run again, the gate passes: **6 of 6** with `gemma4` summaries, which are now held in all six scenes, and **6 of 6**
  with `deepseek`'s, present in two;
- M0 is unchanged: 26 of 28 and 5 of 12 for `gemma4`, 24 and 2 for `deepseek`.

The cost: on this chat each of the three main characters has a secret kept from her, so `<Story>` is mostly absent
while they are together. The 12 new cases' gains come from the budget and `<Cast>`. **Both gates passed.**

## Acceptance (steps 6–7, 2026-09-28)

**Deterministic cases in CI** (`apps/sidecar/tests/test_summaries.py`), one or more for each case the spec lists: an
old scene placed for a message about it; an edit inside a window, checked on the packet (neither the old scene nor the
story made from it reaches `<Story>` until the scene is written again); a branch with only its own summaries; a secret
kept out of `<Story>` with the character it is kept from in the scene, and in strict mode; no `<Story>` for a narrator;
`<Story>` within its share; `<Cast>` lines not said again in `<Facts>`; a secret stated after a summary; facts and
threads off. The Inspector's states, a held summary naming its secret, and a character's state block have cases too.

**Upgrade from Phase 11 `main`** (`fixtures/upgrade/main-phase11.sql`, recorded from 5d40c09): every fixture (beta.7,
beta.16, beta.21, Phase 10 and Phase 11 `main`) now goes on until one sync makes two windows due; the current worker
writes both scenes and the story, and the next recall carries `<Story>`. This found a fault: an append queued only the
newest window it made due, so the story, which waits for every window, was never written (ADR 0042 amendment 4, with a
case of its own).

**Latency at 10,000 messages** (`tools/bench_story.py`: extraction on, a fact for every turn, six secrets, a scene
summary for every one of the 624 due windows and a story; 15 requests after an append each, budget 2,000; five rounds
of Phase 11 `main` (5d40c09), this branch with summaries off, this branch with them on, each run pinned to one CPU):

| | retrieve p50, ms (median of 5) | against Phase 11 `main` |
|---|---:|---:|
| Phase 11 `main` | 106.6 | |
| this branch, summaries off | 108.2 | +1.6 |
| this branch, summaries on (`<Story>` in all 75 packets) | 118.9 | **+13.1** |

The criterion (+10 ms) is not met at this size, by 3 ms: `<Story>` costs a request about 10 ms with 624 scenes.
It grows with the number of scenes; the owner's longest chat has 8 (at 1,000 messages and 62 scenes, three rounds: 20.7 ms on Phase 11 `main`, 21.8 with summaries off, 23.8 on).
What the step changed on the way:
- a first run gave +190 ms: every request checked every scene against every secret, and read every story the chat
  had ever had. A request now reads its current scenes and one story in one query, compares a scene with its window
  in the database, and checks only what it would offer (ADR 0042 amendment 4);
- runs of the same code split into about 100 and about 120 ms. The harness keeps the 10,000-message chat in its own
  process, and a full garbage collection during a request scanned it too; which request one landed in depended on
  small differences in allocation. The bench now freezes the harness's objects before it times, which the sidecar
  alone never needs.

Without a model (`tools/bench_scale.py 10000`, two pairs), nothing changed: lexical retrieve p50 11–14 ms, append
p50 158–170 ms, fact read p50 102–106 ms on both.

**Real-host smoke** (an isolated PocketRisu from `ghcr.io/pocketrisu/pocketrisu:latest`, a stub chat model, a stub
extraction model that also answers the summary prompts, this branch's sidecar and worker, plugin build `8f2d502c32b2`
at the default budget). A test chat of 37 turns, first seen by this sidecar, then 24 messages in play:
- the first sync queued the windows due then; three more were completed in play and summarized by the worker while
  the chat went on (seven scenes and four stories, 11 calls, no failed job);
- the request after the last message carried `<Story>` with the story of all seven scenes (turns 0–55, the newest
  written in play) and one scene summary; requests took 55–62 ms in the plugin (sync about 30, retrieve about 15);
- the Inspector showed the summary generation, the story as covering 7 of 7 scenes and each scene as current, one
  marked "not used while 카이토 is in the scene" (its text names what is kept from him). He was not in that request's
  scene, so it could be offered.
