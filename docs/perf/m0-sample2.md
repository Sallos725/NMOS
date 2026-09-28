# M0 — a second real chat (sample 2)

M0 so far measured one chat. This one differs from it in character card, persona, prompt, response model, preset and
genre, and each reply ends with a status block the preset writes. Measured 2026-09-28 on `main` at `c0383a6`
(Phase 13 step 2, unchanged read path since Phase 12). Numbers only. The cases are the owner's chat and stay outside
the repository (PHASE-11 Q1). The owner confirmed them as drafted.

## Setup

- **Data.** A restored copy of the owner's production backup of 2026-09-28 in the test Postgres. The chat has
  35 turns (69 messages, about 114k characters). Production had already extracted every turn with the current
  generation (`extract-v13`, gemma4) and summarized turns 0–23, so nothing was extracted again and no model was
  called except for query embeddings.
- **Probe requests.** The chat's recorded requests (2026-09-25) predate migration 0020 and cannot be replayed
  (`audit.replay` → `not_recorded`). Two requests were written into the copy only, both at the chat's last user
  message. They differ only in the prompt window (`in_context`):
  - **A**, the window the preset most likely sent. It is measured on the same card's later chat, whose requests
    show a cut by size and not by count: the prompt held about 102k characters of raw messages. Here that is turns
    4–33.
  - **B**, the last 11 messages, the window measured on the first M0 chat. It tests memory on this chat when little of
    it is in the prompt.
- **Cases.** 15 probes on B: early, cast, past, story, why, relationship, question, item and state. There are 2
  isolation cases on the same card's newer chats, which have another persona. They check that none of this chat's
  names or events reach their packets.
- **Compiled as `main` would today.** `packet-v8`, budget 2000, the current extractor and summarizer generations as
  of now. Vectors are on: the query is embedded with the model production embedded the chat with, and searched in
  the stored projection. The lexical-only run is given for comparison with the first chat's M0, which has no
  vectors.

## Result

Window B, vectors on:

| Category | cases | passed | needing memory: passed | gold held | of it in the prompt | forbidden placed | mean tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| cast | 3 | 1 | 1/3 | 1/4 | 0 | 0/0 | 1800 |
| early | 2 | 0 | 0/2 | 1/3 | 0 | 0/0 | 1691 |
| isolation | 2 | 2 | 0/0 | — | 0 | 0/12 | 254 |
| item | 1 | 1 | 1/1 | 1/1 | 0 | 0/0 | 1714 |
| past | 1 | 1 | 1/1 | 1/1 | 0 | 0/0 | 1668 |
| question | 1 | 1 | 1/1 | 1/1 | 0 | 0/0 | 1680 |
| relationship | 1 | 1 | 1/1 | 1/1 | 0 | 0/0 | 1673 |
| state | 2 | 2 | 1/1 | 2/2 | 1 | 0/4 | 1834 |
| story | 2 | 2 | 2/2 | 3/3 | 0 | 0/0 | 1804 |
| why | 2 | 1 | 0/1 | 2/3 | 1 | 0/0 | 1680 |
| **all** | **17** | **12** | **8/13** | **13/19** | **2** | **0/16** | **1568** |

- **Window B, lexical only:** 8 of 17 pass and 4 of the 13 cases that need memory.
- **Window A:** 17 of 17 pass, and no case needs memory: every answer is already in the prompt. With this preset
  only turns 0–3 lie outside the window at turn 34. At this chat's size (about 3.3k characters a turn) memory starts
  to matter after about 31 turns, and 20 turns outside the window need about 51.
- **The first chat's M0** (same code, lexical only) stays 26 of 28 and 5 of 12.

## What fails

- **A persona narrated in the third person does not bring its own facts (K32).** The user writes the persona by name
  ("…, [persona name] said."). `relevant_facts` counts no persona name as a mention (ADR 0023), and only a
  first-person question adds the persona's facts. The two early cases ask about the persona's own past. Apart from
  the excerpts, both get the same facts, and neither gets the fact that answers it. The same question in the first
  person does.
- **A character called by the given name alone is no mention (K31).** In Korean a character written in full as a
  three-syllable name is usually called by the last two syllables. Three probes asked for one fact each about three
  characters, once with the full name and once with the given name alone. The fact came in 2 of 3 with the full
  name and 0 of 3 with the given name. The owner had joined one of these names to the full name by hand, and it did
  not help.
- **Excerpts land on the status block and the footer lines.** The excerpt of a long message is the two sentences that
  share the most trigrams with the query and the previous reply. That reply ends with the same status block and
  footers, so they often win. Two what-ifs (a monkeypatch, no code change) did not help. Removing them from the
  choice took the result from 8 to 6: the status block holds answers, such as the currency. Choosing by the query
  alone kept 8, with two cases gained and two lost. The first chat's M0 was unchanged in both. Recorded, not fixed.
- **The story cap drops scene summaries.** The one story summary and one scene summary do not both fit in 30 % of
  the budget, so the scene that held the answer was dropped. One story case passed only through an excerpt of a
  status block.

## Threads (K23, Phase 13)

At the head the chat has 11 open threads: 7 goals, 2 threats and 2 promises. Reading the chat, about 9 of them have
already ended in the story, close to the first chat (50 of 59). Four ends were extracted but matched no thread. Two
restate a goal that is already closed. In the other two, someone other than the thread's owner ends it: the one
threatened resolves a threat, and a helper resolves another's goal. Both carry the thread's exact text and name its
owner as the object. On the first chat, 1 of 9 unmatched ends is of this kind (a promise).
