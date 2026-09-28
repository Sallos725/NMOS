# 0045 — Canon sources: what the host shows a chat, kept as immutable revisions

Status: accepted, 2026-09-28. Phase 14 step 3 (`docs/phases/PHASE-14.md`, Q1, Q2; host evidence H19,
`docs/HOST-FACTS.md` "Canon sources"). Migration 0025. Names from canon follow in step 4, and canon facts, conflicts
and the lock in step 5, under the same capture.

## Context

The character card, the lorebooks, the persona and the author's note set up the story before its first message,
and the host sends them with every request (its activated entries only). NMOS kept none of it: a given name the
lorebook lists was no mention (K31), and nothing held the story's starting state or noticed a story drifting from
it.

H19 showed what the plugin can read on PocketRisu v1.13.0:
- every lorebook entry the host shows the chat, in about 1 ms;
- the chat's author's note and local entries, with the chat read NMOS already does;
- the persona's prompt, behind the permission the persona's name already has;
- the card, but reading it clones the current chat (82–93 ms at 10,000 messages).

An entry's text is in the outgoing prompt exactly when the host activated it.

## Decision

1. **Canon is source.**
   - Each canon text of a conversation is a `source_object` of kind `canon`, with host logical id `canon:<key>`.
   - Each version of the text is an immutable `source_revision` (invariant 1) under the hash of its normalized text,
     with what it is in its metadata.
   - Keys:
     - `card:name`, `card:desc`, `card:personality`, `card:scenario` and `card:greeting` (the greeting the chat started
       from);
     - `note`;
     - `persona` (the chat's persona: the bound one, else the selected one);
     - `lore:<id>` for each lorebook entry with content. An entry without a usable id is keyed by a hash of its
       comment, keys and mode, so an edit of its text keeps the key. Folders are structure, not canon.
   - The card's instructions, example messages and assets are not canon (Q1).
2. **In force, over time.** `canon_state` records which revision of each key is in force from when. A sync makes the
   plugin's manifest the canon in force: a changed or missing key closes its row and a new one opens. The history
   stays, and a read as of an earlier time sees the canon of that time (ADR 0027). Nothing changes until the sidecar
   has every text the manifest names.
3. **Sync.**
   - `POST /v1/sync/canon` takes the manifest (key, hash, metadata) and the texts the sidecar asked for, verified
     against their hashes, and answers the hashes it still needs.
   - Only an existing conversation takes canon. The message sync creates it.
   - The plugin calls it in the background after a request, when the manifest changed since the sidecar last had it,
     and only once the card is known. The texts go in batches of up to 800,000 characters, since a lorebook can hold
     400,000 and more (`docs/perf/canon.md`).
   - An older sidecar answers 404 once; the plugin then stops for the session.
4. **The card is read off the request path** (H19), with the bot's name, which the plugin already read that way:
   - every 10 minutes;
   - at once when the card's description, which the host puts in every prompt, is no longer in it (an edit).

   The lorebooks are read on the request path (about 1 ms). The note and local entries come with the chat, and the
   persona's prompt with the personas the plugin already reads in the background.
5. **What a prompt held.** The plugin sends the keys of the canon whose text the outgoing prompt holds with the
   request (`canon_held`); the request records them (migration 0025). They say which lorebook entries the story used
   and when, for step 5 (Q3) and the Inspector.
6. **No pipeline but canon's own sees it.** Canon is never a head member: extraction, embeddings, excerpts and the
   status-window state do not read it. A state rebuild now reads messages only. The packet does not change (Q5).
7. **Inspector.** A folded "Canon" section per chat shows, for each text in force:
   - what it is (source, scope, mode, keys);
   - its length, its versions and since when it is in force;
   - how many requests' prompts held it, and the last one;
   - the start of its text.
8. **Lifecycle.** Deleting a chat deletes its canon and its states (ADR 0009). A rebuild keeps them: canon is
   source, not derived.

## Consequences

- A chat's canon is kept as the host showed it to that chat, with its history, and a request replays with its
  canon.
- The plugin's work on the request path grows by one lorebook read and a text search of the prompt. The card read
  stays off it.
- Canon is per conversation: a card shared by several chats is kept once per chat.
- A card edit is noticed at the next request, or within 10 minutes when the prompt did not show the change. The
  canon sent before the card was first read has no scope for its entries, so the plugin waits for the card before
  its first canon sync.
