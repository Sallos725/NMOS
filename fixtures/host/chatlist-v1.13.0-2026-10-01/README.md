# The host's chat list through the plugin API on PocketRisu v1.13.0 (C10 host evidence)

Real observations from an isolated PocketRisu `ghcr.io/pocketrisu/pocketrisu:latest` (v1.13.0, image
`e3fc431541a9`, the version the owner runs), port 6311, a synthetic save, headless Chromium 1223 (Playwright). No chat
was sent and no model was called; the owner's instance was not touched. Host evidence for C10 of
`docs/proposals/IDEA-SURVEY-2026-09-29.md` (Linear AGE-4), taken outside a phase; no NMOS code changed.

- Run: `docker run -d --name age4-probe --user 1000:1000 -e PORT=6311 -p 127.0.0.1:6311:6311 -v <dir>/save:/app/save
  -v <dir>/backups:/app/backups ghcr.io/pocketrisu/pocketrisu:latest`, `node first.mjs` (initializes the save), stop
  the container, `python seed.py <dir>/save` (with `msgpack`), start it, then `node drive.mjs install
  <repo>/adapters/pocketrisu-spike/nmos-chatlist-probe.js`, `node drive.mjs measure boot 5`, `node drive.mjs open 0
  "synthetic 10000" open10k`, `node drive.mjs open 0,0 "synthetic 10000,synthetic 5000" open15k`, `node trash.mjs`,
  `node delchat.mjs`, `node drive.mjs measure after-delete 2`, each with `PORT=6311 PROFILE=<dir>/profile`. The `.mjs`
  scripts need `playwright-core`; `lib.mjs` opens the page with a persistent profile and answers the test password
  prompt.
- `seed.py` writes three synthetic characters (하나, 카이토, 유이) into the stopped save: 하나 with chats of 40, 10,000,
  5,000 and 40 messages, 카이토 with two of 40, 유이 with one of 40; about 167 characters per message, synthetic
  text only.
- `adapters/pocketrisu-spike/nmos-chatlist-probe.js` (a V3 plugin named `age4_probe`, not NMOS) measures, when its
  `go` argument changes, from inside the plugin frame: `getDatabase(['characters'])` (end to end, the host's copy and
  the frame transfer), every chat's id, message count and `_placeholder` flag in what it returned,
  `getDatabase(['characterOrder'])`, and a `getCharacterFromIndex(i)` loop over every character. `drive.mjs` sets the
  argument through the host's `setArg`, answers the "db" permission prompt, and records the host page's long tasks
  (`PerformanceObserver`, type `longtask`) while the probe runs. `open` opens the named chats in the host UI first,
  in one page load.
- `trash.mjs` presses **Move to trash** in 유이's character settings (the host's default character delete);
  `delchat.mjs` deletes the chat 카이토 2 with its trash icon in the chat list and confirms.
- `results.txt` is the probe's output, in the order run.

The machine was under other load during the run (another evaluation with three PocketRisu instances and headless
browsers; load average 2–4, about 8 GB of 31 GB free), so the timings are indicative.

What they show is written up in `docs/HOST-FACTS.md` ("The host's chat list", 2026-10-01, H22).
