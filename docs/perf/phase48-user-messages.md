# Phase 48 — how much of memory comes from the user's messages (step 4, read only)

2026-10-15. PHASE-48 step 4, first bullet: the size of what the replies-only switch would drop, measured before any
code. Numbers only; no chat content.

## Setup

- Database: the trial install's database (`nmos_p32_try` on the test Postgres), read in a read-only transaction
  (`default_transaction_read_only=on`). Nothing was written; the install was not touched (the 1.0 quiet weeks).
- Extractor: the active generation (`extract-v16`, `google/gemini-3.8-flash`). Every served turn of the 10 chats'
  heads is extracted by it, so no turn was served by an older generation.
- Classification: each served fact's `evidence` against its turn's members by role, with the extractor's own test
  (`threads.similarity` ≥ `EVIDENCE_MIN` 0.7 on what the model saw, `TARGET_CHARS` per message). "User only" is what
  the switch's evidence rule (S3) would refuse.
- Recall: every recorded request with excerpts (`retrieval_trace.selected`), each excerpt's revision by role.

## Facts

632 facts on 146 turns of 10 chats; every turn has a user message.

| Evidence found in | Facts | Share |
|---|---:|---:|
| the reply only | 618 | 97.8 % |
| both the reply and the user's message | 5 | 0.8 % |
| neither (paraphrased past the threshold) | 5 | 0.8 % |
| **the user's message only** | **4** | **0.6 %** |

The four are one each of `located_in`, `addresses`, `world_fact` and `identity`. The five in both stay (the reply
says it too). The five in neither are a paraphrase; under the switch the evidence check decides them against the reply.

## Recall

109 recorded requests carried excerpts: **817 excerpts, 210 of them (26 %) from user messages; 88 of the 109
requests (81 %) had at least one.**

## What it means for the phase

- **The read side carries most of the effect.** On this data the switch changes about a quarter of the excerpts and
  four in five packets that have excerpts, and well under 1 % of facts. Step 2 (recall) is where the switch shows.
- **Extraction already rarely records a fact from the user's message alone** (4 of 632). The extraction side
  (step 3) still matters for the chats the switch is for, but this sample may not be such a chat: whether these chats
  are full impersonation was not checked (that would mean reading content). The paid run (Q5) should use a chat the
  owner names as full impersonation, and repeat this count on it first.

## Cost basis for the paid run (Q5)

The active generation's 205 extractions with usage recorded average **11,772 input, 1,179 output and 1,807 reasoning
tokens per turn** (input p90 13,307). A recent window of 100 turns is about 1.18 M input and 0.30 M output plus
reasoning tokens per arm; Q3's comparison doubles it. Q3 (b) also leaves the user's message out of the input, so its
arm costs less. The price is taken from the provider at the time of the run and approved before it, as Q5 says.

## Method, to repeat it

A one-off read-only script, not kept in the repository: served facts are the assertions of non-discarded extractions
of the active generation whose anchor is on a chat's head (`extraction.members` gives the turn's messages); texts are
`revision_text.clean_content` (`clean-v3`); roles are `source_revision.metadata->>'role'`; the test is
`nmos_sidecar.threads.similarity(evidence, text) >= nmos_sidecar.extraction.EVIDENCE_MIN`. Excerpts are
`retrieval_trace.selected[].revision_id` joined to the revision's role.
