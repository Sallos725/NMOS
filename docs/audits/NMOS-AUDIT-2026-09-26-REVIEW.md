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
double injection. The host keeps the injected message a system message across retries: provider conversion
(e.g. Gemini's `system:` folding) works on a copy (HOST-FACTS Q2, source reading). Only a Lua `request`
trigger that rewrites it into another role (H3) could make a retry inject twice; that is a known limitation
of 0.1.0-beta.20.
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

Still open (the fixes below are in order of landing):

| Order | ID | What | Needs |
|---|---|---|---|
| — | A-05, A-06 (invariant 9 wording, the one drift left), A-10, A-12, A-14, A-15 | As in the audit's owner-decision table | owner decision |
| — | From A-09: the 3 s default deadline (D24) at ≈10,000 messages with extraction on; fact reads (≈280 ms for 15,000 facts, every request) | Raise the default, or make fact reads incremental, or keep the workaround | owner decision |

A-01, A-02 and A-04 were released in `v0.1.0-beta.20` and are listed under `docs/KNOWN-ISSUES.md` →
Resolved.

**A-03 — fixed after beta.20** (branch `audit-a03-compose-env`).
- The development `docker-compose.yml` now uses one `x-nmos-env` anchor for both services, as the release
  compose does. The union of the old blocks adds `NMOS_LLM_JSON_MODE`, `NMOS_LLM_API_KEY` and the recall
  settings to the sidecar, and the rest to the worker.
- Both compose files pass `NMOS_EXTRACT_HINTS`.
- `worker.unserved` finds queued jobs of each kind's active generation that no handler of the worker
  implements. `worker.maintenance` logs a warning when the same ones are still there 30 s later.
Tests: `test_compose_env.py` checks that sidecar and worker share one environment and that every variable
documented in README or `.env.example` reaches it (it failed for both files before the change).
`test_generations.py::test_a_worker_whose_settings_give_another_key_sees_the_jobs_it_cannot_serve`.

**A-07 — fixed after beta.20** (branch `audit-a07-doc-drift`). Of the thirteen rows in the audit's
"문서–코드 불일치" table:

| # | State |
|---|---|
| 1 README `H1–H14` | fixed: `H1–H17` |
| 2 README, guide.ko "unreleased / 다음 릴리스" `extract-v10` | fixed: "since 0.1.0-beta.19" / "0.1.0-beta.19부터" |
| 3 AGENTS "`PHASE-8.md` is the latest" | fixed |
| 4 ARCHITECTURE §6 `saveSecretHeader` | fixed: plugin arg `auth_token` (ADR 0003, H12) |
| 5 ARCHITECTURE §7 layout | fixed: phases to 9, `deploy/`, `perf/`, `audits/`, `proposals/`, the worker, current tools |
| 6 STATUS `D1–D38`, `PHASE-0.md`–`PHASE-7.md` | fixed (D range earlier in #84) |
| 7 Invariant 9 "storage is replaceable" | **open**: an invariant changes only by owner decision (A-06) |
| 8 D9 `character_pov` | fixed: marked not implemented and not authorized |
| 9 README plugin arguments | fixed: `route`, `language`, `hud` added |
| 10, 11 `NMOS_EXTRACT_HINTS`, dev `NMOS_LLM_JSON_MODE` | fixed by A-03 |
| 12 K1 / README 10k margin | wording narrowed in K1, README and guide.ko: measured with no facts or vectors; the rest is A-09 |
| 13 AGENTS §0 duplicating STATUS | fixed: §0 points to STATUS and keeps only the standing rule |

The release check now covers these. `tools/check_release.py:drift` compares the ranges in STATUS and
README (`H1–Hn`, `D1–Dn`, `K1–Kn`), STATUS's ADR and phase-spec ranges, and AGENTS's "latest" phase with
the lists they stand for. `apps/sidecar/tests/test_docs_consistency.py` runs it in CI on every change.
Run against the audited commit `3fee5a8`, it reports rows 1, 3 and 6. At tag time, `check()` also refuses
"(unreleased" or "(다음 릴리스" in README and guide.ko.

**A-16 — fixed after beta.20** (branch `audit-a16-upgrade-path`). The audit asked for a schema-transition
test with rows. This goes one step further: the rows come from the earlier releases' own code.
- `tools/make_upgrade_fixture.py <tag>` checks the release out in a temporary worktree and runs its sidecar
  and worker as processes, with a deterministic stub model and embedder. A scripted chat goes through them
  (facts, an edit, a live reroll, a swipe back, a disabled message, a branch, recalls). The tool
  `pg_dump`s the database to `fixtures/upgrade/<tag>.sql`, with the host's view of the chats in
  `<tag>.chat.json`. It is committed, so the upgrade evidence no longer lives in scratch code.
- Fixtures: `v0.1.0-beta.7` (migration 0010, per-message extraction: crosses 0011–0020 and the pre-turn
  `window_hash` path, A-15) and `v0.1.0-beta.16` (0018, where the owner's database was; has
  `worldline_append` and `observation_base` rows).
- `apps/sidecar/tests/test_upgrade.py` restores each dump, applies the current migrations and starts the
  current sidecar. It checks:
  - re-syncing the recorded chats is a no-op;
  - facts the earlier release extracted are still served;
  - the earlier traces are kept;
  - an append, an edit and a recall work, and the recall replays as recorded;
  - the current worker re-extracts and re-embeds without a failed job;
  - an edited-away fact is masked;
  - delete and `nmos-rebuild` work.
- README and guide.ko document backup (`pg_dump -Fc`), upgrade and rollback (restore the backup, then start
  the older image; migrations only go forward). The backup and restore commands were run against the
  compose Postgres on a restored beta.16 database: row counts and the source-revision guard triggers came
  back, and the current migrations applied on top.

**A-08 — fixed after beta.20** (branch `audit-a08-startup-steps`).
- The lifespan runs its startup steps on their own autocommit connection, not a pooled one, so:
  - `normtext.backfill` and `retention.prune_text` commit batch by batch;
  - `ledger.refresh_turns` commits head by head.
- Two steps stay one transaction each:
  - `sync_rules` deletes other rule versions and backfills. A partial backfill would look complete to its
    "any rows?" check, so this must not be committed halfway.
  - `activate` makes a generation active together with the jobs it is missing (and holds its advisory
    lock only there).
- The connection pool is created after the startup steps, so a failed startup leaves no pool open.
Test: `test_startup.py`. An interrupted normalized-text backfill keeps the batches it finished (0 kept
before the change), and the next start completes it.

**A-09 — measured after beta.20** (branch `audit-a09-k1-remeasure`). The audit was right.
- Setup: an isolated PocketRisu v1.12.0 with the synthetic 10,000-message chat, the beta.20 plugin and
  sidecar, and stub extraction and embedding. Before measuring: 15,000 facts and 15,101 vectors after
  "Extract all history".
- With both off: warm generations took 2.73–2.79 s, reproducing K1.
- With both on: 3.14–3.29 s over 10 requests, all over the 3 s default, so every one would have gone
  without memory.
- Recall added 0.4–0.7 s. In the sidecar, ≈280 ms is the read-time fold of every head assertion and
  ≈115 ms the vector search.
- The owner's chat has ≈9.7 facts per turn (aggregate count), more than the 3 used here, so a real chat
  of that length reads more.
- K1, README, guide.ko and `docs/perf/scale.md` now give the measured numbers, and the workaround
  deadline (≈4,000 ms at 10,000 messages with extraction on). The default deadline (D24) is unchanged.
  Changing it, or making fact reads cheaper at this size, is a separate decision (below).
