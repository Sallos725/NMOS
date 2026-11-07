# Phase 56 — The author's note gets a part the owner words: a custom prompt

Status: **approved**, 2026-11-05 (an owner request, not a roadmap stage); shipped in `v0.6.0`. The owner called the
release (2026-11-07: "릴리즈 바로 가자") before making a part with it, so Q4's trial on real chats is the owner's use after the tag. Q1–Q4 answered as recommended (owner,
2026-11-05), implementation approved. The shape below (C1–C7) follows the owner's answers in the design conversation of
2026-11-05: a checkbox opens a prompt box and the model writes the part as the prompt asks; the input is the story,
with the setting behind its own toggle, off by default; one prompt for every chat. Amendment 1 (from the code, before
step 2) changes where the prompt is saved, not what the owner sees. Linear: to be filed by the owner.

In the same conversation the owner considered letting NMOS call the host's main or auxiliary model (the V3
`runLLMModel`) and decided against it (2026-11-05): this phase uses the model the note already uses
(`notes.model_for`, the extraction model) and nothing else.

**High risk if built** (`AGENTS.md §14`), for Phase 50's and Phase 53's reasons:
- **secrets:** the author's note reaches every prompt verbatim with no secret gate (HOST-FACTS H19), and the new part
  is the first one whose output NMOS cannot check line by line, so it is held to Phase 50 S4's bar (C4);
- **a model's claim reaches every prompt:** the part is free text the owner's own prompt shapes, so it cannot be held to
  Phase 53 S4's quote and turn check. The panel says so (C6), and the owner reads it before pasting;
- **canon and provenance:** the note is a canon source (ADR 0045, 0047). NMOS's block stays out of the canon
  (`noteblocks`, unchanged), and with the setting toggle on the part reads canon texts the way Phase 53 S3 does.

Invariants it touches (`AGENTS.md §3`): **the response model never writes canonical memory** (the part is a view; it is
not stored and no packet reads it); **the plugin never mutates host chat data** (the owner pastes, as in Phase 50);
**every automatic semantic claim has provenance**: the part is not an automatic claim of NMOS's but text the owner asked
for in their own words, and its heading says so (C5). That is the reading this phase proposes; Q2 asks the owner to
confirm it.

## Why

Read from the code (`main` at `446d5fb`).

1. **The note's parts are fixed.** `notes.KINDS` is `diverged`, `chronicle`, `changed`, `address`; each has its own
   prompt (`divergence.PROMPT`, `notes.CHRONICLE_PROMPT`) or none. An owner who wants something else in the note
   (the characters' current outfits, a list of who owes whom, a tone reminder built from the latest scenes, the
   chronicle in another shape) has no way to ask for it short of writing it by hand.
2. **The material is already there.** The chronicle's input (`notes._input`: the story so far, the newest scene
   summaries, the threads and the current locations and states) and the setting's side (`divergence.canon_input`) are
   built on every request for the parts that use them. A part the owner words needs no new data, only a new prompt
   around the same input.

## Goal

The owner ticks **커스텀 / Custom** in the **For the author's note** group, writes a prompt (or keeps the one saved
last time) and presses **Make**: the note gains one more part, written by the extraction model as the prompt asks, from
the chat's story (and, with a second toggle, its setting), with secrets kept out as the other parts keep them.

## Scope

C1. **The panel.** The **For the author's note** group gets a fourth toggle after **Address and standing**:
**커스텀 / Custom**, off by default. Ticking it shows:
- a prompt box (a `textarea`, at most `PROMPT_MAX` = 4,000 characters, a counter under it);
- a toggle **설정(카드·로어북)도 넣기 / Include the setting (card, lorebook)**, off by default, with one line saying the
  input grows by up to 60,000 characters when it is on;
- one line saying the part is written freely from the prompt and NMOS cannot check it line by line (C6).

The chronicle's length (3,000 / 6,000) applies to the custom part too. The plugin change is the toggle, the box, the
second toggle, the texts and sending them (`nmos-plugin-stays-light`): the input, the call, the checks and the cache are
the sidecar's.

C2. **One prompt for every chat** (owner, 2026-11-05). The prompt is a sidecar setting, `notes_custom_prompt`
(`runtime.EDITABLE`, a string of at most `PROMPT_MAX`, stored in `app_config` like the other settings), so it is the
same on every device that talks to the sidecar and goes with a full archive (it is not a secret). The panel fills the box
from the settings view when the form opens and saves the box's text through the settings API when **Make** is pressed
with **Custom** on and the text changed. The request itself carries the prompt text (C3), so a note is made from what
the box showed even if the save fails; a failed save is said under the button and does not stop the note.

C3. **The request.** `POST /v1/conversations/{id}/notes` accepts `custom` among `sections`, with two new fields:
`custom_prompt` (a non-empty string of at most `PROMPT_MAX` after trimming, required when `custom` is asked for, else
ignored) and `custom_setting` (boolean, default false). `notes.Ask` gains both. `custom` is last in `KINDS`, so the
note's order is the header, `## Diverged from the setting`, `## Chronicle (tA–B)`, `## Now`, `## Open threads`,
`## Address and standing`, then the custom part (C5). An older plugin never sends `custom`; nothing it asks for changes.

C4. **The input, the call and its checks.** `notes.custom(...)`:
- **The story's side** is the chronicle's input, built the same way: the newest scene summaries in at most
  `INPUT_CHARS` (40,000), the story so far for the turns they leave out, the threads shown (not stale, secrets
  filtered), and the `located_in` / `has_status` facts of `NOW`. A scene summary or the story so far held for a secret
  (`summaries.held`) is left out and counted, as the chronicle does. No scene summary at all: the part is not made
  (`reason: no_scenes`), as the chronicle.
- **The setting's side**, only with `custom_setting` on: `divergence.canon_input` over the manifest in force, unchanged
  (the card's story fields, the persona and the note without NMOS's block always; then the ranked lorebook entries; at
  most `ENTRY_CHARS` a text and `CANON_CHARS` in all). The panel reports how many entries went in and how many did
  not fit, as for **Diverged from the setting**.
- **The call:** one call to `notes.model_for` (the extraction model), JSON mode as configured. The system message is a
  fixed frame and the owner's prompt inside it, marked as the owner's instruction:
  the input's parts and what each is; *write what the instruction asks, from the input only, at most N characters;
  keep names, titles, places and quoted words as the input writes them; write in English unless the instruction
  explicitly names another language, the instruction's own language not being such a request* (Q1; worded so after
  step 4, `docs/perf/phase56-custom-part.md`); the secrets rule of the chronicle (`SECRETS_KEPT` or `SECRETS_TOLD`); and *answer with JSON
  only: `{"text": "..."}`*. The owner's prompt cannot remove the secrets rule or the JSON frame: it is placed before
  them, and the reply is checked whatever it asked for.
- **The checks:** a reply that is not JSON with a non-empty `text` is asked again once. With secrets off, a reply that
  repeats an open secret at `LEAK_NEAR` (`summaries.leaks`, as the chronicle) is asked again once with the secrets
  named; a second such reply is dropped. The text is cut to the length (`_cut_lines`). There is **no fallback**: a part
  that fails or is held twice is left out of the note and the panel says why (`reason`: `no_model`, `failed`, `held`).
  An empty `text` that passed is an answer: the part is left out with `reason: none`.

C5. **The note.** The part is `## Custom (owner's prompt)` and the model's text under it; the model may use `###`
headings and lists inside. It is in the same block between Phase 50's markers, after the other parts, and the
header's lines stay as they are. Nothing is stored; no packet reads the part; the canon still never reads the block.

C6. **What the panel says about it.** Under the result, the custom part's line reads like the others' (made by the
model, cached, how many summaries held, how many setting entries in and left out) and adds: *written from your prompt;
NMOS did not check it against the story; read it before you paste it.* With **Include the setting** on, the line
counts the entries as **Diverged from the setting** does.

C7. **The cache.** The part is cached like the chronicle (`CACHE_MAX` 64, in memory), keyed by everything that goes into
the call: the prompt text, `custom_setting`, the length, `secrets`, the model's name and the whole input text (the story's
side and, when on, the setting's). Making the note again with nothing changed calls nothing; editing one character of the
prompt calls again. A failed or held part is not cached, so the next **Make** tries again.

## Out of scope

- Calling the host's main or auxiliary model (`runLLMModel`); the owner decided against it (2026-11-05).
- More than one custom prompt, named presets, or a prompt per chat or per card (C2: one for every chat).
- A prompt that changes the other parts (the chronicle's or the divergence prompt); they stay as they are.
- NMOS writing the note through the host, or putting the part into the packet.
- Checking the free text against the story (Phase 53 S4's quote and turn check needs a structured answer).
- New input: the raw messages, the Inspector's memory view beyond `NOW`, embeddings or recall.

## Questions and proposed answers

- **Q1 — the language of the part. Answered (owner, 2026-11-05): (a).** The other parts are English (Phase 50 amendment 2: the story model reads the note).
  **(a) Recommended:** English unless the owner's prompt asks for a language; names and quoted words as the chat writes
  them. (b) Always English, whatever the prompt says. (c) The chat's language.
- **Q2 — what the frame forbids. Answered (owner, 2026-11-05): (a).** **(a) Recommended:** the frame says *from the input only* (no invented events, no
  guesses), and the owner's prompt shapes what to pick and how to write it; the part is the owner's text, so it is not
  held to the provenance check (C5, C6). (b) No such line: the prompt may ask for anything, including what the input does
  not say (for example "suggest where the story could go next"); the panel's warning stays.
- **Q3 — measurement** (no paid call, `nmos-api-spend`). **Answered (owner, 2026-11-05): (a).** **(a) Recommended:** the zero-call unit tests (the request,
  the frame, the checks, the cache, the order) and, on throwaway copies of the test install's chats (test PG :5436), the
  model path on the local eval Ollama (:11500) only, with two or three prompts the owner gives; the owner reads every
  part. Whether the part helps the replies is the owner's own trial, not a gate. (b) The same and one paid sample, its
  cost estimated and approved first.
- **Q4 — release. Answered (owner, 2026-11-05): (a).** **(a) Recommended:** as Phase 53 Q1: the test install (6131/6113) first, then the install the owner
  uses, when the owner says; released with the next minor after `0.5.0` (a new part and a new setting, not a patch).
  (b) The test install only until a release.

## Amendment 1 (2026-11-05, from the code, before step 2): the prompt has its own endpoint

C2 put the prompt in `runtime.EDITABLE`, which is saved through `PUT /v1/config`. That route rebuilds the runtime
configuration and runs `activate` (the extractor, projection, summarizer and canon generations) for any key but the
parser presets, and `runtime.effective` hands every `EDITABLE` key to `Settings`. A note's prompt has nothing to do
with either. It is saved instead as the status pins are (PHASE-43): its own `app_config` key, `notes_custom_prompt`,
read with `GET /v1/notes/prompt` and written with `PUT /v1/notes/prompt` (`{"prompt": "..."}`, at most `PROMPT_MAX`
after trimming; an empty one deletes the row). It is still one prompt for every chat, the same on every device, and in
a full archive (the archive copies the `app_config` rows it lists, `archive.SETTINGS`, so the key is added there).
Step 2's `runtime.EDITABLE` reads as this endpoint.

## Steps

1. This spec (docs only), for the owner's answers.
2. **The sidecar.** `notes.KINDS` gains `custom`; `notes.Ask` gains `custom_prompt` and `custom_setting` with their
   checks (422 on a missing or too-long prompt); `notes.custom()` builds the input from the chronicle's and Phase 53's
   builders without changing them, calls, checks and caches (C4, C7); `notes.make` places it last (C5);
   `runtime.EDITABLE` gains `notes_custom_prompt` (C2); the route reads the summaries when `custom` is asked for and
   the manifest only when `custom_setting` is on (today it reads them for `chronicle` and `diverged` only). Tests: the request's validation, an older request unchanged
   byte for byte, the frame holds the prompt before the secrets rule, a leaked secret asked again then dropped, invalid
   JSON asked again, no model and no scenes, the cache hit and its miss on a changed prompt or toggle, the order in the
   block, the setting's side only with the toggle on.
3. **The plugin.** The toggle, the box with its counter, the setting toggle, the warning, the texts (Korean and English),
   loading and saving `notes_custom_prompt`, sending `custom_prompt` and `custom_setting`; the result line (C6). The
   bundle rebuilt (`dist/`).
4. **The check** (Q3) and the trial (Q4).

## Acceptance criteria

1. With **Custom** off, the note and every request are as before: an existing request's response is byte-identical.
2. With **Custom** on and a prompt, the note ends with `## Custom (owner's prompt)` and the model's text, within the
   chosen length, after the other parts it holds.
3. With secrets off, no part the panel shows repeats an open secret at `LEAK_NEAR`; a reply that did is asked again
   once, and dropped with `reason: held` if it does again.
4. Without **Include the setting**, no canon text is in the call; with it, the call holds exactly what
   `divergence.canon_input` gives for the same chat.
5. The prompt saved on one device is in the box on another that talks to the same sidecar, and a full archive restored
   into a fresh install carries it.
6. Making the note again with nothing changed calls no model; changing the prompt calls once.
7. The panel states, every time the part is shown, that NMOS did not check it.

## Stop conditions

- The local model cannot keep the JSON frame for ordinary prompts (most replies need the retry): report it before step 3
  with the counts, instead of loosening the frame.
- The owner's prompts in Q3 regularly make the model drop the secrets rule (held twice): stop and bring the cases to the
  owner; do not ship a part that is mostly left out.

## Risk

High risk (see the top): secrets on an ungated surface, model text the owner pastes into every prompt, canon read with
the setting toggle on. The off path must stay byte-identical (criterion 1). No schema, extraction, packet, recall or
memory selection change; one new editable setting.
