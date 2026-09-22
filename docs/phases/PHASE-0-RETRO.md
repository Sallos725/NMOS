# Phase 0 retrospective (2026-09-22)

## Surprises

1. **The host decides more than the docs assumed.** Continue with the default `useSayNothing`
   creates a new char message. Reroll removes the tail *before* the request (H14). Import
   duplicates message ids across chats (H6). Importing silently re-targets the current chat index (H9).
2. **Plugins need a secure context (H8).** Over plain-HTTP LAN, V3 plugins do not load at all. NMOS
   deployment docs must lead with "localhost or HTTPS".
3. **Replacers leak on plugin unload (H13).** After any plugin install, update, or disable, every
   generation hangs until reload. It looked like an NMOS bug twice before the source reading found it.
4. **`saveSecretHeader` is a stub (H12).** The token lives in a plugin arg (ADR 0003).
5. **No group chats on this build (H11).** Group-chat principal logic has no host surface.
6. **Recall tuning was needed immediately.** With the prescribed "user + previous AI" max score, the
   previous AI turn dominated on repetitive chats. It is now a tiebreaker (ADR 0004).
7. **The first plugin cache key could inject stale text.** It was keyed on tail id + prompt length,
   so an edit to an out-of-context message followed by a reroll reused the old packet. The key is
   now the full chat state. The bug was found only by driving the real UI.
8. **Performance was fine once two accidental O(n) costs were removed:** a per-row `allBefore` cut,
   and full-manifest observation JSON. 1,000-message chats add ≈200 ms; ~500-message chats add
   ≈120 ms at p95.

## What worked

- Recording hash-only manifests in 0A gave the reconciliation planner real fixtures without storing
  any RP text.
- A pure planner (`reconcile.py`) with replayable, key-based delta ops made the idempotency and
  rebuild criteria cheap to prove.
- Driving the real PocketRisu UI headlessly (Playwright over CDP, isolated container, stub model)
  made every acceptance check a real host check instead of a simulation.

## What Phase 1 should change or keep in mind

- **Write `docs/phases/PHASE-1.md` first.** Deterministic state parsers (D10) need real examples of
  the owner's bots' status windows and HTML/regex blocks. That is an evidence boundary like 0A.
- Keep the plugin thin. Parsers belong in the sidecar and run on stored revision content.
- The lineage from a live reroll to its replacement is not observable in one request (H14). If
  Phase 1+ needs it, correlate on the next sync: a new tail char at the same position whose
  `swipes` contain the retracted text.
- Decide retention for `host_observation` (compact now, but still grows per divergence) together
  with O5.
- Retune `NMOS_RECALL_THRESHOLD` on real Korean RP chats. The CJK token estimate
  (1.5 tokens/char) is deliberately conservative.
- The inspector (Phase 1) can read `retrieval_trace` directly. It already records candidates,
  exclusions, selection, and plugin + sidecar timings.
