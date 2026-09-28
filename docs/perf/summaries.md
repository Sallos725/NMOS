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
  one that left it out scored 0.59 and stays usable. `deepseek` wrote "둘은 소라에게는 비밀로 할 일을 함께 했다", 3 of 3.

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
