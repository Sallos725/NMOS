# Scene summaries — real-model tier (Phase 12 step 4, ADR 0041)

Measured 2026-09-28. `summarize-v2`: the scene prompt lists the window's OPEN SECRETS and says never to write their
content; whether a stored summary may be used is checked when it is read (`summaries.leaks`).

## Method

`tools/eval_summaries_model.py`: 8 Korean scenes written for this evaluation (6 scenes of 3–4 turns, 2 "story so far"
inputs of 3 scene summaries). Each scene ran 3 times on each model, through the local Ollama, with 2 workers and no
errors. Raw prompts, replies and checks are in `fixtures/model/summaries/`. Each reply is checked for:

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
| secret | the secret is the scene (a kiss kept from a child) | 3/3 | 3/3 |
| secret | a secret listed but not touched | 3/3 | 3/3 |
| ooc | an out-of-character note | 3/3 | 3/3 |
| quiet | a quiet afternoon (nothing invented) | 3/3 | 3/3 |
| story | the story so far | 3/3 | 3/3 |
| story | the story keeps the order | 3/3 | 3/3 |
| **all** | | **21/24** | **24/24** |

**The miss, shown to the owner:**
- `gemma4` never wrote the secret's content (the forgery), 3 of 3.
- But it wrote the act it is about, 3 of 3: "카이토가 자리를 비운 사이 하나는 서랍 속 편지를 확인하고 다시 넣어두었다".
- The check counts the object as a leak, so the scene fails.
- Two things weigh against calling this a leak. The act happened while Kaito was away, and NMOS does not treat
  something done while a character is away as kept from them (ADR 0033, "away is not kept from"). The listed secret
  was only the forgery.
- `deepseek` left the moment out, or wrote "그에게 숨기는 일을 했다" and "하나는 카이토에게 무언가를 숨기고 있다".
- Neither model wrote the content of either secret in any run. The kiss that was the whole scene came out as "부엌에서
  만났다" (`gemma4`) or "둘만의 시간을 가졌다" and "엘피가 모르는 일을 함께 했다" (`deepseek`).

## What changed before this record

The first run (fingerprint `bee481978138f6a8`, `*-first-prompt` fixtures) had `gemma4` at 18/24. Three of its six
misses were the check's own:
- the kiss summaries left the kiss out, but kept the scene's names and setting ("엘피가 잠든 사이 유우마와 …"), and
  trigram containment scored them 0.68, above the 0.6 then set;
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

The restored copy (PHASE-11 Q1), read-only, lexical recall only (`--no-vectors`), the request at turn 73. Two
extractions of the same chat: `gemma4:31b-cloud` (`extract-v13`, copy `nmos_m0v13b`) and `deepseek-v4.1-flash`
(`extract-v13`, copy `nmos_m0ds`, 73 turns re-extracted through the local Ollama for this comparison). Each copy has
its own summaries (`summarize-v3`, 8 scenes and the story, written by the same model), and M0 uses both case sets.

| | `gemma4`: 28 cases (memory 9) | `gemma4`: 12 cases outside the window | `deepseek`: 28 (memory 9) | `deepseek`: 12 |
|---|---:|---:|---:|---:|
| `packet-v6`, budget 800 (Phase 11) | 26 (7) | 2 | 24 (5) | 1 |
| `packet-v6`, budget 2,000 | 26 (7) | 4 | — | — |
| `packet-v7`, budget 2,000 | 26 (7) | 5 | 24 (5) | 2 |

Nothing forbidden was placed as current in any `packet-v7` run. What the step added:
- **The budget** brought two of the 12 answers: the heater and why the soup tasted odd, from facts and excerpts
  that 800 tokens had no room for.
- **`<Cast>`** brought one more. What Elpi carried the cookies in came from her group: `엘피 possesses 양철 상자`,
  turn 19.
- The scene summary that holds an answer depends on how the model wrote it. With `summarize-v2` summaries the same
  runs gave 27 of 28 and 6 of 12. One case each way moved on wording alone.
- `deepseek` extraction answered fewer of the owner's cases than `gemma4`'s, although it did better on the synthetic
  tiers. The 28 cases were drafted from the `gemma4`-extracted facts, so their wording may favour it.

**Two faults found here and fixed before this record:**
1. **A finished goal in an unrelated question.** The first `<Cast>` gave every scene character's open goals.
   Radia's goal to check the kitchen heater had been over since turn 29, but nothing closed it (K23), and it reached
   a question about arithmetic. `<Cast>` now groups goals only for a character the message names.
2. **A secret in the story, reworded.** A kiss at turns 61–63 was stated to be kept from Elpi only at turns 64 and 68,
   after the summaries of its window were written. The story so far said "…모두에게 애정을 표현하며 입을 맞추었고…" in
   the scene where Elpi asks what happened last night; `packet-v6` had it in `<Private>` only. Now (ADR 0041 amendment
   2, `summarize-v3`):
   - each summary's prompt lists the secrets stated up to 8 turns after its window, and the story's prompt lists
     them too;
   - a summary written before such a secret is held and written again;
   - the same story then read "…신체적 접촉을 통해 애정을 확인했습니다": no kiss, a vaguer hint (K30).
