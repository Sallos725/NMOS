# Phase 0A — PocketRisu Host Spike Runbook

This runbook is for the **real PocketRisu runtime**. It is not replaceable by unit tests.

Read `docs/phases/PHASE-0.md` first.

## 1. Start the optional local collector

From the repository root:

```bash
python tools/spike_collector.py --host 0.0.0.0 --port 8765
```

Health check:

```bash
curl http://127.0.0.1:8765/health
```

If PocketRisu runs on another machine, use the collector machine's LAN/Tailscale address in the
plugin's `collector_url`.

PocketRisu must be opened from a **secure context** (`http://localhost…` or HTTPS via PocketRisu
Remote Access). Over plain-HTTP LAN addresses V3 plugins do not load at all (HOST-FACTS Q5, H8).

Optional stub model (no API key needed; can force failures for S12):

```bash
python tools/spike_stub_llm.py --host 127.0.0.1 --port 8766
curl -X POST http://127.0.0.1:8766/control -d '{"fail_next": 2, "fail_status": 500}'
```

Point PocketRisu "Custom API" at `http://127.0.0.1:8766/v1/chat/completions`.

The collector is **throwaway Phase 0A tooling**, not the NMOS production sidecar.

## 2. Load the spike plugin

Use:

```text
adapters/pocketrisu-spike/nmos-host-spike.js
```

Configure:

- `collector_url`: e.g. `http://100.x.y.z:8765/spike` or blank to log locally only.
- `scenario`: label for the next dump, e.g. `S1-before`.
- `include_raw_snapshot`: `1` only if you intentionally want the local collector to store message
  bodies; use `0` for metadata/manifest-only capture.
- `skip_output_manifest`: leave `0` so every `output` observation carries a full manifest.

Menu actions: **NMOS Spike: Dump snapshot**, **NMOS Spike: Hash benchmark**, **NMOS Spike: Reset
request counters**. Scripted runs can trigger the same actions by posting
`{ type: 'nmos-spike-action', action: 'dump' | 'hashBenchmark' }` from the host page to the plugin iframe.

The plugin's `beforeRequest` hook must return the prompt unchanged.

## 3. Evidence naming

For a scenario, create at least:

```text
S1-before
S1-after
```

Set the plugin `scenario` argument before pressing **NMOS Spike: Dump snapshot**.

Automatic `beforeRequest` and `output` observations are also sent to the collector when configured.

Collector files are written under:

```text
fixtures/host/incoming/
```

Do not commit sensitive RP content unless anonymized.

## 4. Run scenarios

Perform the exact S1–S14 scenarios defined in `docs/phases/PHASE-0.md`.

Recommended order:

1. S1 normal send/reply
2. S2 reroll
3. S3 swipe switch
4. S4 continue
5. S5 edit old user message
6. S6 edit old AI message
7. S7 delete middle message
8. S8 disable/hide-before
9. S9 branch
10. S10 import/reload
11. S11 auxiliary request
12. S12 forced failure/retry/fallback
13. S13 group chat
14. S14 1,000-message synthetic/large chat

For mutation scenarios, dump **before and after**.

## 5. S14 performance capture

Generate an importable synthetic chat and import it through the chat import button:

```bash
python tools/make_synthetic_chat.py --messages 1000 --output nmos-s14-synthetic-chat.json
```

For the large chat, the dump record must include:

```text
getChatFromIndex elapsed ms
serialized byte size
message count
crypto.subtle availability
manifest/hash elapsed ms
```

Run more than once if practical and record the environment.

## 6. Lua request-trigger spot check

Q7 specifically asks whether common Lua `request` triggers rewrite injected/system messages.

Phase 0A does not inject NMOS memory. If needed, use a temporary clearly-marked test system message
only for this specific measurement and remove it immediately afterward. Do not turn it into
production behavior.

## 7. After the run

Codex/owner should:

1. review `fixtures/host/incoming/*.json` (`python tools/spike_report.py fixtures/host/incoming`
   prints per-scenario observations and before/after manifest diffs);
2. anonymize/copy durable fixtures into `fixtures/host/`;
3. complete `docs/HOST-FACTS.md`;
4. compare results against `ARCHITECTURE.md §4`;
5. record any correction;
6. resolve O3 and O4 explicitly.

Only then may `docs/STATUS.md` advance to Phase 0B.
