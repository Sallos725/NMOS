# 0093 — The author's note in the chat's language, and a check by meaning when it is not

Status: accepted, 2026-11-25, PHASE-65 (S8). The owner's plan, decision 12 (the note's language: the chat's by
default, English on request with a cross-language secret check). Amends PHASE-50 (amendment 2: an English Markdown frame and
English model parts) for the model-written parts of PHASE-50, PHASE-53 and PHASE-56. Recorded as built at `361130c`.

## Context

The note's model-written parts (the chronicle, the custom part) were written in English. A secret kept from someone is
checked in every line of the note by `tells`, which compares letters at `LEAK_NEAR`. An English chronicle of a Korean
chat's secret shares no letters with it, so the check never fired there (C2): for a Korean chat the gate on the
model-written parts was open.

## Decision

1. **`language`**, on a note request (`notes.Ask.language`): `"chat"` or `"en"`. A request without the field (an
   older plugin) reads `"chat"`. `"chat"` reads the chat's language from its scene summaries, else from its threads
   and NOW facts (`chat_language`: `"ko"` or `"en"`), and the prompt asks the model to write in it; `"en"` keeps the
   prompts as they were. The frame (headings, assembled lines) stays English Markdown. The plugin's Author's Note
   Studio offers both, `chat` first.
2. **A check by meaning, for English only.** When a model writes a part with `language="en"` and the owner left
   secrets out, the reply also goes through `semantic_leaks` (`api.leak_check`): by the configured embedder
   (`embedding_leak_checker`: each line and sentence against each secret's content, the names of its holders and of
   those it is kept from taken out of both, cosine ≥ 0.62, one embedding request per text), else by one call of the
   note's model (`model_leak_checker`). A checker that errors or answers out of shape counts as a leak, so the part
   falls back as for any leak. With `"chat"` the reply is in the secret's script and the lexical check suffices.
3. **Every line is checked.** Open-thread lines and assembled lines go through `tells` one by one. Open threads are
   capped at the 15 newest and 25 % of the part, with "+N more".
4. **Before the first summary.** With no scene summary (the first turns, the summarizer off, every summary held), the
   chronicle and the custom part are made from the shown threads and NOW facts; `no_scenes` only when there are
   neither.
5. The language and whether a check by meaning ran are part of the note's cache key.

## Consequences

- The default changes with no switch: a Korean chat's chronicle and custom part are Korean from the deploy on. The
  owner picks `en` for the earlier behavior.
- `en` with secrets left out costs one embedding request per model part, or one extra model call when no embedder is
  configured.
- A chat whose summaries are held, or that has none, gets a model-written chronicle where it got `no_scenes`: one model
  call on the owner's press.
- The conditional-address label stays English inside a Korean note (`notes.address_lines`, Phase 64's `address_label`
  without a language).
- `held_keys` (PHASE-65 S4, B8) is not passed by the note yet: the "diverged from the setting" part reads every
  lorebook entry, as before.
- No note was made with it on a real chat: the check and its threshold are pinned by tests only.
