# Phase 57 step 5 — what a model change and a second chat cost, before and after

Measured 2026-11-08 on a throwaway copy (`pg_dump` into a database of its own on the test PG :5436) of the test
install's database: 18 conversations, 12 of them with canon in force. No model was called and nothing was written to
the test install. Scripts: the counts below come from the sidecar's own functions on the copy (`canonfacts.input_of`
over every text in force; `POST /v1/config/preview` with the model renamed; `summaries.windows` per chat).

## A3 — what changing the extraction model queues

| | facts (turns) | summary windows | canon texts | all |
|---|---:|---:|---:|---:|
| before Phase 57 (every model change) | 232 | 22 | 304 | 558 |
| carry on (the default) | 0 | 0 | 0 | 0 |
| redo the latest 100 turns | 232 | 22 | 0 | 254 |
| carry on, read the setting again | 0 | 0 | 304 | 304 |

"Before" is what the activation queued until now: the latest `extract_backfill` (100) turns of every chat, every due
summary window of every chat and every chat's canon in force. On this copy the chats are short, so "the latest 100
turns" is every complete turn and every window; on a long chat the summaries' share grows with its length. A restart of
the sidecar on the copy with no generation change queued nothing.

## A1 — canon parts a second chat of the same bot would copy

Of the 416 parts every chat's canon in force sends the model (texts of at least `MIN_CHARS`), 243 inputs are distinct:
**173 parts (41.6 %) would be copied** instead of read, by A1's fingerprint (the source line, the part, its text, and
the names only for texts that use the name macros).

| revisions sharing one input | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|
| inputs | 141 | 54 | 25 | 23 |

This is an estimate: the fingerprints were computed now, from today's normalized text and names, because reads made
before migration `0033` recorded no input (ADR 0079 item 3). After the upgrade the first chat of a bot reads its canon
once more, and the chats after it copy what it read.

## Not measured

- A live model run: the change adds no prompt and no call, and the owner's no-spending rule holds (`nmos-api-spend`).
- The panel on the test install (6131/6113): the owner's check, after deployment there.
