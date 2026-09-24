# 0023 — The host's persona name is the persona

Status: accepted, 2026-09-24. Owner-reported bug after `v0.1.0-beta.15` (not a phase feature). The
owner chose: the plugin reads the name from the host, and the host's permission is asked at load.
Amends ADR 0012 (entity identity) and D26.

## Context

The extraction prompt tells the model to write the persona as `{{user}}` "only if no name is given"
(since Phase 2). PocketRisu writes the persona's name into the chat: the replies use it, and a user
message typed with `{{user}}` is stored with the name already in place (HOST-FACTS, "Persona name").
The extractor therefore wrote the persona both ways. ADR 0012 counted only `{{user}}`, `{user}`,
`user` and `유저` as the persona, so a named persona was two characters.

In the owner's chat (60 messages, the persona named 유우마 in 51, `{{user}}` in none), `extract-v8`
wrote `{{user}}` 28 times and 유우마 70 times, `extract-v6` 4 and 31 times. The effects:

- two current locations, holders and promise threads for one person;
- a named persona was not the persona for recall. Its facts, events it took part in (ADR 0021) and
  knowledge marks naming it counted as a mention in every message that narrates the persona by name,
  while the same facts spelled `{{user}}` came back only for a first-person question;
- KNOWN ENTITIES listed 유우마 as an ordinary character (47 extractions), which kept the split going.

The V3 plugin API gives no user name. `getDatabase(['personas', 'selectedPersona'])` returns the
personas and the selected index, behind the host's "db" permission ("access the full database").
`getChatFromIndex` already returns the chat's `bindedPersona`. The host names the user after the
chat's bound persona, else `db.username`, which the persona screen keeps equal to the selected
persona's name (HOST-FACTS).

## Decision

1. **The plugin reports the persona name.** It reads the personas off the request path: once at load,
   right after its hooks are registered, so the host's permission dialog comes after the replacer one
   and never during a request; then again in the background when the last read is older than 30 s. It
   picks the persona as the host does: the chat's bound persona, else the selected one. The name goes
   with every sync as `persona_name`, like the bot and chat labels. A refused permission or a failed
   read sends none. The request path never waits for it.
2. **The sidecar keeps the latest name** (`conversation.host_persona_name`, migration 0018). A report
   replaces it; a sync without one leaves it. It is the host's current name, as `{{user}}` in the chat
   is: a user who renames or rebinds the persona changes it for the whole chat.
3. **Resolution (`resolve-v3`, amends ADR 0012 item 2).** For characters, the conversation's persona
   name joins `{{user}}`, `{user}`, `user` and `유저` as the persona. Other types are unaffected (an
   item named 유우마 stays an item). The persona entity lists the host's spelling among its names, and
   the resolver exposes every name the persona goes by (those, the host's name and the story's aliases
   of the persona) as `persona_names`. Nothing is stored: the next read after a name arrives, or
   changes, re-groups the rows already extracted, with no model call.
4. **The persona never counts as a mention under any name.** Fact and claim recall ignores
   `persona_names` in subjects, objects, participants, `known_by` and `hidden_from`; a first-person
   question still brings the persona's facts, now under either spelling. Thread recall does the same
   (ADR 0019, 0021).
5. **Hints.** KNOWN ENTITIES leaves the persona entity out, whatever its spelling. OPEN PROMISES does
   not count its names. The extraction prompt is unchanged (no new extractor generation); the hints
   recorded on an extraction row show what it saw.

## Consequences

- Upgrading changes entity ids once (`resolve-v3`). A chat's persona joins up at its first sync with the
  new plugin; until then, and wherever the permission is refused, resolution is as before.
- PocketRisu shows a second dialog at load: *"Plugin nmos_memory is requesting to access the full
  database, which may expose sensitive information."* The plugin reads only persona names and ids with
  it. Refusing is permanent until the permission responses are reset; NMOS then keeps working without
  the name.
- A different persona bound to the same chat later takes over the persona role; facts written under the
  old name become an ordinary character again. The host does the same with `{{user}}`.
- A persona name that is also another character's name merges them. The resolver cannot tell them
  apart from text, as with any shared name (ADR 0012, item 3).
- The extraction prompt still allows either spelling. Asking the model to always write `{{user}}`
  would be a new extractor generation; the owner deferred it.
