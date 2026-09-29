# Saving a file from the plugin frame on PocketRisu v1.13.0 (Phase 16 step 2)

Real observations from an isolated PocketRisu `ghcr.io/pocketrisu/pocketrisu:latest` (v1.13.0, the version the owner
runs), port 6181, a copy of the synthetic save of `../canon-v1.13.0-2026-09-28/`, headless Chromium 1223 and Firefox
1543 (Playwright). No chat was sent and no model was called; the owner's instance was not touched.

- Run: `docker run -d --name p16-risu --network host -e PORT=6181 -v <dir>/save:/app/save
  ghcr.io/pocketrisu/pocketrisu:latest`, `python3 bytes.py 8830`, `node reinstall.mjs
  <repo>/adapters/pocketrisu-spike/nmos-download-probe.js`, then `node run.mjs info small delayed server1 direct1
  server30 direct30 link` (Chromium) and `FF=1 node run.mjs info small server1 direct1 server30 direct30` (Firefox).
  The `.mjs` scripts need `playwright-core`; `lib.mjs` opens the page with a persistent profile and answers the test
  password prompt.
- `bytes.py` answers `GET /bytes?mb=N` with N MB of deterministic bytes as an attachment (`Content-Disposition`), their
  SHA-256 in `X-Sha256`, CORS open.
- `adapters/pocketrisu-spike/nmos-download-probe.js` (a V3 plugin, not NMOS) draws one button per action in its
  fullscreen container: `small` saves a 10-byte Blob through `<a download>`; `delayed` does so 8 s after the click;
  `serverN` / `directN` fetch N MB through `risuai.nativeFetch` (with and without `networkRoute: 'local_network'`),
  hash the `arrayBuffer()` with `crypto.subtle`, log it against the server's hash and save it as a Blob; `link` clicks
  an `<a href=… download>` to the server; `info` logs the frame's origin and secure-context state.
- `run.mjs` opens the probe from Settings, clicks each action, waits up to 60 s for a browser download, and logs its
  name, size and SHA-256 (of the file Playwright saved) and the page's frames after the action. The iframes' `sandbox`
  and `allow` attributes are read from the host page's DOM.
- `results.txt` is the output of both runs.

Not observed: WebKit (Playwright's WebKit build does not start on this machine: `libevent-2.1.so.7` missing) and
mobile browsers.

What they show is written up in `docs/HOST-FACTS.md` ("Saving a file from the plugin frame", 2026-09-29, H21).
