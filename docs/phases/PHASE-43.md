# Phase 43 — Status windows by their shape, per chat, told as changes

Status: **proposed** 2026-10-11, not approved. Drafted at the owner's request after the Phase 41 live check.
It would amend Phase 39 amendment 2 (explicit card-bound status configuration) and ADR 0071. Not a roadmap
stage; a correction phase beside the current one (AGENTS.md §7.5) once approved.

## Why

1. **Setup is bound to the wrong thing.** A status rule is regex JSON bound to a card's exact display name. A
   renamed card or two cards with one name break or mix it, and the Settings view "saved JSON rules" lists every
   card's rules together, which the owner finds confusing.
2. **The current status can be invisible to the model.** NMOS withholds a current status value whose source
   message is in the prompt (D3: in context), and decides that from the message's prose. The owner's presets strip
   every status bar from the prompt, so on the trial install's newest card chat no current status value was placed
   in 14 of 14 requests. In the incident of 2026-10-11 (Phase 41 investigation), a request failed open, the model
   had no date in its prompt and invented one 15 days ahead; the next request's packet then carried that invented
   date as current state, faithfully. NMOS held the correct earlier value but never showed it.
3. **Placing the whole status every turn is heavy.** One trial card's status has 23 keys (about 1,700 characters
   as `<State>` items); its inventory value alone is 413 characters, repeated every turn.

## Proposal

S1. **A built-in shape detector, no regex.** In a reply, an outermost balanced `[ … ]` block whose `|`-separated
segments are at least three and at least 60 % `key=value` or `key: value` fields (a leading `Label:` such as
`Status:` is allowed; values cleaned as the rule parser cleans them) is a status window candidate.
Existing regex rules stay available as an advanced override and keep working unchanged.

S2. **Per chat, confirmed once.** When the same key set appears in at least two replies of a chat, the panel offers
"this chat has a status window (N keys) — track it". Confirmation binds the detected shape to that conversation
(Q1, Q2). Values, history and flags stay per chat as today.

S3. **The panel shows this chat only.** Detected keys, their current values, the toggle and pins for the open chat.
Other chats' and cards' bindings move to a collapsed management list; regex JSON only under advanced settings.

S4. **The packet tells the status as changes.** When a chat tracks a status window, its packet carries the current
value of a few core keys (Q3) and only the keys that changed since the previous status window, as changes: a number
as `44 (−1)`, a list as `+ added / − removed`, other text as the new value. This is placed whether or not the source
message counts as in context. A recorded recall option under `packet-v18`, off for historical traces (Q4, Q5).

## Evidence so far (read-only, private restored copy of the trial install; no provider calls)

| Chat | Replies | Detector values equal to the bound rule's | Recurring blocks found that are not status windows |
|---|---:|---:|---:|
| Card A (2 chats, 9 keys) | 14 | 126 / 126 | 0 |
| Card B (23 keys) | 49 | 1,127 / 1,127 (with the rule parser's tag cleaning) | 0 |
| Card C (no rule configured) | 2 | — (found a real 3-key status window) | 0 |
| Other chats | 13 | — | 0 (one non-recurring block ignored) |

Two prototype fixes were needed: brackets inside a value (`Location: … [a place] …`) required balanced outer
blocks, and five values differed until the parser's tag cleaning was applied. Lorebook-data blocks in replies were
not detected. This is one install's data; acceptance needs a wider synthetic false-positive set (A2).

## Questions for the owner

- Q1. Confirm in the panel (recommended), or start tracking automatically after N recurrences?
- Q2. After confirmation, bind to this chat only, or also to new chats where the same key set appears
  (recommended: same key set on the same card, so a new chat of that card starts tracked)?
- Q3. Core keys: automatic (keys that change in most status windows, such as date, time, location) plus pins in the
  panel (recommended), or pins only?
- Q4. Also skip the block when the prompt already holds the latest status window (the plugin checks the literal
  text), or always place it (recommended: always; it is small once told as changes)?
- Q5. Existing card-bound rules: keep both, with a one-click conversion in the panel (recommended), or migrate?
- Q6. Where the per-chat binding lives: `app_config` JSON (no migration) or a table (migration, high risk).

## Acceptance (once approved)

- A1. On the trial install's copy, the detector's values equal the bound rules' for every reply (above) and no
  non-status block recurs.
- A2. A synthetic false-positive set (prose with `=` or `|`, markdown tables, code, lorebook-data blocks, quoted
  logs, nested brackets) proposes no status window.
- A3. Packet: the state block's tokens per request on both cards, before and after; the zero-call replay gate shows
  no newly failed probe or forbidden phrase; chats without a status window are byte-identical.
- A4. The incident shape: a request whose prompt holds no status window gets the correct current date from NMOS.
- A5. Panel: the open chat's window only; other bindings collapsed; old card rules unchanged; restore and archive
  carry the new binding.

## Out of scope

Extraction prompts, generations, embeddings, provider calls; host-side preset changes; inferring dates or durations;
any change to raw source revisions. Plugin changes are limited to the panel and, if Q4 says so, a literal check.

## Risk

High risk: status-source scope, derived-state rebuild, packet contents, configuration and restore compatibility.
