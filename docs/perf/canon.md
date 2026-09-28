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
