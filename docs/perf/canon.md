# Canon sources — measurements (Phase 14, Stage 6 part 2)

Phase 14 (`docs/phases/PHASE-14.md`) makes the character card, the lorebooks, the persona and the author's note
sources of each chat. This file records what they look like on the owner's data and what they cost. Numbers only:
the canon itself is the owner's and stays outside the repository.

## The canon of the two measured chats (step 2, 2026-09-28)

A count-only inventory with the owner's OK (PHASE-14 Q8). The owner's PocketRisu database was opened read-only
(SQLite `mode=ro`, one key: `database/database.bin`, decoded in memory), and the characters of the two measured chats
were found by their host chat ids. The script (`~/nmos-eval/phase14-canon/inventory.py`, outside the repository) prints
numbers only.

| | Longest chat (74 turns) | Sample 2 (35 turns, `docs/perf/m0-sample2.md`) |
|---|---:|---:|
| Card: description | 2,880 chars | 6,456 chars |
| Card: greeting (alternates) | 1,272 chars (0) | 3,312 chars (9) |
| Card: personality, scenario, example messages, instructions | empty | empty |
| Character lorebook | 10 entries (6 `normal`, 4 `folder`), 9 always active, 4 keys, 37k chars | **124 entries** (112 `normal`, 12 `folder`), 36 always active, 334 keys, **372k chars** |
| Chat lorebook | 2 entries, no keys, none always active, 128k chars | none |
| Module lorebooks (enabled) | none | 41 entries, 9 always active, 67 keys, 64k chars |
| Persona prompt (bound) | 15.6k chars | 7.5k chars |
| Author's note | empty | empty |

Names (the character names NMOS extracted for each chat, against the lorebook keys):

| | Longest chat | Sample 2 |
|---|---:|---:|
| Character names NMOS knows | 9 | 20 |
| … that are a lorebook key | 0 | 7 |
| … three-syllable names whose two-syllable given name is a key (K31) | 0 | **6** |
| Entries naming exactly one known character, and the aliases they add | 0, 0 | 9, 23 |
| Entries naming two or more known characters (joined by nothing, Q6) | 0 | 2 |

What it means for the spec:

- **Names.** Lorebook keys would make six characters' given names mentions on sample 2 (K31) without a model
  call. They do nothing for the longest chat, whose few keys are not names.
- **Cost.** Reading every entry once would take 165 calls on sample 2, over 435k characters. Reading only what a
  prompt held (Q3) starts with its 45 always-active entries, then adds an entry the first time the story names it.
  The longest chat's chat lorebook (128k characters, no keys, not always active) never reaches a prompt, so it is
  never read.
- **Duplication.** Everything above except the unused entries is in every prompt already, so NMOS still sends none of
  it (D3, Q5).

## The host's cost at request time (step 2)

On PocketRisu v1.13.0 (`docs/HOST-FACTS.md`, "Canon sources"; H19):

| Call | Synthetic chat (7 messages) | 10,000 messages |
|---|---:|---:|
| `getCharacter()` (the card; clones the current chat) | 0.6–4.1 ms | **82–93 ms** |
| `getChatFromIndex()` (note, local lorebook; NMOS already reads it) | 0.3–3 ms | 80–83 ms |
| `getCurrentLorebookEntries()` | 0.3–1.6 ms | 0.8–2.3 ms |
| `getDatabase(personas, modules)` | 0.2 ms (93 ms with the first permission dialog) | 0.8–1.1 ms |

The card is therefore read off the request path (step 3). The rest is read with each request's sync.

## Names from canon (step 4)

Sample 2's canon, built from the owner's database the way the plugin sends it (153 texts: card fields, the greeting,
the persona, and 149 lorebook entries, 108 with keys), stored in the evaluation copy with this step's code. The
given-name probes of `docs/perf/m0-sample2.md`: three questions, each asking one fact about a character, once with the
full name and once with the given name alone.

| | Full name | Given name alone |
|---|---:|---:|
| Before (no canon) | 2 of 3 | 0 of 3 |
| With the chat's canon | 2 of 3 | **2 of 3** |

The one character whose fact the given name still does not bring is not reached with the full name either, so
it is not a naming problem. The chat's 17 M0
cases are unchanged: 8 of 17 lexical only (4 of 13 that need memory), 12 of 17 with vectors (8 of 13), nothing
forbidden placed.


## Evaluation (step 6, 2026-09-29)

### Setup

Copies of the two measured chats' evaluation databases (Phase 13's, with the owner's repairs applied), migrated to
0026, with each chat's canon built from the owner's PocketRisu database and stored as the plugin sends it. The probe
requests predate canon, so the keys their prompt held were simulated as the host activates canon: the card's
description and the persona in every prompt; a lorebook entry when always active, or when one of its keys (and a
second key, for a selective entry) is in the last messages the host scans (5 on the longest chat, 10 on sample 2); the
greeting only when it is a message of the window. The canon generation then read what a prompt held, with the
extraction model the owner uses (`gemma4:31b-cloud`, through the local Ollama), and no other job ran. The scripts are
outside the repository (`~/nmos-eval/phase14-step6/`). M0 and the secret gate were run with and without canon facts on
the same copies and code (`tools/eval_rp.py --canon`, `tools/eval_secret_gate.py --canon`).

### Model calls

| | Canon texts | Read (held by a prompt, or always read) | Model calls | Facts (valid) | Time |
|---|---:|---:|---:|---:|---:|
| Longest chat | 12 | 8 | 12 | 118 | 66 s |
| Sample 2 | 153 | 62 | 66 | 323 | 188 s |
| Production (one chat, since the owner installed the plugin; counts only) | 156 | 22 | 26 | 257 | ≈1 min |

Sample 2 read what step 2 predicted: the card, the greeting, the persona, its 45 always-active entries and the 14
entries the probe's scanned messages name. No call failed. The persona's 15.6k characters on the longest chat took 3
calls. Half of sample 2's texts gave no fact (a text of names and numbers, a folder's note); the others about ten each.

### Memory

| | Without canon facts | With canon facts |
|---|---:|---:|
| Longest chat, M0 28 cases | 27 (8 of 9 needing memory) | 27 (8 of 9), the same cases |
| Longest chat, M0 12 cases | 5 of 12 | 5 of 12, the same cases |
| Longest chat, secret gate | 6 of 6 | 6 of 6 |
| Sample 2, M0 17 cases, lexical | 8 (4 of 13) | 8 (4 of 13), the same cases |
| Sample 2, M0 17 cases, with vectors | 12 (8 of 13) | 12 (8 of 13), the same cases |
| Forbidden phrases placed | 0 | 0 |
| Given-name probes (K31), sample 2 | given name finds what the full name finds | the same |

No category is worse. Canon facts changed no case, as Q5 expected: the host sends the card, the persona and the entries
it activates, and NMOS does not send a canon fact whose text the prompt held (D3). On the longest chat 23 canon lines
reached 21 of its 40 packets (+9 tokens a packet on average), all from the greeting, the one canon text the prompt no
longer held at turn 73. On sample 2 3 canon lines reached 1 of 17 packets. 105 of the longest chat's 118 canon facts,
and 296 of sample 2's 323, are still current at the probe; the story superseded the rest.

### Conflicts

With `identity` and `relationship` listed (ADR 0047 as step 5 had it), 10 canon conflicts were listed: 8 on sample 2
and 2 on the longest chat, and about one was a contradiction. Sample 2's lorebook and persona are in English, so their
facts are, and the story's Korean statement of the same identity read as another one (6). `identity` holds one value,
so a job and where someone lives replaced each other (2). No
relationship was listed. The owner decided to list relationships only (ADR 0047 amendment 1): none is listed on either
chat now. Telling a new identity from the same one in other words needs a model and is left for later.

### Latency (`tools/bench_story.py`, 10,000 messages)

Retrieve p50, the median of five rounds, each round running Phase 13 `main` (fea5967), this step without canon, with
a 50-entry lorebook and with a 200-entry lorebook in turn, pinned to two cores, nothing else running. The canon is the
card, the persona and the lorebook, every text read, about five facts a text (as sample 2's reads), each entry about
its own subject; each request holds the card, the persona and a quarter of the entries (`BENCH_CANON=N`).

| | Canon facts | retrieve p50, ms | against Phase 13 `main` |
|---|---:|---:|---:|
| Phase 13 `main` | — | 120.3 | |
| Phase 14, no canon | — | 123.5 | +3.2 |
| Phase 14, 50 entries | 260 | 133.7 | +13.4 |
| Phase 14, 200 entries | 1,010 | 154.0 | **+33.7** |

The criterion (+5 ms with 200 entries) is missed. The owner accepted it (2026-09-29, K36) after the one low-risk fix:
- A canon fact costs what a story fact costs: every read folds it with the story's (≈15 µs a fact). 1,010 canon facts
  cost about what the facts of 2,000 more messages would.
- The canon-facts query's planning (≈4.7 ms) took longer than its run (≈1.6 ms with 260 facts); it is now prepared
  once per connection. A run before that fix gave +35.4 ms at 200 entries, so it saves one or two milliseconds of a
  request's median here, and the planning of every later request on the same connection.
- What the owner's chats read is closer to the 50-entry row: 118–323 canon facts (22–62 texts).

### Upgrade and real host

- **Upgrade.** A database written by Phase 13 `main` (fea5967, `fixtures/upgrade/main-phase13.sql`) upgrades to 0026,
  takes a canon on an upgraded chat, reads the card once, and the story supersedes its place; every earlier fixture
  does the same (`tests/test_upgrade.py`, 6 fixtures).
- **Real host** (an isolated PocketRisu v1.13.0, stub models, 2026-09-29), each step passed:
  1. the card was captured and read after the first request whose card read finished (the card is read after a request,
     off its path);
  2. an edit of the card's description made a second revision and manifest, the first kept, and was read once;
  3. a story line making the card's sister a rival was listed in "Needs attention" with Lock and Retract;
  4. after Lock, the next packet carried the canon's relationship marked `source="canon" locked="true"` and not the
     story's, also with a short-window preset where the story's line was outside the prompt (without the lock it was
     sent);
  5. after Undo, the story's relationship was sent again, with canon's as its earlier version.

  It found one display bug, fixed in this step: the Inspector marked every canon fact "older generation" (it compared
  the canon generation with the extraction generation).
