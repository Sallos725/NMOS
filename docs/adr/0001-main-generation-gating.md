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
