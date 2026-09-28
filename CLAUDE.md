# CLAUDE.md — NMOS

The canonical implementation-agent instructions are in **`AGENTS.md`**.
Read `AGENTS.md`, `ARCHITECTURE.md`, the current phase file, and `docs/HOST-FACTS.md` before making changes.

When Claude leads a material change, get one Codex review before calling it done (`AGENTS.md §14`); the
project skill `peer-review` has the steps. On the owner's host Codex's sandbox cannot start (restricted user
namespaces), so Codex needs `--inline`.

The original Claude-generated operating draft is retained at `docs/reference/CLAUDE-original.md` for provenance only.
