# Contributing to NMOS

Thanks for helping. NMOS is a small project in beta; the most useful contributions are clear bug reports from real
chats and focused pull requests.

## Reporting a problem

Use the [issue forms](https://github.com/Sallos725/NMOS/issues/new/choose). The most helpful details are:

- the NMOS version (the panel's Status tab) and how you run it (Docker or the portable bundle);
- your PocketRisu version and how you open it (`localhost`, HTTPS / Remote Access, or a tunnel);
- what you did in the chat (edit, reroll, swipe, branch, import…) and what NMOS recalled or missed;
- the panel's **Inspector** view of the turn, if it shows the problem.

Remove API keys, tokens and anything private from screenshots and logs. Security problems go through the
[security policy](SECURITY.md), not a public issue.

## Pull requests

Development setup is in the README's [Develop](../README.md#develop) section. Before opening a pull request:

```bash
cd apps/sidecar && uv sync && uv run pytest               # needs the compose Postgres on :5436
cd adapters/pocketrisu-plugin && npm ci && npm test && npm run typecheck && npm run build
```

Design and decisions live in `ARCHITECTURE.md`, `docs/adr/` and `docs/phases/`; a change to how memory is stored,
recalled or injected usually needs a phase spec or an ADR first, so please open an issue to discuss it. Keep a pull
request to one change, with tests, and describe what it changes for a user.

By contributing you agree that your contribution is licensed under the [MIT License](../LICENSE).
