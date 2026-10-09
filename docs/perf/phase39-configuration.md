# Phase 39 amendment 2 — explicit status configuration

Date: 2026-10-09. Scope: status parser configuration, card-name binding and named presets.
No model/provider calls, live 6113 writes, schema changes or new dependencies.

## Observed problem and correction

A fresh installation already had no default parser. The panel nevertheless saved status JSON with general
settings, and a blank field sent null, restoring file-backed rules. Rules without a card could run globally.
The owner required a blank default and explicit application of selected JSON to a character, with presets.

The panel now starts with a blank target, preset and draft; it displays saved bindings separately. JSON import,
preset selection/save and general Save do not activate the draft. Card Apply sends only the explicit target and
draft. An empty rules document disables that target; a blank draft does nothing. Older sidecars cannot receive
a fallback global write. Named presets are separate app_config data and travel in full-install archives.

The server validates before mutation and serializes card merges using a transaction advisory lock, including
when there is no existing parser row. Runtime construction and state rebuild complete before publication after
commit. Failed construction, save or reparse rolls back the parser/configuration path. The same template can be
applied to multiple cards without rule-ID collisions. Applying one card preserves the latest other-card rules.

Legacy unbound JSON remains visible but inactive, with a distinct effective parser version so previous global
observations cannot be reused. Already-bound documents keep their parser version. Raw source revisions are
unchanged. Binding is an exact display name, not a stable card ID: same-name cards share rules; values, history
and flags continue to read each conversation head's membership.

## Executed verification

- Plugin: 237 tests in 20 files, typecheck, and build passed. Build identifier: `0319794d06bd`.
  Pure/DOM checks cover blank startup, JSON import, preset selection/save/removal, general Save/close separation,
  invalid or failed writes, another card's payload exclusion and an older sidecar without the new contract.
- Focused sidecar: 125 tests passed in 74.80 s. The new tests first failed against the old implementation.
  Coverage includes concurrent card updates (one and separate app instances), stable IDs on reapply, card A/B
  and two chats of card A, disable-one-card, unchanged sources, preset-only no reload/rebuild/jobs, validation,
  startup with legacy global rows, malformed file preservation, archive restore and injected failures.
  Full sidecar: **1,518 passed**, two existing deprecation warnings, 918.48 s; database tests required, no skips.
  Updated-head CI is tracked separately in PR #291; earlier head results are not substituted.
- Archive roundtrip initially exposed a missing setting in the export allowlist; adding parser_presets fixed it.
  Presets now survive restart and archive restore without changing active rules or state.
- Read-only 6113 check: both existing rules have card bindings. Previous and new compilers both produce
  `e208d973e577d413`, two rules and no errors. Eight synthetic card/body combinations produce identical results:
  each matching card reads its example; the other card, an unrelated card and an absent name do not.
  This is compatibility evidence, not a real-chat replay or UI check. No write was made to 6113.
- The Inspector bar benchmark fixture now supplies an explicit synthetic card through sync, matching its rule.
  A 100-message bar fixture passed with 150 state observations and rendered status lanes. This is a smoke check,
  not a new performance gate. Historical performance results are not re-attributed to this changed source.

The first host attempt exposed a connection-only Save path that did not reload server configuration.
Two deterministic UI regressions failed before the fix and passed after it: a first successful connection now
loads status capabilities without reopening, and a failed connection switch cannot keep the previous sidecar's
Apply enabled. The draft and target remain intact. All 237 plugin tests, typecheck and build passed again.
The host harness also needed its own explicit local CORS setting; the first screenshot alone cannot separate
that setup error from the product issue. Both facts remain recorded; no production CORS setting changed.

## Review and evidence limits

High risk: status-source scope, derived-state rebuild, configuration atomicity and archive compatibility.
The lead reviewed the changed product files and direct parser/state/archive/UI callers. It checked that input
is displayed as text, authenticated endpoints retain their existing boundary, validation precedes activation,
card merges preserve unrelated rules, rollback preserves source rows, legacy observations cannot retain their
old version, templates cannot activate, and general Save cannot submit a draft. No extraction generation,
packet policy, host data or secret handling is added by this correction.

The prior AGE-76 gate and actual-model evidence belong to the frozen r4 source. This change requires its own
regression/CI results; it does not rerun paid providers. The actual isolated PocketRisu v1.13.0 panel passed nine checks in Chromium 1223, including first connection
without reopening, real file import, A Apply preserving B, preset save/reload/selection, and both validation
failure paths. At a 390 px desktop viewport the document and panel measured 390 px (no horizontal overflow).
[Recorded results and screenshots](../../fixtures/host/status-config-v1.13.0-2026-10-09/README.md).
This does not verify mobile Safari, the native host package, generated answers or the owner's live UI. The current 6113 deployment remains fb095aa with packet-v18 and the approved watch keys.
