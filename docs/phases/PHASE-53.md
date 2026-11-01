# Phase 53 — The author's note says where the story left the setting

Status: **approved**, 2026-11-01 (an owner request, not a roadmap stage). Implementation plan:
`docs/superpowers/plans/2026-11-01-phase53-diverged.md`. It reworks Phase 50's note (AGE-88, PR #315).
The shape below (S1–S7) was agreed with the owner in the design conversation of 2026-11-01; Q1–Q2 are answered. **Implementation approved (owner, 2026-11-01).**

The owner added the author's note feature for one purpose: to help the story model with events the setting does not
allow for, such as a character's arrest or death, which the card and the lorebook keep contradicting on every turn.
What Phase 50 built drifted from that purpose (owner, 2026-11-01): its headline part is a chronicle of the story so
far, and the part meant for divergence, **Changed from the setting**, misses most such events (Why, 1–3). The owner
chose (2026-11-01):
- **What counts:** every event of the story that does not fit the card's or the lorebook's setting: a character's
  life and freedom (death, arrest, disappearance, a grave wound, exile), a position or allegiance (dismissal,
  promotion, desertion, a change of side), a relationship turned around, and the world and its places (a city
  destroyed, a regime fallen, an item gone).
- **How it is found:** a model compares the setting with the story (option B of the conversation). The deterministic
  alternative (more signal classes over stored facts) was not chosen: it cannot see a divergence the setting states
  only in free text, or one the extractor never wrote as a fact.
- **Which setting goes in:** the card and the persona whole, and the lorebook entries that name what the story is
  about (S3), not only the entries the host activated.
- **The rest stays:** the chronicle and **Address and standing** remain, off by default, under the new part.
- **Still copy-paste:** the owner places the text in the note, as in Phase 50.

**High risk if built** (`AGENTS.md §14`), for Phase 50's two reasons and one more:
- **canon and provenance:** the note is a canon source (ADR 0045, 0047); NMOS's block stays out of the canon
  (`noteblocks`, unchanged), and this phase reads canon texts in a new place (S3);
- **secrets:** the note reaches every prompt verbatim with no secret gate (HOST-FACTS H19), so the part is held to
  Phase 50 S4's stricter bar (S5);
- **a model's claim reaches every prompt:** a line the model invents would be told to the story model on every turn
  as truer than the card, so every line must cite canon text that exists and turns that exist (S4).

Invariants it touches (`AGENTS.md §3`): **the response model never writes canonical memory** (the part is a view; it
is not stored and no packet reads it); **the plugin never mutates host chat data** (the owner pastes); **every
automatic semantic claim has provenance** (each line names its canon text and its turns, both checked).

## Why

Read from the code (`main` at `6696682`).

1. **A divergence is listed only where the setting stated the same slot.** `notes.changes` lists a current story fact
   only when its history holds a canon fact of the same predicate and subject (and object, where `per_object`) that it
   superseded or ended. A card that describes a character without a `has_status` fact gives the story's "arrested" or
   "dead" nothing to supersede, so no line.
2. **Most divergences are of predicates it never compares.** `notes.CHANGEABLE` is the single-valued predicates and an
   item's holder. A desertion is `member_of`, a fallen city `world_fact`, a death often an `event`: all multi-valued,
   never listed, because NMOS cannot tell a change from an addition there (Phase 50 S3).
3. **A change of position is left out on purpose.** `identity` is excluded (Phase 50 amendment 1, ADR 0047 amendment 1):
   on the test install's copy 57 of one chat's 68 lines were the card's identity told again in other words. A
   dismissal or a promotion is an `identity` change, so it is never listed either.
4. **The setting says much that canon facts do not hold.** Canon facts are what `canonfacts` extracted from each text
   (its first `MAX_PARTS` × `PART_CHARS` = 24,000 characters); a lorebook line can state a situation ("the guard
   answers to Captain Ren") that no single fact carries. Only the text itself shows what the story has broken.
5. **The story's events are not all facts.** The extractor misses some events (the recall weaknesses of AGE-86 were
   mostly extraction-side), but the scene summaries and the story so far usually tell them.
6. **The note's header does not say the setting is out of date.** It says "the latest messages take precedence"; it
   never tells the story model that the card and the lorebook below were written before the story began.

## Proposal

S1. **What the owner does.** The panel's **For the author's note** group (Phase 50 S1, amendment 2) gets a new first
part, **설정과 달라진 것 / Diverged from the setting**, on by default. **Chronicle** and **Address and standing**
remain as toggles, off by default. Phase 50's **Changed from the setting** is no longer a toggle: it is the new
part's fallback (S6). The panel says that making the part calls the model once and that whatever is pasted is sent
with every request. The plugin change is the toggle's name, the defaults and the texts (`nmos-plugin-stays-light`).

S2. **The story's side of the input**, all of it stored for the chat's head:
- the current story facts (the Inspector's memory view, as `notes.make` reads it), each with its turn;
- the story so far and the newest current scene summaries that fit, each with its turn range;
- the named entities among them, with their merged aliases (ADR 0046, 0058), pick the lorebook entries (S3); the prompt
  carries them only through the facts and summaries, which already name them.
Together at most `STORY_CHARS` (20,000). With secrets off (S5) nothing secret or private goes in.

S3. **The setting's side of the input** (owner, 2026-11-01: the relevant entries, not only the activated ones), from
the manifest in force (`canon.manifest`):
- **always:** the card's `card:desc`, `card:personality`, `card:scenario` and `card:greeting`, the `persona`, and the
  `note` without NMOS's block (`noteblocks.strip_blocks`);
- **lorebook entries, ranked:** an entry is a candidate when its activation keys (the manifest's metadata) or its
  text name an entity of S2 by a name or an alias. Candidates rank by how many of S2's entities with a story fact
  they name, then by how many S2 entities, then by how recently the story stated a fact of one of them; ties by key.
- **caps:** at most `ENTRY_CHARS` (4,000) of a text, at most `CANON_CHARS` (60,000 since amendment 1; 30,000 before)
  in all, the card and persona
  first. The panel says how many entries went in and how many candidates did not fit.
Entries are matched by name in Python over texts the sidecar already holds: no embedding and no extra call.

S4. **The model call and its check.** One call (`notes.model_for`, the extraction model, as the chronicle's) is given
both sides with each canon text under its key and each story item with its turns, and asked for JSON:
`{"diverged": [{"key", "quote", "subject", "now", "turns", "kind"}]}`, where `quote` is the setting's words that no
longer hold, `now` how things stand in the story, `turns` the turns that show it, and `kind` one of `life`, `position`,
`relationship`, `world`, `other`. Only what the input says; a setting line the story merely adds to is not a
divergence. The sidecar then checks every item and drops what fails:
- `key` is a canon text the call was given;
- `quote`, whitespace and case normalized, is in that text (at least `QUOTE_MIN` = 12 characters);
- every turn is at most the head's last turn and is a turn of a story fact or within a scene summary's range that the
  call was given;
- two items with the same key and quote are one line (the newer turns).
Invalid JSON, or no item left while the reply named some, retries once; then the fallback (S6). An empty list that
passed is an answer: nothing in the setting has changed.

S5. **Secrets**, as Phase 50 S4: off by default. Off, every secret still kept from someone is listed in the prompt as
one it must not tell, and the reply's lines are checked with `summaries.leaks` at `LEAK_NEAR` (0.3); a held reply is
retried once with the held secrets named, then the fallback, built without secret or private facts. On, the secrets go
in and their lines say who does not know them.

S6. **The fallback.** No model configured, the call or its retry failing, or the owner choosing no model: the part is
Phase 50's deterministic **Changed from the setting** (`notes.changes`, unchanged), under the new heading, and the panel
says it was made without a model and lists less.

S7. **The note.** Still one block between Phase 50's markers (amendment 2), English Markdown, the parts in this order:
the header, `## Diverged from the setting`, `## Chronicle (tA–B)`, `## Now`, `## Open threads`,
`## Address and standing`. The header gains one line: the card and the lorebook were written before the story began,
and where they disagree with this note, the note is true now. A line reads
`- Ren (lorebook "Royal Guard"): the setting says "Captain of the Royal Guard" → now arrested and held in the capital
prison (t42–44).`, with the entry's comment as the host shows it, or `card` / `persona` / `author's note`. Names and quoted words stay as
the chat writes them. The cache is Phase 50 S7's, keyed by the fingerprint of both inputs (fact and summary ids, the
canon revisions read), the options and the generation: making it again with nothing changed calls nothing. Nothing is
stored; no packet reads it; the canon still never reads the block.

## Out of scope

- NMOS injecting the part by itself, or writing the note through the host.
- The deterministic signal classes of the conversation's option A (a setting fact ended by the story, a story state on a
  canon entity the setting is silent about); the fallback stays Phase 50's.
- A hybrid that sends only deterministic candidates to the model (option C); a later proposal if the cost proves high.
- Embedding search over lorebook entries; changing the canon read, canon facts, conflicts or locks.
- Changing the packet or the story so far.

## Questions for the owner

- **Q1 — release. Answered (owner, 2026-11-01): the test install, then the install the owner uses as a second trial.**
  The trial build goes to the test install (6131/6113) first and, once it passes there, to the install the owner uses
  (`owner-deployment`), before any release; the owner says when that deploy runs. The second install is the owner's
  trial on a database the implementation agent does not read: nothing of this phase reads, copies or measures it, and
  what it shows comes from the owner. The release itself is the next minor after `0.5.0` (a toggle and a new model call
  are not a patch).
- **Q2 — measurement** (no paid call, `nmos-api-spend`). **Answered (owner, 2026-11-01): (a).** (a) **Recommended:** zero-call checks on throwaway copies of
  the test install's chats (test PG :5436): S3's candidates and caps per chat, and whether the entries of the
  divergences the owner can name are among them; then the model path on the local eval Ollama (:11500) only, every line
  checked by S4 and S5 and read by the owner; whether the note improves the replies is the owner's own trial, not a
  gate. (b) The same and one paid sample, its cost estimated and approved first.

## Steps

1. **Spec** (this file): Q1–Q2 answered and implementation approved.
2. **Sidecar:** S2–S4 and S6–S7 with the stub model: a quote not in its text dropped, a turn out of range or uncited
   dropped, a key not given dropped, invalid JSON retried then the fallback, an empty answer kept, S3's ranking and
   caps, the card always in, the cache. Synthetic chats and names only (public repository).
3. **Sidecar:** S5, with the stub model: a reply that tells a kept secret retried, then the fallback without secrets.
4. **Plugin:** the new toggle first and on, the chronicle and address off, the texts (`i18n.ts`).
5. **Measurement** (Q2) and the owner's check on the test install: make, paste, reload, a request, the canon unchanged.
6. **Second trial** (Q1): the same build on the install the owner uses, when the owner says; the owner's own use and
   report, with no read of that database by the agent.

## Amendment 1 (owner, 2026-11-01, from the measurement): 60,000 for the setting, the model through the eval Ollama

Step 5's zero-call check (below) showed the setting's cap held 7–8 of 51–52 candidate entries on the three long chats.
The owner chose to raise `CANON_CHARS` to 60,000 (about 10,000 more input tokens per Make, paid only when the owner
makes the part); ranking still puts first the entries naming characters the story changed. The host has no local
generation model (every one on the eval Ollama is a cloud model), so for Q2's model path the owner chose the cloud
`gemma4:31b-cloud` through the eval Ollama on :11500 instead of a local one. Two fixes came from that run: a reply's key
copied with its header label is still its key, and the prompt says a translation or restatement is not a divergence.

## Step 5 evidence (2026-11-01): measurement on the test install's copy

A throwaway copy of the test install's database (`nmos_p53_m` on test PG :5436, from `nmos_p32_try` by `pg_dump`; the
source only read), 14 chats with a head. Scripts and every output (the parts, the raw replies) are outside the
repository in `~/nmos-eval/phase53/`; below are counts and roles only.

- **Zero-call** (`zero_call.py`): building both sides took at most 0.07 s and the reads at most 0.18 s per chat. At
  30,000 the three long chats (49–76 turns) had 51–52 candidates and 7–8 given (44 left out); at 60,000, 15–21 given.
  The entity that matched most entries matched 25–71 % of a chat's candidates and was never the card's character; of
  the short Korean names' matches, none was inside a longer word (each was a name and its particle), so no Korean
  word-boundary rule is needed now. `canon.manifest` loaded up to 1.4 times the revisions in force (215 for 154).
- **Model** (`model_run.py`, three runs, about 30 calls, 3,400–23,600 input tokens each, 0.7–2.6 s a call). First run:
  on 4 of 13 chats every item named its key as the whole header (`persona · persona`) and was dropped, falling back
  after a retry; fixed (above). After both fixes, every chat's part was the model's in one call: 10 lines on 6 chats,
  1 item dropped for a quote not in its text, nothing on the 6 chats of four turns or fewer. Read by the agent: 6 lines
  are true divergences, among them the case this phase is for (a status two characters have in a lorebook entry that
  the story ended, on two chats of the same card) and a card's described clothing the story changed; 4 are wrong or
  doubtful (a persona's item named again in another language, a weak inference from a plugin's data entry kept in
  the lorebook, a "former" read as "current", a reading of a persona's character). One event told by several setting
  lines (a goal, a status) gives a line each. The owner reads the text before pasting it; no further prompt tuning.
- Not yet: the owner's check on the test install (the build there, then make, paste, reload, a request).

## Steps 2–4 evidence (2026-11-01)

Built on `docs/phase53-diverged-from-setting`, plan `docs/superpowers/plans/2026-11-01-phase53-diverged.md`.

- **Sidecar.** `divergence.py` (`story_input`, `canon_input`, `check`, `line`, `diverged`), `notes.py` (`KINDS` with
  `diverged` first, the header's line that the setting is older, `Ask.of` drops `changed` beside `diverged`,
  `make(..., canon=...)`), the endpoint passes `canon.manifest` and the summaries when the part is asked.
  `tests/test_divergence.py`: 17 tests on synthetic chats (the story's side and its cap, a held scene left out, a
  denial; the card, persona and note always in, the note without its block, the ranking, an alias with a particle,
  "ren" not in "current", the caps; the check's drops and merge; the line; the call, an empty answer, a broken reply
  asked again then the fallback, a reply with nothing that holds asked again with why, a reply telling a kept secret
  asked again then the fallback, no model or no setting without a call, the cache and a failure not cached).
  `tests/test_notes.py`: the header, `Ask`'s order, the part first with its fallback, the endpoint with a stand-in
  model on a real canon sync. The whole sidecar suite: 1,678 passed and the two docs-consistency checks failed until `AGENTS.md` named Phase 53 the latest; with that, they and the touched files' tests pass.
- **Plugin.** The form's first toggle is `diverged` and on, `chronicle` and `address` off; the part's line says how many
  lorebook entries were compared and left out; the request's timeout is 600 s (two parts may call a model, each with a
  retry); `notes.changed` removed (the form no longer offers it; `notes.part.changed` stays for an older sidecar or a
  request for `changed` alone). 268 tests with typecheck. Build `25d4fcdd5a1d`; `//@version` unchanged (bumped only at
  releases).
- **Review** (scoped self-review, high risk: canon/provenance, secrets, a model claim in every prompt). Fixed: name
  matching ran one regex per name and entry (a synthetic 200-entry, 425,000-character lorebook with 150 entities took
  1.58 s; by word sets, 0.08 s). Checked: nothing in the packet path changed (the endpoint, `notes` and the new module
  only), so packets are as on `main`; the canon guard (`noteblocks`, `canonfacts.process`) is untouched and its tests
  pass; with secrets off the part reads facts `notes.kept` leaves in, summaries `summaries.held` does not hold, and its
  lines pass `summaries.leaks` at 0.3, else the fallback, which is Phase 50's secret-filtered lines. Remaining: the
  model's `now` is free text (checked for secrets, not for truth; its quote and turns are checked); a two-character
  Korean name that is also a common word can make most entries candidates (ranking and the caps bound it; measured in
  step 5).

## Acceptance criteria

- Every line of the part names a canon text the call was given, quotes words that are in it, and cites turns of the
  input (test, and every line of the measurement).
- With secrets off, no line holds a kept secret at 0.3 (stub tier and the measurement).
- The card, the persona and the note (without NMOS's block) are always in the input; no lorebook text over
  `ENTRY_CHARS`, no input over `CANON_CHARS` + `STORY_CHARS` (test).
- With no model configured, the part is made as Phase 50's Changed from the setting, marked so.
- Making the part twice with nothing changed makes one call; the chronicle and address need no call change.
- A note without a marker hashes and reads exactly as on `main`; packets are byte-identical to `main` for every replayed
  probe.
