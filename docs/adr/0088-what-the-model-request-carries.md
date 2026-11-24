# ADR 0088: What the model request carries is part of the generation, and changing it is a model change

Date: 2026-11-23. Status: accepted (PHASE-61, approved by the owner 2026-11-23).

## Context

The requests the worker sends to the extraction model were fixed: the model, `temperature: 0`, two messages and, in
JSON mode, `response_format`. The owner wants to add provider parameters (first of all a reasoning effort) and to be
able to send no temperature to a model that will not take one. A derived row must carry what produced it (D20, D21),
and a generation change must re-derive nothing by accident (ADR 0078, 0081): a setting hashed into the key is, by
`generations.classify`, a `version` change, which queues the latest turns of every chat again.

## Decision

1. **One object.** `llm_extra_body`, a JSON object, is merged at the top level into every chat-completions body made
   with the extraction model. It may not name the request's own fields, hold a credential-like key, or exceed a small
   size. A second setting, `llm_no_temperature`, sends the request without a `temperature` field; no other temperature
   is selectable.
2. **In the key only when set.** A generation's spec gains `request` (the body itself) only when the body is not
   empty, and says `temperature: null` only when none is sent. With both settings at their defaults every key is
   byte-identical to the key before this decision.
3. **A model field.** `request` and `temperature` join `generations.MODEL_FIELDS`: a change of either alone is
   classified `model`, so the owner's choice applies (carry on by default, PHASE-57 A3) and nothing is extracted again
   unless the owner asks.
4. **No silent fallback.** A provider that rejects the body fails the job; the request is never repeated without it,
   since its rows would then carry a generation that did not make them.
5. **Rollback is two steps.** An image from before this decision reads a spec with `request` or a null temperature
   as a `version` change next to its own. The settings go back to their defaults under the new image first (a `model`
   change, carry on), then the image changes, with the worker stopped (as ADR 0081's switch, PHASE-60 C3).

## Consequences

- The spec holds the body, so which body wrote a row is on record; the Inspector does not show it yet.
- The panel's reasoning-effort dropdown is a view of the JSON text; there is one stored setting.
- A body is archived like any other setting; the credential scan is unchanged because a credential-like key is never
  accepted into it.
- Amended 2026-11-24 (review): beside credential-like key names, a body holding one of the install's own credentials
  in a value is refused, since the body is stored in every generation it makes and the archive's scan would then
  refuse every archive.
