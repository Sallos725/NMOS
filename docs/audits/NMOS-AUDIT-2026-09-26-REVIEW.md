# Review of the 2026-09-26 audit

- Reviews: `docs/audits/NMOS-AUDIT-2026-09-26.md` (Korean; kept as written).
- Baseline: `main` at `3fee5a8` (`v0.1.0-beta.19`), the same commit the audit used.
- Method: every High/Medium claim the audit calls a real bug was checked against the code; A-01 was
  reproduced again independently. Labels as in the audit: **[verified]** by code or run, **[inferred]**.
- Outcome: A-02 and A-04, then A-01 (the owner chose option (c) below), are fixed on branch
  `audit-fixes-a02-a04` (this document's PR). Everything else is open and listed under
  [Open items](#open-items).

## Verdict

The audit is sound. Its overall rating (late beta, not production-ready) stands. Every bug it marks as
verified is real. One cause is misattributed: A-01 fails in request validation, not in the INSERT the audit
names, and it reaches further than message bodies. The other corrections are about severity, a narrower
trigger for A-03, and a cheaper fix for A-01.

## Claims checked

| ID | Result | Evidence |
|---|---|---|
| A-01 | **[verified] reproduced; cause corrected, scope wider** | A throwaway test posting `"hello \ud800 there"` got reconcile 200 `needs_bodies`, then `UnicodeEncodeError … surrogates not allowed` from `/v1/sync/bodies`. The error is not raised by the INSERT in `ledger.py:store_bodies`, as the audit says. FastAPI 0.141 decodes bodies with `json.loads`, which keeps the lone surrogate. Pydantic then refuses the `str` (`string_unicode`). FastAPI's 422 response echoes the input, and Starlette fails to encode it, so the client gets 500. psycopg would fail the same way one step later. The same happens to a persona, chat or character name on every `/v1/sync/reconcile` (the chat never syncs), and to a query on `/v1/retrieve`. |
| A-02 | **[verified]** | `prompt.ts:hasPacket` used `includes(PACKET_TAG)` on every message; `core.ts:beforeRequest` returns early when it is true. |
| A-03 | **[verified], narrower trigger** | The dev `docker-compose.yml` passes `NMOS_LLM_JSON_MODE` to the worker only. But `runtime.effective` lets a value saved in the panel (`app_config.llm_json_mode`) override the environment in both processes, so the keys diverge only with the dev compose, `NMOS_LLM_JSON_MODE=0` in `.env`, and no saved panel value. The dev sidecar also lacks `NMOS_LLM_API_KEY`, so the panel's LLM "Test" button uses an empty key there unless one is saved. |
| A-04 | **[verified], worse than stated** | `llm.py:ChatModel.complete_json` read `res.json()["choices"][0]["message"]["content"]` catching only `KeyError/IndexError/ValueError`, so `"message": null`, `"choices": null` or a top-level array raised `TypeError`; list-valued `content` raised `AttributeError` in `parse_json_object`. `worker.run_once` did not catch either, and `worker.loop` catches only `OperationalError`, so the thread ended. **[inferred]** The job stays `running` until the 10-minute lock recovery hands it to another thread, so one job that always fails can end every worker thread in turn; the main thread keeps the process alive, so `restart: unless-stopped` never fires. |
| A-05 | **[verified]** | `auth()` passes when no token is set; no Host check; `/v1/config/models` sends the stored key to the URL in the request body. |
| A-07 | **[verified]** | README `H1–H14` and "unreleased `extract-v10`", AGENTS "`PHASE-8.md` is the latest", ARCHITECTURE §6 `saveSecretHeader`, STATUS `D1–D38` and `PHASE-7.md`, and guide.ko "다음 릴리스" are all present. |
| A-08 | **[verified]** | The lifespan runs every startup step on one `autocommit=False` connection (`api.py`, `db.py:make_pool`). |

## Corrections to the audit

1. **Severity of A-02 and A-04.** A-02 is more likely to happen than A-01: every request shows the model the
   packet's XML tag, and models that echo XML-like markup are common. A second trigger the audit missed:
   a user pasting the packet from the Status tab ("Show the injected memory") into the chat. A-04 can stop
   all extraction and embedding (see above). Both belong at **High**; A-03 at **Low–Medium** given its
   narrower trigger.
2. **A-02's scope.** The audit says memory stops "until the message is edited". It also comes back once the
   quoting message scrolls out of the prompt.
3. **Count mismatch.** The summary and A-07 say nine documentation drifts; the "문서–코드 불일치" table
   lists thirteen.
4. **A-05 and the owner's deployment.** The owner's production sidecar is published on a LAN address
   without a token. The owner confirmed (2026-09-26) that it is reachable only through the tailnet and the
   reverse proxy, with every other ingress blocked at the router, so this is accepted and not a live risk.
   A-05 remains a question about the product's defaults for other users.

## A-01: a fix that keeps the hash contract (chosen)

The audit offers (a) replacing lone surrogates with U+FFFD in both `normalizeText` implementations, which
changes the cross-language hash contract and needs a plugin release, or (b) rejecting such bodies with 422,
which leaves the chat unsynced.

A third option, recommended here: **(c) verify the hash on the text as received, then store the text with
lone surrogates replaced by U+FFFD** (content and metadata strings), in `ledger.store_bodies` only.

- The hash is recomputed from content only at ingest (`ledger.py`, `store_bodies`), so nothing later
  expects the stored content to re-hash to `revision_hash`.
- Sidecar-only: no fixture, plugin or protocol change, and no release coupling.
- Cost: the stored content differs from the host's by the unrepresentable code unit. PostgreSQL `text`
  cannot hold it at all, so this is the closest faithful copy. It touches "source content is stored
  verbatim" and needs an ADR and an owner decision, but a smaller one than (a).

The owner chose (c) on 2026-09-26. Because of the corrected cause above, the fix has to act before request
validation, and it has to cover the other request text too. See ADR 0029 and "Fixed in this PR".

## Fixed in this PR

**A-02 — a quoted packet tag no longer turns memory off** (`adapters/pocketrisu-plugin/src/prompt.ts`).
`hasPacket` now requires `role === 'system'` in addition to the tag. The plugin only ever injects the
packet as a system message, so H2 retries of an injected prompt are still recognised. The audit suggested
`startsWith`; `includes` was kept so that a host trimming or prefixing the system message cannot cause a
double injection.
Tests: `prompt.test.ts` "does not mistake a message quoting the packet tag…", `core.test.ts` "still syncs
and injects when a reply in the prompt quotes the packet tag". Both failed before the change.

**A-04 — one bad job no longer stops the worker** (`apps/sidecar/src/nmos_sidecar/worker.py`, `llm.py`).
- `run_once` catches any `Exception`, rolls back, and fails that job (backoff, `dead` after five
  attempts). Expected errors log a warning as before; unexpected ones also log the traceback and record
  `TypeName: message` as `last_error`.
- `loop` also catches any other `Exception`, logs it, waits 5 s and reconnects. This covers a failure
  while recording a job failure.
- `ChatModel.complete_json` reports `TypeError` shapes and non-string `content` as `LLMError`
  ("unexpected response shape"), like other malformed replies.
Tests: `test_extraction.py::test_an_unexpected_job_error_fails_the_job_and_the_worker_goes_on`, and
`test_llm.py` (malformed reply shapes; the null-message, null-choices, list-content and top-level-array
cases failed before the change, the others pin existing behaviour).

**A-01 — a broken emoji no longer stops a chat's sync** (ADR 0029, D40; sidecar only).
- `models.BodyText`: a message body is validated as the raw string, so its hash can be checked on the text
  as sent. `ledger.store_bodies` then stores content and metadata with lone surrogates replaced by U+FFFD
  (`canonical.storable`), keeping the host's `revision_hash`.
- `models.Text` makes other request text storable before validation: labels, `character_ref`, manifest
  `name` and special comments, query, previous reply, entity-link names.
- `set_json_dumps(canonical.storable_json)` in `nmos_sidecar/__init__.py` covers every jsonb value written.
- `ChatModel.complete_json` makes model replies storable.
- A validation-error handler keeps a 422 from turning into a 500 when it echoes such input. Host ids with
  a lone surrogate are refused with 422.
- Cost: ≈6.5 ms more to validate a 10,000-message manifest (13.9 → 20.4 ms).
Tests: `test_unstorable_text.py` covers a chat with broken characters in bodies, a speaker name and labels:
it syncs, is stored keyed by the host's hashes, re-syncs as `noop` and recalls with such a query. It also
covers the 422 for ids and the `storable` helper. `test_llm.py` covers an escaped half emoji in a reply.
All of these failed before the change.

No schema, generation or hash-format change. At the next release, the plugin fix needs the new
`dist/nmos-pocketrisu.js` installed and the page reloaded (H13); the A-01 fix needs only the new sidecar
image.

## Open items

Recommended order after this PR:

| Order | ID | What | Needs |
|---|---|---|---|
| 1 | A-03 | Pass `NMOS_LLM_JSON_MODE`, `NMOS_EXTRACT_HINTS` and `NMOS_LLM_API_KEY` to both dev services and `NMOS_EXTRACT_HINTS` to the release compose; warn in `worker.maintenance` when a handler key differs from the active generation | — |
| 2 | A-07 | Fix the doc drifts; extend `tools/check_release.py` to cross-check the H/D/K maxima and the phase file list | — |
| 3 | A-09 | Re-measure K1's 10k margin with extraction and embeddings on, or narrow the wording | real-host session |
| 4 | A-16 | Schema-transition test (0013 → 0020 with rows) and a `pg_dump` backup/rollback note | — |
| 5 | A-08 | Commit startup steps one by one | — |
| — | A-05, A-06, A-10, A-12, A-14, A-15 | As in the audit's owner-decision table | owner decision |

At release preparation, add A-01, A-02 and A-04 to `docs/KNOWN-ISSUES.md` → Resolved as "(not listed;
audit 2026-09-26)".
