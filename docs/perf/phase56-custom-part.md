# Phase 56 — the custom part on a real model (step 4, Q3 a)

Run 2026-11-05 on `docs/phase56-custom-note-part` against a throwaway copy of the test install's database on the test
Postgres (:5436, read-only connection; the copy Phase 53 measured), through the eval Ollama on :11500
(`gemma4:31b-cloud`, as Phase 53's run). No paid call. The script and every part it wrote stay outside the repository
(`~/nmos-eval/phase56`); this page holds counts only, as the repository is public.

Three stand-in prompts (the owner's own come at the trial, Q4):

| prompt | language of the prompt | setting toggle |
|---|---|---|
| outfits: each character's clothes and what they carry, one line each | Korean, names no language | off |
| debts: who owes whom what, one line each, with the turns | English | off |
| vs_setting: how each main character's situation now differs from the card or lorebook | English, asks for Korean | on |

## Result

14 chats in the copy; 4 have a scene summary (last turns 13, 49, 60, 76).

| | parts asked | made by the model | asked again | held for a secret | failed | `no_scenes` |
|---|---:|---:|---:|---:|---:|---:|
| all prompts | 42 | 12 | 0 | 0 | 0 | 30 |

- Every made part was one call; every reply was the JSON frame with a string `text`.
- Input without the setting: 2,400–6,700 characters (about 800–3,700 input tokens); with it: 21,000–67,000 characters
  (5,400–19,700 tokens), 2–21 lorebook entries in and 0–36 left out for length. Parts written: 73–416 characters.
- Every call took under 2.2 s.
- **Language (Q1 a): a correction.** With the first frame (*the language the instruction asks for; if it names
  none, English*) the Korean outfits prompt, which names no language, was answered in Korean on all four chats: the
  model took the prompt's own language as the request. The frame now says the instruction's own language is not such a
  request. Rerun on the four chats: the prompt that names no language is answered in English (names and the chat's
  words as written, per the frame), and the same prompt with "in Korean" added is answered in Korean.
- The owner reads the parts at the trial; whether they help the replies is the owner's own trial, not a gate (Q3 a).
