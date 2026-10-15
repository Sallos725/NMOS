# Phase 49 — A translation plugin's markup: memory reads the original text only

Status: **draft**, 2026-10-15 (AGE-79). An owner request, not a roadmap stage. Not approved for implementation.
**Q1–Q4 answered (owner, 2026-10-15): Q1 hidden as far as possible (stricter than recommended), Q2 (a), Q3 (a),
Q4 as recommended.** **Q5 (raised by step 2: the input is Korean, the original English) answered (owner, 2026-10-15): (d), measure
first; step 3 waits for that measurement.** **The recall half measured (2026-10-15): the original only finds 4 of 12
Korean questions, the translation only 12, both (`clean-v3`) 12 ("Q5 measurement" below). Q6 open.**
Approval to implement is a separate decision and has not been given.
**After 1.0.0** (R7; the two quiet weeks on the trial install run from 2026-10-13 to at least 2026-10-27): nothing of
this phase lands on the trial install or in a `0.4.x` release. The owner deferred it past `0.4.0` on 2026-10-10
(`docs/STATUS.md`); the prototype of that time was not adopted.

The owner asked (2026-10-15) for memory to work with a translation plugin that keeps the text the model wrote and
shows a translation beside it. The plugin writes both into the message: the translation, then the original inside an
element of its own, and a button marker after it. Shape (AGE-79; this spec writes the plugin's tag names as
`‹ORIG›` and `‹CTRL/›`; Q1 keeps the real names out of every document):

```
translation ‹ORIG› original ‹/ORIG›‹CTRL/›
```

Memory should read the original only, and nothing of the marker.

**High risk if built** (`AGENTS.md §14`):
- derived text, and through it every generation key that names the normalizer: the embedding, extractor, summary,
  canon and reveal generations re-derive once (S3);
- a change to what memory reads select (recall, excerpts and facts of a tagged message come from the original only);
- deployment compatibility: older normalizers' text is pruned once the new one exists (ADR 0015), so a rollback
  rewrites it and re-embeds (S4).

## Why

1. **Today both texts become memory.** `clean-v3` (`packet.clean_text`) has no rule for this markup; its generic
   tag rule removes the tags and keeps every word. Called on 2026-10-15 with synthetic text:
   `번역문 ‹ORIG› original text ‹/ORIG›‹CTRL/›` → `번역문 original text`. An unclosed element, and any other
   self-closing marker the plugin may write, are stripped the same way. So for a tagged message:
   - extraction reads the story twice, in two wordings, and a translation's own wording (a name spelled differently,
     a mistranslated line) can become a fact of its own or contradict the original's;
   - an excerpt can quote both copies, and spend its length on the duplicate;
   - embedding's 8 × 700-character cap (D21) fills with the duplicate first on a long reply.
2. **One function feeds every reader.** `clean_text` writes `revision_text` (ADR 0006, D21), which lexical recall,
   embedding, extraction, excerpts, summaries, canon and reveals read. The query side calls the same function
   (`retrieval.py`, the request's query and previous reply; `api.py`, the prefetched query embedding). One change to
   it is the whole fix; nothing else needs to know about the plugin.
3. **The markup has never been seen in real data.** The owner's earlier backups hold no tagged message (AGE-79). The
   shape above is the issue's description, not a capture: whether user messages carry it too, which language each
   part is in, and whether the model is sent the original are not known. Step 2 finds out before any code.
4. **The normalizer is part of five generation keys** (`normalizer=normtext.NORMALIZER_VERSION` in `vectors.py`,
   `extraction.py`, `summaries.py`, `canonfacts.py`, `reveals.py`). Any change to `NORMALIZER_VERSION` makes each of
   them a new generation, for every chat, tagged or not (S3).

## Proposal

S1. **`clean-v4`: pick the original first, then clean as `clean-v3` does.** In `packet.clean_text`, on the raw
content and before every `clean-v3` step:
- **A complete element** is the plugin's opening tag (its name only, matched case-insensitively, attributes
  allowed), then text with no opening tag of the same name, then its closing tag (case-insensitive).
- **A message with one or more complete elements, and no other opening or closing tag of that name**, becomes its
  elements' originals, in order, joined by a blank line. Everything outside them (the translation, the markers) is
  dropped.
- **Anything else stays `clean-v3`:** an opening tag without its close, a close without its opening, an element
  inside another, or originals that are all empty. The whole message is then cleaned exactly as `clean-v3` cleans it
  (the tags removed, all text kept). Nothing is guessed: no other tag name, no language detection, no "looks like a
  translation" rule.
- **Then every `clean-v3` step runs on the result**, so an original that holds a reasoning block, HTML, an inline
  image or memory markup is still cleaned.
- **No new marker rule.** The button marker, and any other self-closing marker of the plugin's, already falls to the
  generic tag rule (Why 1).
- **Any role.** The rule follows the markup, not who wrote the message. Step 2 checks what the plugin does to user
  messages; if it wraps them the other way round (what the user typed outside the element), stop and ask.

S2. **Raw stays raw.** `source_revision.content` is never edited (invariants 1, 2); the Inspector's message view
still shows the raw text with both parts. The plugin does not change (`nmos-plugin-stays-light`): the sidecar
normalizes what the plugin already sends.

S3. **Activation and cost.** `NORMALIZER_VERSION = "clean-v4"` makes, once, for every chat:
- **Embedding** (local): every message is embedded again at background priority. No provider cost; on the owner's
  CPU embedder it takes the time a first embedding of the whole ledger takes.
- **Extraction** (paid): each chat's recent window (`NMOS_EXTRACT_BACKFILL`, default 100 turns) is extracted again
  (ADR 0014); older turns keep their earlier facts until **Extract all history**. For scale: on the trial install a
  generation cost about $3.2 for 135 turns on Gemini 3.8 Flash (`PHASE-45.md`), about $0.024 a turn, so about $2.40
  for a chat with 100 or more turns.
- **Summaries, canon and reveals** (paid): a new summary key schedules every chat's whole history, not only the
  recent window (`summaries.schedule_all`: one call per 8 turns and a story call per chat); each chat's canon is
  read again (a few calls per chat); reveals follow the extraction.
- Every chat pays this, though only tagged messages change, because the key cannot tell them apart. Q2 decides when
  it is paid.

S4. **Rollback.** Once every revision has a `clean-v4` row, the `clean-v3` rows are pruned (ADR 0015). Going back to
an image with `clean-v3` rewrites them at startup (`normtext.backfill`) and re-embeds once (local: superseded
vectors are pruned too). What the `clean-v3` generations made with a model is kept (ADR 0015 keeps superseded LLM
extractions), so it is expected to serve again without a paid call; step 3 tests this on a copy, summaries and
canon included.

S5. **What this does not change.**
- **Gating.** A main generation is recognized by the user's latest input in the prompt (ADR 0001, K14). If the plugin
  sends the model a translated input, the request is not recognized and gets no memory at all, whatever this phase
  does (K14: "a preset that sends the input only in transformed form gets no memory"). Step 2 checks it.
- **Which language memory is in.** Facts, excerpts and summaries of a tagged message follow the original's language.
  If that is not the language the user asks in, lexical recall and name matching across the two (one name in two
  scripts) can get worse than `clean-v3`, which kept both. Step 2 records the languages.

## Out of scope

- Any other translation plugin's markup, or a generic "translation" detector.
- Changing gating (K14) to recognize a translated input.
- Translating memory, or the packet, into the user's language.
- Editing raw messages, or showing the Inspector's messages without the translation.
- The per-chat switch for the user's messages (Phase 48).

## Questions for the owner

- **Q1 — the plugin's name in the public repository. Answered (owner, 2026-10-15): hidden as far as possible**
  (stricter than the recommended (a); the options were (a) the tag names in the matcher and its tests, (b) also in
  the changelog, (c) also in this spec).
  - The tag name is written once, as one constant in `packet.py`; no comment or docstring names the plugin.
  - Tests and fixtures build their markup from that constant, never the literal; no test, fixture or file name says it.
  - Every document (this spec, the ADR, `CHANGELOG.md`, `docs/KNOWN-ISSUES.md`, the README, `docs/guide.ko.md`), every
    branch, commit and PR says "a translation plugin (AGE-79)". The plugin's users cannot find the support by its name;
    the owner accepts that.
  - The 2026-10-10 deferral note in `docs/STATUS.md` named the tags; it is reworded in this phase's first PR. Git
    history keeps the old wording (public history is not rewritten).
  - Linear (private) may name the plugin.
- **Q2 — when the re-derivation is paid** (S3; `AGENTS.md §13`: at most one extractor generation per milestone).
  **Answered (owner, 2026-10-15): (a).**
  - (a) **Recommended:** with the next extractor generation after 1.0.0 (Phase 45's `extract-v17`, Phase 48's
    variant or whichever comes first). The re-extraction is paid once for both; summaries and canon are the only
    extra calls (summaries over every chat's whole history). Steps 2–4 can land before it with `NORMALIZER_VERSION` unchanged (nothing re-derives), and `clean-v4`
    joins "Queued for the next extractor generation" in `docs/STATUS.md`.
  - (b) A generation of its own, in the first release after 1.0.0. Every chat pays S3 for this change alone.
  - (c) Only turns whose extraction input changes are queued; every other turn is served by the `clean-v3`
    generation through ADR 0014's fallback. The cost follows the tagged turns only, but every untagged turn shows as
    "served by an older generation" in the Inspector until the next generation, and summaries, canon and embeddings
    still re-derive in full. Not recommended.
- **Q3 — how step 2 sees a real message.** Real tagged messages have never been checked (Why 3). **Answered (owner,
  2026-10-15): (a); the owner offered to run it.**
  - (a) **Recommended:** the owner opens one chat with the plugin on, sends one message and reports its shape only:
    the tag names and attributes, their order, the markers, whether the user's message is wrapped too, which language
    each part is in, and whether that request got memory (the Inspector's request list, K14). No chat content leaves
    the owner's machine; the fixtures rebuild the shape with invented text.
  - (b) An agent installs the plugin in the isolated PocketRisu harness (not the trial install during the quiet
    weeks, not production). The plugin's own translation calls need its provider and key, which are the owner's.
- **Q4 — the gate.** `AGENTS.md §7.6` asks a generation-key change for the full live gate, but no gate chat has a
  tagged message, so the gate cannot see what this phase changes. **Answered (owner, 2026-10-15): as recommended,
  the zero-call byte-identity check and the bundled generation's full live gate.**
  - **Recommended:** under Q2 (a), the bundled generation's full live gate covers the re-extraction, and this phase
    adds a zero-call check that is decisive for every other message: on the gate databases' copies and a copy of the
    trial install, `clean-v4` equals `clean-v3` byte for byte for every revision without the markup. Under Q2 (b) or
    (c), that check, the synthetic stub tests of step 3 and one paid run on a synthetic tagged chat (estimated and
    approved first) replace the full live gate.

- **Q5 — which text of a tagged reply memory reads, when the input is in the translation's language** (raised by
  step 2). **Answered (owner, 2026-10-15): (d), as recommended.** The comparison runs once the owner's tagged chat
  has about 30 tagged turns (counted read-only on the trial install); its estimate is approved again before the run.
  Under `clean-v3` a turn holds the Korean input, the Korean translation and the English original.
  - (a) The original only, as S1. The text the model wrote, without a translation's losses, and half the extraction
    input of a tagged turn. But the input, the recall query and the names typed are Korean: the lexical and keyword
    routes and name matching meet English memory (one name in two scripts), and only the vector route crosses
    languages.
  - (b) The translation only. Memory in the input's language; but it reads a machine translation (units converted,
    details smoothed), and the model, which wrote the original, gets memory in another language.
  - (c) Both, as now. Nothing changes (the marker is already dropped): every route matches either language; a tagged
    turn costs about twice the extraction input, and a translation's wording can become a fact of its own.
  - (d) **Recommended: measure before choosing.** No argument settles (a)–(c); the losses are in recall, which only a
    measurement shows. Once the owner's tagged chat has about 30 tagged turns: a private copy, the same turns extracted
    under (a), (b) and (c) (each a normalizer variant on the copy only), and a few Korean questions the owner writes
    about them, scored for recall. About 90 extractions at about $0.024, about $2–3, estimated again and approved
    before the run. The answer decides S1; if it is (c), this phase closes with nothing to build.
- **Q6 — after the recall half** (raised by the Q5 measurement: (a) 4 / 12, (b) 12 / 12, (c) 12 / 12).
  - (a) **Recommended:** close the phase as (c). `clean-v3` stays: it already drops the button marker, recalls best
    for Korean questions, and needs no new generation, re-extraction or re-embedding for anyone. The cost it keeps is
    that a tagged turn's extraction reads both texts (about twice the input on those turns, under a cent each on the
    trial host's model). AGE-79 is closed with this measurement as its answer.
  - (b) Run the extraction half for (b) against (c) first: the 48 tagged turns extracted once under each on a copy,
    their facts compared (count, duplicates, contradictions, Korean and English names), about $2, its estimate approved
    again before the run. Worth it only if the doubled extraction input matters, or translation-only facts might be
    cleaner.
  - Dropped: (a) original only, the draft's S1.

## Steps

1. This spec, and the owner's answers.
2. **The real shape** (Q3), before any code. Record the shape only (no content): tag names, attributes, order,
   markers, user messages, languages, whether the request got memory. If it differs from S1, amend this spec and ask
   again.
3. **`clean-v4` behind the version, not active** (after Q5's measurement decides which text it keeps). The rule in `clean_text` under a new version name, with
   `NORMALIZER_VERSION` still `clean-v3` (no key changes, nothing re-derives), and tests with synthetic text:
   - one element; several; attributes; the tag name in other cases; markers only; markers between elements;
   - an unclosed opening, a stray close, a nested element, empty originals: each equal to `clean-v3`;
   - an original holding a reasoning block, HTML, an inline image and memory markup: each cleaned;
   - a message without the markup: equal to `clean-v3`;
   - with the stub extractor, a tagged reply's facts quote the original only, an excerpt comes from the original
     only, and a query with the markup is normalized the same way;
   - rollback (S4) on a copy: back to `clean-v3`, its text rewritten, its extractions served without a call.
4. **Measurement** (zero calls).
   - The byte-identity check of Q4 on the copies: the count of revisions, the count with the markup (expected 0), and
     the count whose text differs (must be 0 outside the markup). Numbers only.
   - The cost of `clean_text` on the copies' longest messages, against `clean-v3`.
5. **Activation** (Q2) and docs: `NORMALIZER_VERSION = "clean-v4"` with the generation Q2 names; an ADR (next free
   number); `CHANGELOG.md`'s upgrade note with S3's cost; `docs/KNOWN-ISSUES.md` (S5: gating and language);
   the README and `docs/guide.ko.md`; `docs/STATUS.md`.

## Step 2 evidence (2026-10-15)

One reply captured by the owner, then one new chat on the trial install with NMOS on (two inputs, each reply
translated before the next input), read there read-only. Shape and counts only; no content enters the repository.

```
{translation}
‹ORIG›
{original}
‹/ORIG›
‹CTRL/›
```

- One element per reply; the opening tag has no attributes and is spelled as in AGE-79; the close follows the
  original on its own line; the button marker follows the close on its own line.
- **The original is English and the translation Korean.** Both parts hold the same markdown headings and the same
  inline image tags; `clean-v3` removes the image tags and keeps both parts (checked on a synthetic rebuild of the
  shape, 2026-10-15).
- The shape matches S1.
- **The input is not translated** (the plugin does not support it, owner). Both inputs were typed in Korean and stored
  unwrapped; the owner sometimes types in English.
- **Gating is not affected (K14).** Both requests were recognized and retrieved (`retrieval_trace`: fresh, every route
  run); the packets were empty only because the chat was new.
- **The ledger holds the reply as translated.** The reply was first observed at the next request, after the
  translation ran, so it is one revision with the element (open, close and marker in the expected order, the tag
  spelled as in AGE-79). A reply translated after the next request would arrive as an edit of that reply (K3), and its
  turn would be extracted again.
- **The language stop condition applies.** A turn is a Korean input and an English original; the translation is the
  only Korean of the reply. `clean-v4` would make the reply's memory English while the input, the recall query and
  the names the owner types stay Korean. Q5.

## Q5 measurement: the recall half (2026-10-15)

Numbers only; the chat, the questions and the answers stay on the owner's machine.

- **The chat.** The owner's tagged chat was filled from 14 to 50 turns on an isolated clone of the trial host (its own
  PocketRisu and sidecar, a restored copy of the trial database; the trial install untouched), with the owner's preset,
  toggles, modules, model bindings and persona. Turns 15–50 were written by a model playing the persona, one input in
  three in English, as the owner's own inputs are mixed (9 Korean, 5 English). 49 of 50 replies carry the element.
  Cost about $4.8 (owner-approved cap $16).
- **The arms.** Three copies of the database after turn 50. In two, the normalized text of the 48 tagged replies was
  replaced by `clean_text` of (a) the original only or (b) the translation only, and those replies embedded again with
  the trial host's embedding model (under $0.05); (c) is `clean-v3` as it stands (both). Facts are the same in every
  arm (extracted from `clean-v3`): this half measures recall routes only.
- **The probes.** 12 Korean questions about facts stated in turns 7–43 (5 names, 3 promises, 2 places, 1 number,
  1 object; 3 of them first stated in an input), drafted from the transcript and approved by the owner. Each replays the
  last request (`audit.replay`, probe in place of the message, `packet-v19`) three times per arm.
- **The context.** The preset's 150k context holds the whole 50-turn chat, so every message was in the prompt and no
  arm placed any excerpt. The replay therefore keeps only the last 12 messages in context (a long chat whose early turns
  fell out), the case memory is for.
- **Scored.** "Found": a placed excerpt or quote from the answer's turn (majority of three; all three rounds agreed in
  every case). "With the answer": the answer's words (Korean or English) in a placed excerpt.

| Arm | Found | With the answer | Packet (mean) |
|---|---|---|---|
| (a) original only | 4 / 12 | 2 / 12 | 2.3k tokens |
| (b) translation only | 12 / 12 | 6 / 12 | 3.2k tokens |
| (c) both (`clean-v3`) | 12 / 12 | 8 / 12 | 2.8k tokens |

- (a) misses 8 of 12. Two of its 4 are questions whose answer is in a Korean input, which no arm changes. The vector
  route, the only one that crosses languages, did not make up the difference.
- (b) finds every turn but holds the answer less often than (c): where the translation spells a name differently from
  turn to turn, the English original in (c) still carries it.
- **Reading:** for an owner who asks in Korean, S1 as drafted (the original only) makes recall worse, the outcome the
  language stop condition named. (c), which is `clean-v3` today and already drops the button marker, recalls best.
- **Limits:** one chat, one simulated context size, 12 questions; English questions not measured; the extraction half
  (what facts each arm yields) not run. Q6.

## Acceptance criteria

1. For every revision without the markup on the copies, `clean-v4` equals `clean-v3` byte for byte.
2. Every case of step 3 holds; an incomplete or nested element never drops a word `clean-v3` keeps.
3. No raw message changes; the Inspector's raw view is unchanged.
4. With the stub extractor, no fact, excerpt or embedded chunk of a tagged message holds text from outside its
   original elements.
5. Ingest of a message costs at most +1 ms p50 over `clean-v3` on the copies' longest messages.
6. Step 2's real shape matches S1, or the spec is amended and answered again before step 3.
7. A rollback to `clean-v3` on a copy keeps every extraction and needs no provider call.

## Stop conditions

- Any revision without the markup changes text. Stop and diagnose.
- The real shape differs from S1 (other tag names, the original outside the element, user messages wrapped the other
  way round). Stop, amend, ask.
- A request with the plugin on gets no memory (K14). This phase cannot fix that; stop and report.
- The original is not in the language the user asks in. Stop and ask before step 3: `clean-v4` may then recall worse
  than `clean-v3`.
- A paid run passes its approved estimate by more than half. Stop and report.

## Evidence rules

The repository is public. Tests and fixtures use invented text in the plugin's shape only; no chat content, captured
or paraphrased. Step 2 reports a shape, never a message. Measurements on copies of the owner's data report numbers
only. No other memory plugin is named or cited.
