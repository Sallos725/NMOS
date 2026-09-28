# Canon sources on PocketRisu v1.13.0 (Phase 14 step 2)

Real observations from an isolated PocketRisu `ghcr.io/pocketrisu/pocketrisu:latest` (v1.13.0, image
`e3fc431541a9`, the one the owner runs), port 6141, a fresh save directory, headless Chromium 1223, the local stub
chat model (`tools/spike_stub_llm.py`). All data is synthetic (`seed.py`); the owner's instance was not touched.

- `seed.py` wrote the save's `database/database.bin` with the container stopped. It holds:
  - one character (`desc`, `personality`, `scenario`, a greeting and one alternate);
  - a character lorebook: a keyed entry, an always-active `constant` entry, a folder and a keyed entry in it;
  - a chat with an author's note and a local lorebook entry, bound to a persona that has a `personaPrompt`;
  - an enabled module with one keyed lorebook entry.

  `seed.py 10000 5000` gave the chat 10,000 messages and added a second chat of 5,000.
- `adapters/pocketrisu-spike/nmos-canon-probe.js` was installed through Settings → Plugins → Import. At every
  request it logs shapes only: which calls exist, their times, field lengths and counts, 12-hex content hashes, and
  whether each canon text is in the outgoing prompt. It returns the prompt unchanged.
- `probe.mjs` sent four messages: the first three named the keyed entries (character, module, chat), and the fourth
  followed an edit of the card's `desc` through the host's own character write (`__pluginApis__.setChar` on the main
  window). The "full database" permission dialog of the first `getDatabase` was answered Yes. `probe10k.mjs` sent
  three messages on the 10,000-message chat.
- `observations.jsonl` and `observations-10k.jsonl` are the probe's lines, one per request.

What they show is written up in `docs/HOST-FACTS.md` ("Canon sources", 2026-09-28).
