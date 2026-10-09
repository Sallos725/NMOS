# Restore from the panel while NMOS runs (PHASE-38 step 5)

Measured 2026-10-08 on the owner's host with `tools/bench_restore.py` (code of `29f537b`; the restore path is the same
since `fc8134c`), against the test PostgreSQL 16 (:5436), one throwaway database per install. No model is called.

## Method

- **Source:** a synthetic chat of N messages (`bench_scale.build_chat`: Korean prose of ≈1.5 kB per reply) and one
  extraction generation with an assertion per turn (`bench_scale.add_generation`). Its whole-install archive is
  exported as the panel's **Export everything** writes it.
- **Target:** a running install (in-process `TestClient`, request parsing included, network excluded) with two chats
  of its own. The archive goes through the panel's routes: chunks of 8 MB in base64 (H23), the check, the restore.
- **While it restores:** one thread syncs a new turn of the first chat every 0.1 s (a write that draws a shared id);
  another recalls in the second chat every 0.2 s (a read that records the request). Their times inside and outside
  the restore (from its POST to the `restored` state, which includes the startup steps after the commit) are reported.

## Results

| Messages | Archive | Upload | Check | Restore | Sync during (p50 / max) | Sync outside (p50 / max) | Recall during (p50 / max) | Recall outside (p50 / max) |
|---:|---:|---:|---:|---:|---|---|---|---|
| 1,000 | 0.43 MB | 0.01 s | 0.05 s | 0.86 s | 19 / 455 ms | 17 / 39 ms | 15 / 15 ms | 15 / 20 ms |
| 10,000 | 4.21 MB | 0.09 s | 0.20 s | 5.1 s | 19 / 1,585 ms | 16 / 19 ms | 18 / 26 ms | 14 / 27 ms |

- **Recall does not wait.** In another chat it took the same time during the restore as outside it.
- **A sync waits only while the restore's transaction holds the shared ids' sequences** (1.6 s at 10,000 messages,
  the longest single wait). The rest of the restore, the startup steps for the new rows (normalized text, turn data,
  state, missing jobs), does not hold them: the syncs after the commit took their usual time.
- **A recall in the chat whose sync is waiting waits with it.** The sync holds that conversation's row, and the
  request's record names it. In the plugin that recall comes after the sync in the same request, so the request waits
  as a whole and its deadline sends the reply without memory (fail-open). A first version of this benchmark recalled
  in the syncing chat and measured that wait (≈0.44 s at 1,000) as the recall's.

## What it does not measure

The host's proxy (H23 measured an upload through it: 8 MB of base64 in ≈1.1 s in Chromium, so a 2 GB archive in a few
minutes), the owner's own archives (step 6), and archives with embeddings (larger files; the same restore path).
