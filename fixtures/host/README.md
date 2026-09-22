# Host Fixtures

This directory contains **real PocketRisu Phase 0A observations**.

- `incoming/` is written by the throwaway local spike collector (git-ignored).
- `a14c911-2026-09-22/` holds the Phase 0A evidence run (see its `README.md`); it drives
  `apps/sidecar/tests/test_reconcile_fixtures.py`.
- Durable/anonymized fixtures should be copied to clearly named files such as:
  - `S01-normal-before.json`
  - `S01-normal-after.json`
  - `S02-reroll-before.json`
  - `S02-reroll-after.json`

Never fabricate a fixture to satisfy a test.

A fixture should normally contain:

```text
scenario label
observation kind
PocketRisu target metadata
manifest
timings
optional raw snapshot (only when intentionally captured)
```

Sensitive chat content should be removed/anonymized before committing.
