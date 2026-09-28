# CLAUDE.md — NMOS

The canonical implementation-agent instructions are in **`AGENTS.md`**.
Read `AGENTS.md`, `ARCHITECTURE.md`, the current phase file, and `docs/HOST-FACTS.md` before making changes.

After any non-trivial implementation change, use the project `peer-review` skill before reporting the
work done. The default review is scoped to the diff against the task base; do not perform a repository-wide
audit unless the owner explicitly requests one.

Only changes classified as high risk by `AGENTS.md §14` require an independent Codex review. For other
non-trivial changes, the scoped Claude self-review is sufficient. On the owner's host, a required Codex
review needs `--inline` because Codex's sandbox cannot start with the current user-namespace restriction.

The original Claude-generated operating draft is retained at `docs/reference/CLAUDE-original.md` for provenance only.
