# The panel's Export on PocketRisu v1.13.0 (Phase 16 step 5)

A real-host smoke of the NMOS panel's two Export buttons (ADR 0050) on an isolated PocketRisu
`ghcr.io/pocketrisu/pocketrisu:latest` (v1.13.0), port 6181, the synthetic save of
`../download-v1.13.0-2026-09-29/`, headless Chromium 1223. The sidecar ran from `main` after step 3 on a copy of a
synthetic smoke database (one chat, 97 revisions), at `http://127.0.0.1:8841`, no model configured. The owner's
instance was not touched.

- Run: `node reinstall.mjs <repo>/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js` (build `f371c057201b`), then
  `node smoke.mjs server`. The script answers the host's permission dialogs, sets the sidecar address and the
  `server` route in the panel's Settings tab (the host page's `__pluginApis__.setArg` does not reach a V3 plugin's
  args), clicks **전부 내보내기** (Export everything) there, then opens the first conversation in the Inspector tab
  and clicks **이 대화 내보내기** (Export this chat), and logs each browser download's name, size and SHA-256 and the
  panel's message.
- `results.txt` is a summary of its output: the panel found, the settings saved, each download's line and the
  panel's last message (the script also prints the args it tried and the panels' text). The two files were checked afterwards: the whole-install file's tables are the same
  bytes as `python -m nmos_sidecar.archive export` of the same database; it restored into a fresh database, which
  exported the same bytes again; the chat's file passed `restore --check` (one conversation).

Not observed in this run: phones. The owner's iPhone was checked on 2026-10-01 (`docs/HOST-FACTS.md`, K38).
