# 0045 — Canon sources: what the host shows a chat, kept as immutable revisions

Status: accepted, 2026-09-28 (revised the same day after the step's Codex review: manifests). Phase 14 step 3 (`docs/phases/PHASE-14.md`, Q1, Q2; host evidence H19,
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
   - Each version of the text is an immutable `source_revision` (invariant 1) under the hash of its normalized text.
   - Keys:
     - `card:name`, `card:desc`, `card:personality`, `card:scenario` and `card:greeting` (the greeting the chat started
       from);
     - `note`;
     - `persona` (the chat's persona: the bound one, else the selected one);
     - `lore:<id>` for each lorebook entry with content. An entry without a usable id is keyed by a hash of its
       comment, keys and mode, so an edit of its text keeps the key. A key the chat has twice gets `~n` (never in an
       id). Folders are structure, not canon.
   - The card's instructions, example messages and assets are not canon (Q1). A text over 1,900,000 characters is not
     kept (the sidecar takes up to 2,000,000 per text).
2. **Manifests.**
   - A manifest is the chat's canon at one time: each key with its text's hash and what it is (scope, mode, keys,
     comment; the metadata).
   - Its id is SHA-256 of its canonical JSON in key order. Plugin and sidecar compute it alike
     (`fixtures/unit/canon-manifest-v1.json`).
   - Metadata lives in the manifest, not in the immutable text, so an entry whose keys or mode changed with the same
     text makes a new manifest.
   - The conversation's canon is the manifest last applied (`canon_applied` keeps the order). A sync observed
     earlier than the one in force is stored but not applied, so a late upload never brings old canon back.
3. **A request replays with its canon.** The plugin sends the id of the manifest its prompt was built with and the
   keys of the canon the prompt holds (`canon_manifest_id`, `canon_held`), and the request records both
   (migration 0025). The texts may reach the sidecar after the request: the replay resolves them by key and hash
   (ADR 0027).
4. **Sync.**
   - `POST /v1/sync/canon` takes the manifest, the time the plugin read it, and the texts the sidecar asked for,
     verified against their hashes. It answers the hashes it still needs. A manifest that names a key twice is
     refused.
   - Only an existing conversation takes canon. The message sync creates it.
   - The plugin uploads in the background after a request, cached packet or not, when the sidecar's conversation
     lacks the manifest. It waits until the card is known and sends one upload per chat at a time, the newest
     observation waiting.
   - Texts go in batches of up to 800,000 characters (a longer text goes alone), since a lorebook can hold 400,000
     and more (`docs/perf/canon.md`).
   - What was sent is remembered per sidecar conversation, so a chat deleted and synced again gets its canon again.
   - A failed lorebook read sends nothing (never an empty lorebook).
   - An older sidecar answers 404 once, and the plugin then stops for the session.
5. **The card is read off the request path** (H19), with the bot's name, which the plugin already read that way:
   - every 10 minutes;
   - at once when the card's description, which the host puts in every prompt, is no longer in it (an edit).

   The lorebooks are read on the request path (about 1 ms). Texts are hashed once and remembered. The note and local
   entries come with the chat, and the persona's prompt with the personas the plugin already reads in the
   background.
6. **No pipeline but canon's own sees it.** Canon is never a head member: extraction, embeddings, excerpts and the
   status-window state do not read it. A state rebuild now reads messages only. The packet does not change (Q5).
7. **Inspector.** A folded "Canon" section per chat shows, for each text in force:
   - what it is;
   - its length, how many versions the chat has seen, and since when it is in force;
   - how many requests' prompts held it, and the last one;
   - the start of its text, or that the text has not arrived yet.
8. **Lifecycle.** Deleting a chat deletes its canon, manifests and their order (ADR 0009). A rebuild keeps them:
   canon is source, not derived.

The step's Codex review found eight defects, all confirmed and fixed before merge, with tests:
- a request recorded keys only, so a replay could show the canon from before the prompt's own;
- a late upload could bring old canon back;
- a failed lorebook read ended every entry;
- metadata-only edits were lost;
- a repeated key's suffix could collide with a host id;
- a cached packet skipped canon;
- a chat deleted and synced again got no canon;
- a first text could exceed the batch size.

The Copilot review of the pull request found five more, all fixed with tests:
- a text is kept as the host has it (only its hash is normalized), not trimmed;
- a lone surrogate hashes as U+FFFD, as the browser's encoder does (ADR 0029);
- a host without the lorebook call, or without a list, gives no canon observation at all;
- a message whose id happens to be a canon id is never taken as canon;
- the newest observation holds from the time its manifest arrives, before its texts do.

## Consequences

- A chat's canon is kept as the host showed it to that chat, with its history, and a request replays with its
  canon.
- The plugin's work on the request path grows by one lorebook read and a text search of the prompt. The card read
  stays off it.
- Canon is per conversation: a card shared by several chats is kept once per chat.
- A card edit is noticed at the next request, or within 10 minutes when the prompt did not show the change. The plugin
  waits for the card before its first canon sync, so a chat's first request records the lorebook keys it held but no
  manifest.
- Two tabs of one chat observe canon on their own clocks; the later observation wins.
