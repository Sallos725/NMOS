# 0001 — Main-generation gating (resolves O3)

Status: accepted by owner, 2026-09-22.

## Context

`beforeRequest` receives every model request with only a model mode (H1). Runtime evidence
(HOST-FACTS Q1/Q2): send, reroll, continue and retries use `model`; Auto Suggest uses `submodel`;
trigger/Lua LLM calls also use `model` (source reading). In every observed main generation the
prompt's last `user` turn equals the host chat's latest user message after normalization; in
every `submodel` call it does not.

## Decision

The plugin treats a request as a main generation only when **both** hold:

1. `mode === 'model'`;
2. the last `user`-role message in `formated` equals the latest `user` message of the current
   host chat, after NFC + CRLF→LF normalization and trimming.

Everything else passes through untouched.

## Consequences

- Auxiliary requests never receive a packet.
- A trigger/Lua `model` call that happens to end with the latest user message would be treated as
  main generation. This was not observed; it is accepted as a rare, harmless over-injection.
- A chat whose latest user message is transformed by host regex scripts before prompting would
  fail rule 2 and get no packet (fail-safe direction).

## Amendment (2026-09-22)

Rule 2 compares *cleaned* text (markup stripped, whitespace collapsed) and accepts containment of a
64-character anchor from the host message. Sim bots and input scripts often wrap or reshape the user
turn, and exact equality would silently turn memory off for them.

## Amendment 2 (2026-09-23)

Rule 2 no longer looks only at the **last** `user` message. Real presets put instruction blocks
after the turn. The owner's preset wraps the input in `<Current Input>` over three user messages,
then adds three user-role blocks and a system note. Under the old rule every request in that chat
was classed as auxiliary: no sync, no retrieval, and nothing in the status panel said why
(`docs/HOST-FACTS.md`, "Preset-shaped prompts"). Keeping a rule per preset layout would not scale.

Rule 2 now reads: the host chat's latest user message (cleaned text, 64-character anchor) is in some
prompt message that is not `assistant`, searched newest first. No preset layout is assumed; the only
assumption is that a main generation sends the user's input to the model. The packet goes before
that message, or before the run of user messages that ends with it, so a preset's wrapper around
the input is not split.

Consequences: a `model`-mode auxiliary call whose prompt contains the latest user input anywhere is
now treated as a main generation. The Consequences section above already accepts this as rare,
harmless over-injection. A preset that sends the input only in a transformed form (e.g. translated)
still gets no packet (fail-safe).
