# Phase 61 — What the model request carries: a JSON body the owner adds, and a reasoning effort that writes into it

Status: **approved**, 2026-11-23 (owner request of 2026-11-23, during the Phase 60 trial: "for OpenRouter, a place to
enter a custom JSON body and the reasoning effort; a dropdown for the effort that goes straight into the JSON"; the
questions answered the same evening: Q4 "fixed at 0, or not sent at all", Q7 "build now and deploy", the rest as
recommended). An owner request, not a roadmap stage. Built 2026-11-23/24 and on production since 2026-11-24 02:41 KST
(`exp-phase61-dd36134`): the switch made no generation and queued nothing; C1 and C2 held on a fresh copy. Amendments 1–2 (S5, S6)
built and on production since 2026-11-24 10:35 KST (`exp-phase61-9d2a80d`, migration `0039`).

Parameters marked **(owner)** are the owner's; those marked **(proposal)** are this draft's choice and the owner may
amend them. Nothing here changes a default: with the new setting empty, every request and every generation key is
byte-identical to today's.

**High risk** (`AGENTS.md §14`). Guarantees at risk, each with the check that pins it:

| Guarantee | Risk | Pinned by |
|---|---|---|
| A generation change re-derives nothing by accident (D20, ADR 0078, 0081) | the new setting enters every key, or a change of it is classified `version` and re-queues the latest turns of every chat (paid) | A1, A3, the copy check C1 |
| Derived rows carry what produced them (D20, D21) | rows written under another reasoning effort are served as if nothing changed | A3 |
| Secrets and credentials (D60) | a credential typed into the body reaches an archive, a log or `/v1/config` | A4, A5 |
| Deployment compatibility | an image from before this phase classifies the change back as `version` (rollback) | C2 |
| The plugin stays thin | settings logic in the browser | A7 |

Invariants it touches (`AGENTS.md §3`): **derived rows carry their generation** (the body is part of the generation
that wrote them); **the request path makes no generative call** (unchanged: the body is only ever sent by the worker,
the author's-note calls and the settings test).

## Why

1. The owner wants to try a reasoning model through OpenRouter at a low reasoning effort for extraction. Today the
   request is fixed: model, `temperature: 0`, the two messages and, in JSON mode, `response_format`
   (`llm.ChatModel.complete_metered`). There is no way to say how hard the model should think, so a reasoning model
   runs at its provider's default: slower and dearer than the owner wants for a per-turn call.
2. Providers differ in what else they take (a provider preference, a token cap, a thinking budget). A field per
   parameter would never end; one object the owner writes covers them.

## What it does

### S1 — One setting: the extra request body

- **`llm_extra_body`**: a JSON object, `{}` by default. Editable in the panel (S4), saved through `PUT /v1/config`
  like the other model settings, and settable as `NMOS_LLM_EXTRA_BODY` (a JSON object as text) for an install that
  configures by environment; a saved value wins over the environment, as every editable setting does.
- **Where it is sent.** Merged at the top level into every chat-completions body made with the extraction model:
  extraction and its confirmation calls, reveal checks, scene summaries, canon facts, the author's-note calls and the
  settings test (`/v1/config/test`, kind `llm`) **(proposal: one body for every call of that model; Q1)**. Never the
  embedder, never the reranker.
- **What it may not hold.** The request's own fields stay the request's: `model`, `messages`, `stream`,
  `response_format` (JSON mode owns it), `temperature` (0, or not sent: S1b), `n`, `tools`,
  `tool_choice`, `functions`, `function_call`. A body naming one of them is refused. So is a body that is not an
  object, one over 2,048 bytes as canonical JSON **(proposal)**, one with a key name that is not plain ASCII
  (letters, digits, `_`, `-`, `.`), and one with a key that looks like a credential at any depth (lower-cased with
  all but letters and digits removed, the name contains `apikey`, `authorization`, `secret`, `password`, `passwd`,
  `bearer`, `credential`, `privatekey`, `accesskey`, `subscriptionkey` or `cookie`, is `auth` or `key`, or ends with
  `token`): a credential belongs in the key field, which is write-only and never archived (D60).
- **Empty is today.** `{}` adds nothing: the request body is byte-identical to today's.

### S1b — The temperature: 0, or not sent (Q4, owner)

- **`llm_no_temperature`**: off by default. Off, every request carries `temperature: 0` as today. On, the request
  carries no `temperature` field at all, for a model that rejects or ignores one. Nothing else is selectable: the
  body may not name `temperature` (S1). Editable in the panel and as `NMOS_LLM_NO_TEMPERATURE=1`.
- It applies to the same calls as the body (S1), the settings test included.

### S2 — The body is part of the generation, and changing it is a model change

- **In the key only when it is set.** Each generation built from the model settings (extract, reveal, summarize,
  canon) gains the spec field `request`: the body itself, as canonical JSON would hold it (sorted keys). With an
  empty body the field is absent, so every key of every install that does not use the setting is byte-identical
  before and after this phase. Holding the body, not a fingerprint of it, lets the Inspector's generation page say
  which effort wrote a row.
- **The temperature in the key.** A spec that sends the temperature says `temperature: 0`, as every spec does today;
  one that does not says `temperature: null`.
- **A change of the body or of the temperature switch alone is a `model` change.** `request` and `temperature` join
  `generations.MODEL_FIELDS` (`model`, `endpoint`). So saving a different body is handled exactly as saving a different model is (PHASE-57 A3): the panel's
  preview says what each choice would queue, and the default is **carry on**: nothing is extracted again, turns
  already read stay served by the generation that read them, and new turns are read under the new body. `recent`
  reads the latest `extract_backfill` turns again, on the owner's choice only.
- With a compiler change among the `ADDS` compilers in the same save, the classification is `model` (as it already is
  when the model changes with the compiler), never `version`.

### S3 — The request

- `ChatModel` takes the body and sends `{**its own fields, **the extra body}`; the reserved names cannot collide
  because a body holding one is never accepted (S1).
- A provider that rejects the body answers an error, and the job fails as any model error does today (its message in
  the Status tab, the usual retries). Nothing is retried without the body: a silent fallback would write rows under a
  generation that says they were made with it.
- **The settings test sends the body under test**, so a rejection shows before anything is saved.
- A saved value that would be refused (a restored row, a downgrade) is ignored with one warning and the environment's
  value applies, as PHASE-60 S5 does for the reranker's settings. An invalid `NMOS_LLM_EXTRA_BODY` refuses startup
  with a message naming the setting.
- Reasoning tokens are already counted (`usage.reasoning`, Phase 17): the cost of an effort shows in the existing
  usage figures. Nothing new is measured.

### S4 — The panel: a JSON box, and a dropdown that writes into it

- In Settings, the extraction model's card gains one text area, **"Extra request values (JSON)"**, holding the body
  as indented JSON, one dropdown, **"Reasoning effort"**, and one switch, **"Do not send a temperature"** (S1b).
- **The dropdown is a view of the JSON** **(owner)**. Choosing a value sets `reasoning.effort` in the text
  (`{"reasoning": {"effort": "low"}}`), keeping every other key; "—" removes `effort`, and `reasoning` with it when
  that leaves it empty. Editing the text by hand moves the dropdown: it shows the value when `reasoning.effort` is one
  of its values, "custom" otherwise. While the text is not a JSON object the dropdown is disabled and the field says
  why. One stored setting, no second source of truth.
- **Values** **(proposal; Q3)**: —, `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`: the values
  OpenRouter's documentation lists for `reasoning.effort` (read 2026-11-23; not every model accepts every value, and
  the settings test says so before a save).
- **Shown for an OpenRouter address** **(proposal; Q2)**. The text area is shown for any address. The dropdown is
  shown only when the model address's host is `openrouter.ai`: `reasoning.effort` is that service's unified field,
  and other providers name theirs differently (the owner writes those in the JSON box).
- Saving goes through the model-change preview that exists (S2). The plugin holds two small pure functions (read the
  effort from a JSON text; write it into one) and the two inputs; validation, limits and refusals are the sidecar's.
- `GET /v1/config` returns the body (`llm.extra_body`, an object) and the switch (`llm.no_temperature`); the body is
  not a secret, and a credential-like key is never accepted into it (S1). `PUT /v1/config` takes `llm_extra_body`
  (an object) and `llm_no_temperature` (a boolean); `/v1/config/test` (kind `llm`) takes `extra_body` and
  `no_temperature` beside the fields it has, and sends the request as they say.

### S5 — What the worker is doing, shown (amendment 1, owner 2026-11-24)

The owner could not tell, after a save that queued a long re-read, whether the model was slow or failing: the panel
showed neither the queue nor a model error (S3 said a rejection shows "in the Status tab"; nothing did).

- **`GET /v1/worker/status`** (read-only, the same authorization as the other routes; never on the request path):
  the jobs waiting by kind (`extract`, `reveal`, `summarize`, `canon`, `embed`), the number running, the number
  being tried again (waiting or running after a failed attempt), the number given up on in the last 24 hours, the
  number finished in the last 30 minutes, and the most recent failure (its kind, time, state and the first 200
  characters of its error). One bounded read of the job table; numbers only, no chat text of its own. A queued
  job of a generation its kind has left (a model change saved with "carry on" leaves such jobs queued, and no
  worker claims them) is counted apart as `set_aside`: not waiting and not being tried again, or the card would
  show it waiting for ever.
- **The Status tab** gains a "Model work" card: one line for the queue ("1,708 waiting: extraction 642, canon 1,010,
  summaries 56; 2 running"), one for the last 30 minutes (finished, being retried, given up), and the last error
  with its time. With nothing waiting and no recent failure it says so in one line. Shown only when the sidecar has
  the route (an older sidecar: nothing). The plugin composes the lines from the numbers with one pure function; it
  fetches the route when the Status tab is drawn, with the tab's usual deadline, and a failure of the fetch leaves
  the card out.
- Not a high-risk addition: it reads counts and writes nothing; no setting, key, schema or packet changes.

### S6 — A log of model calls (amendment 2, owner 2026-11-24; migration `0039`; ADR 0089)

A failed call left one trace: the job's `last_error`, overwritten by the next attempt and deleted with the job. The
container's own log is lost at every deployment. The owner asked for a log kept on the server.

- **`model_call`** (migration `0039`): one row per call the worker or the sidecar makes to a model outside the
  request path: `at`, `kind` (`extract`, `reveal`, `summarize`, `canon`, `embed`, `note`, `test`), the conversation
  and the job when there is one, the generation key, the model and the endpoint (scheme, host and path; never
  userinfo or a query), `outcome` (`ok`, `http`, `timeout`, `transport`, `bad_reply`), the HTTP status, the time it
  took, the usage the provider reported, and for a failure the first 300 characters of the provider's error.
- **Never in it:** a prompt, a reply, a key. NMOS writes no chat text of its own: a reply that could not be read is
  logged by the kind of fault only (its text is the model's, so it may hold chat text). The one free text is the
  provider's own error message for a failed HTTP call; a provider that quotes the request back in its error puts
  that quote there, cut at 300 characters, as it already does in a job's `last_error`. A key that is part of an
  endpoint's path is kept as the generation's endpoint already keeps it.
- **Never in the way.** The row is written outside the job's transaction, so it survives a failed job; writing it is
  bounded and its own failure is swallowed with one warning: a call, a job and a request go on without the log.
  The cost is one short connection per logged call (measured: about 8 ms; at most 2 s to connect and 2 s to write,
  the second only when another session holds the chat's row, as a chat's delete does), then the row is given up.
  `ok` means the call succeeded: a reply that is JSON but lacks what the job needs fails the job, not the call.
  `/v1/retrieve` writes none: the request path's embedding and rerank calls are not logged (a trace has their times).
- **Kept as long as traces are** (`NMOS_TRACE_RETENTION_DAYS`, 30 by default); the worker's maintenance prunes it.
- **Read.** `GET /v1/worker/calls` (the newest first, at most 500) and a summary of the last hour in
  `GET /v1/worker/status` (`calls`: how many succeeded, how many failed by HTTP status or fault, the median time).
  The Status tab's "Model work" card says it in one line; the browser Inspector has a "Model calls" page.
- **Archive, delete, rollback.** The table is in no archive (like `job`); deleting a chat deletes its rows (the
  foreign key cascades, so an older image deletes a chat cleanly too); an image from before the migration ignores the
  table.

### What it does not change

Any default; any key of an install with an empty body and the switch off; the request path (`/v1/retrieve` makes no
model call); JSON mode; the embedder; the reranker; the model-change choices themselves.

## Out of scope

- A body per call kind (one for extraction, another for summaries).
- Extra bodies for the embedder or the reranker; custom headers.
- Reasoning dropdowns for other providers' field names.
- The host's main or sub model for extraction (decided against, owner 2026-11-05).
- A recommendation of a model or an effort: whether a model at a low effort extracts well is the owner's experiment
  (Q6).
- A paid measurement in this phase: every check is zero-call (stub models).

## Questions (answered, owner 2026-11-23: Q1 a, Q2 a, Q3 a, Q4 amended, Q5 a, Q6 no, Q7 a)

- **Q1 — Which calls carry the body?** (a) every call made with the extraction model (recommended: one model, one
  way of calling it, one field in every key); (b) extraction only (summaries and canon facts keep the provider's
  default effort).
- **Q2 — When is the dropdown shown?** (a) only for an `openrouter.ai` address (recommended); (b) always, writing the
  same `reasoning.effort` whatever the provider.
- **Q3 — Which values?** (a) —, none, minimal, low, medium, high, xhigh, max (recommended); (b) only low, medium,
  high.
- **Q4 — `temperature`.** Answered: fixed at 0, or not sent at all (a switch, S1b); no other value. The draft's
  choices were (a) fixed at 0 and reserved; (b) the body may override it. Some reasoning models
  ignore or reject a temperature; whether the model the owner means to try accepts `temperature: 0` was not checked
  (the settings test will show it).
- **Q5 — What a body change does.** (a) the model-change dialog, carry on by default (recommended); (b) always carry
  on, no dialog.
- **Q6 — The experiment.** The feature ships with zero-call checks only. Does the owner want a measured comparison
  (a copy of one chat extracted twice, counts of rows and of rows that fail their quote check, cost) before using a
  new model and effort on production? It would be a paid run and needs its own estimate and go. Answered: no
  measurement in this phase.
- **Q7 — When.** Production is in the Phase 60 trial and the 1.0 quiet weeks restarted on 2026-11-23. Deploying this
  restarts them again. (a) build now, deploy on the owner's word (recommended); (b) wait for the trial's end. Answered:
  build now and deploy.

## Steps

1. This spec and ADR 0088 (the body in the generation, `request` as a model field), after the questions are answered.
2. **Pin what must not move**: the keys of every generation for fixed settings with an empty body, and the request
   bodies `ChatModel` sends today (a stub transport), before any code changes.
3. The setting: `config.py`, `runtime.EDITABLE`, validation (S1), `public_view`, the environment variable, the
   compose files and `.env.example`.
4. `ChatModel` and every call site (S3); the settings test.
5. The generations: `request` in the four specs when set; `MODEL_FIELDS`; the preview and the save.
6. The panel (S4): the two pure functions with their tests, then the card; build.
7. Checks (below), the scoped self-review (`AGENTS.md §14`), docs (`ARCHITECTURE.md §5`, `CHANGELOG.md`,
   `docs/STATUS.md`, the guide).
8. The copy (C1, C2), then production on the owner's word.

Each small logical change is one commit.

## Acceptance criteria

- A1. With an empty body and the temperature switch off: every pinned key of step 2 is unchanged, and every request
  body is byte-identical to the one pinned.
- A1b. With the switch on: no request of S1's call sites has a `temperature` field; each spec says
  `temperature: null`; toggling it alone is a `model` change.
- A2. With a body: every call site of S1 sends it merged at the top level; `response_format` is still JSON mode's;
  the embedder's and the reranker's requests are unchanged.
- A3. `classify`: a body-only change is `model`; with an `ADDS` compiler change it is `model`; activation under
  "carry on" queues nothing on a covered chat and only unserved turns on a partial one; `recent` queues the latest
  `extract_backfill` turns; the preview's counts match what the save queues. The generation row's spec holds the body.
- A4. Refused with 422 and nothing saved: not an object; over the size; a reserved name; a credential-like key at any
  depth. A saved value that would be refused is ignored with a warning; an invalid environment value refuses startup.
  **Amended 2026-11-24 (review):** also refused: a key name that is not plain ASCII; a value or key name holding one
  of the install's own credentials (and a key cannot be saved while the body holds it); a float PostgreSQL would
  store in another form (1e16 and above in size, negative zero).
- A5. An archive holds the setting and a restore brings it back; the archive's credential scan is unchanged.
- A6. The settings test sends the body under test and shows a provider's rejection.
- A7. Plugin: reading and writing the effort round-trip and keep every other key; a text that is not a JSON object
  disables the dropdown; the dropdown is hidden for an address that is not OpenRouter's (Q2); both languages for
  every new string; the plugin's tests, typecheck and build pass.
- A8. The sidecar suite passes with `NMOS_TEST_REQUIRE_DB=1`; counts reported.

## The copy

- C1. On a copy of production (isolated as PHASE-60 C1: an internal network, no worker, empty keys): the new image
  with an empty body and the switch off queues nothing and changes no key; saving a body with "carry on" queues nothing and makes a new
  extract generation whose spec differs from the previous one in `request` only.
- C2. **Rollback rehearsal.** An image from before this phase does not know `request`: it would read a generation
  with a body or without a temperature, next to its own, as a `version` change and queue the latest turns of every chat again. So
  a rollback clears the body and turns the switch off first, under the new image (a `model` change, carry on, nothing queued), and only then
  changes the image, with the worker stopped throughout (as PHASE-60 C3). Both steps queue nothing on the copy.

## Stop conditions

- A pinned key moves with an empty body, or a body change is classified `version`: stop; nothing is deployed.
- Either rollback step queues a job on the copy: stop before production.
- The body cannot be kept out of a call site without a second request path: that call site stays without it and the
  report says so.

## Risk and release

High risk (the table at the top). Off path: an install that leaves the body empty sees one more settings field and
nothing else. No migration. No tag. Deploying it to the install the owner uses restarts the 1.0 gate's quiet weeks
(`ROADMAP-1.0.md`); whether it is in `1.0.0` is the owner's decision.
