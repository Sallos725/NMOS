# Scene summaries — real-model tier (Phase 12 step 4, ADR 0042)

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
