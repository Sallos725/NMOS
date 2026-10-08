# Sending a request body from the plugin frame on PocketRisu v1.13.0 (Phase 38 step 2)

Real observations from an isolated PocketRisu `ghcr.io/pocketrisu/pocketrisu:latest` (the local image of 2026-09-27,
v1.13.0, the version the owner runs; not pulled again), port 6191, an empty save dir, headless Chromium 1223 and
Firefox 1543 (Playwright). No chat was sent and no model was called; the owner's instances were not touched.

- Run: `docker run -d --name p38-upload-risu --network host -e PORT=6191 -v <dir>/save:/app/save
  ghcr.io/pocketrisu/pocketrisu:latest`, `python3 sink.py 8831`, `node reinstall.mjs
  <repo>/adapters/pocketrisu-spike/nmos-upload-probe.js`, then `node run.mjs <action>…` (Chromium) and
  `FF=1 node run.mjs <action>…` (Firefox, after `FF=1 node reinstall.mjs …`). The `.mjs` scripts need
  `playwright-core`; `lib.mjs` opens the page with a persistent profile.
- `sink.py` answers `POST` with the body's length and SHA-256 as JSON, CORS open; a JSON body `{"data": base64}` is
  decoded first, so both forms are hashed as the bytes the frame meant. It logs each request's user agent.
- `adapters/pocketrisu-spike/nmos-upload-probe.js` (a V3 plugin, not NMOS) draws one button per action:
  `<route>-<form>-<MB>` builds that many MB of deterministic bytes in the frame, hashes them with `crypto.subtle`, and
  POSTs them through `risuai.nativeFetch` on the route (`server`: `networkRoute: 'local_network'`; `direct`: the
  default) as a `Uint8Array` (`binary`), a `Blob` (`blob`) or `{"data": base64}` (`base64`); it logs the sink's length
  and hash against its own and the time to the answer.
- `results.txt` is the output of both browsers and the sink's user agents.

Not observed: WebKit and mobile browsers (the iPhone is not a target, PHASE-38 Q3).

What they show is written up in `docs/HOST-FACTS.md` ("Sending a request body from the plugin frame", 2026-10-08, H23).
