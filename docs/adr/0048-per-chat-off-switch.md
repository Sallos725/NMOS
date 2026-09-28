# 0048 — NMOS off for one chat

Status: accepted, 2026-09-28. Owner request outside the Phase 14 steps (not a phase feature: no migration, no
extractor generation, no packet policy). Plugin only; a new plugin build.

## Context

NMOS has one switch, the plugin arg `disabled`, for every chat at once. The owner wants to leave some chats out
(a throwaway test, a chat not worth remembering, one they do not want sent to the sidecar) without deleting what NMOS
already keeps of them (ADR 0009 deletes it) and without turning NMOS off everywhere. The switch should be quick to
reach, and the panel should also open from the sidebar's ☰ menu, not only from the chat input's.

Three meanings were offered: everything off, injection only, extraction only. The owner chose everything off, kept
in the plugin (2026-09-28).

## Decision

1. **Kept in the plugin.** A string plugin arg, `disabled_chats`, holds the host chat ids NMOS is off for (separated
   by spaces). PocketRisu stores plugin args with the plugin (`realArg`) and keeps an arg of the same type when the
   plugin is updated (v1.13.0 `plugins.svelte.ts`). It works for a chat the sidecar has never seen (D22), and nothing
   is stored in the host's chat data (the plugin never mutates it, §2).
2. **Everything off.** After the host chat is read, a chat on the list returns the prompt untouched: no manifest, no
   sync, no canon read or upload, no card read, no retrieve. The output listener sends nothing for it. What the
   sidecar already keeps of the chat stays as it is (invariant 1); the Inspector still shows it.
3. **Back on.** Taken off the list, the chat's next main generation syncs as any other: the commits since are one
   reconcile, and the worker extracts the new turns (the long-append path, ADR 0042 amendment 4).
4. **Where it is switched.**
   - The chat input's ☰ menu has **NMOS: this chat off/on**. Its name is fixed at load, so a tap says in the host's
     dialog which way it went.
   - The panel's Status tab starts with a **This chat** card: on or off, what that means, and the switch.
   - The sidebar's ☰ menu opens the panel (`registerButton` location `hamburger`). It shows icons only (v1.13.0
     `Sidebar.svelte`), so it is the 🧠 icon.
   - The progress display, when on, says "NMOS is off for this chat" after a generation in such a chat, and stops
     following the chat's conversation, so not even a coverage poll reaches the sidecar.
   - The dialog is the one alert outside the output listener (H18 amended): it answers the owner's own tap.
5. **Global switch first.** `disabled` still turns NMOS off everywhere; the per-chat list only adds chats to it. A chat
   turned back on while it is set is told so, in the card and the dialog.

## Consequences

- A chat that is off gets no memory and adds none. Turned back on after a long pause, its first generation may miss
  the deadline while the sync catches up (fail open, as for any long append).
- The list lives in PocketRisu, not in NMOS: a sidecar backup does not carry it, and another PocketRisu using the
  same sidecar has its own list.
- The host chat id is the key. A chat branched from one that is off is a new chat and starts on (H5).
- The request path reads one more arg per request; the chat read it follows was already there.
