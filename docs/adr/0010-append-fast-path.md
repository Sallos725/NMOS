# 0010 — Verified append fast path

Status: accepted, 2026-09-23. Track A, A1 (`docs/proposals/TRACK-A-STABILIZATION.md`). Adds migration
0013; D4 unchanged in meaning.

## Context

At 10,000 messages a warm generation (the previous reply plus a new user turn) cost the sidecar
≈715 ms, almost all of it proportional to the chat: `load_state` read every stored revision, `plan`
compared the whole head with the whole manifest, `_membership_rows` recomputed window and turn data for
every member, and the append was concatenated onto the head commit's `delta` jsonb, which PostgreSQL
rewrote in full (2.2 MB, ≈117 ms at 10k, growing with every append). Together with the plugin's
manifest this exceeded the default 800 ms deadline beyond ≈8,000 messages, so memory was effectively
off for long chats (`docs/perf/scale.md`).

Almost every generation is a pure append. The host gives no hook that says so (H10), so the sidecar
must prove it from the request alone.

## Decision

1. **Proof of an append.** A sync takes the fast path only when all of these hold; otherwise the full
   path runs unchanged:
   - the conversation has a head, and the request is longer than it (head length is
     `max(position) + 1` on the `(commit_id, position)` primary key);
   - the manifest hash of the request's first `head length` messages equals the stored head manifest
     hash — a deep edit, delete, reorder, swipe, disable or reroll changes it;
   - no new message ID repeats, none is already a head member, and none is an `allBefore` cut (a new
     cut changes the turn layout of the whole head).
   An equal-length request with the head's manifest hash is a noop, as before, without loading state.
2. **Bounded tail.** The sidecar loads the head from the start of turn `last − 2K` (and at least the
   last `NMOS_EXTRACT_WINDOW` members). From turn `last − K` on, a turn's K-turn hash window lies
   inside the tail, so layouts computed from the tail equal those of the whole head there. The tail is
   rejected (full path) when a member before that region is not `accepted`, or when the tail's own
   layout does not reproduce the stored `turn` / `turn_hash` (e.g. K changed).
3. **Same result.** `reconcile.plan_append` computes lifecycle, ops and changes from the tail and the
   new messages; `ledger.apply_append` writes the same rows `apply_plan` would; extraction and
   embedding jobs are scheduled from the tail. Acceptance of a member depends only on members after
   it, and every member that can change lies in the tail, so nothing outside it changes.
   `tests/test_append_fast_path.py` drives two sidecars (fast path on and off) with the same random
   host actions and compares ledger, windows, turns, jobs and observations after every sync.
4. **Appends are rows (migration 0013).** An append no longer rewrites the head commit's `delta`: it
   inserts a `worldline_append` row (ops, changes, observation). A commit's full delta is its `delta`
   followed by its appends in `seq` order; `nmos-rebuild` replays both, and the Inspector's commit
   list counts both. Deltas written before 0013 keep their inline append ops, which replay first. The
   full path writes appends the same way.
5. **Kill switch.** `NMOS_APPEND_FAST_PATH=0` forces the full path for every sync.

## Consequences

- Warm append at 10,000 messages: p50 715 → 156 ms (p95 768 → 191 ms) in `tools/bench_scale.py`,
  including ≈39 ms of the harness's own JSON encoding. What remains is mostly parsing the full
  manifest twice (reconcile, then bodies with `then_reconcile`); removing that needs a protocol
  change on the plugin side. Edits and other divergences are unchanged (full path).
- The fast path trusts nothing the plugin says beyond the request itself; every shortcut is checked
  against stored data, and a failed check costs only the full path.
- Migration 0013 adds one table and two indexes; existing data needs no backfill.
