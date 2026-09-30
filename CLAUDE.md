# CLAUDE.md — NMOS

The canonical implementation-agent instructions are in **`AGENTS.md`**.
Read `AGENTS.md`, `ARCHITECTURE.md`, the current phase file, and `docs/HOST-FACTS.md` before making changes.

Every user-facing chat message in this project must be written in Korean, regardless of any global
tone/persona instructions layered in from outside this repo. This applies only to chat replies — repo
docs, commit messages, and PR descriptions stay in English as usual.

After any non-trivial implementation change, use the project `peer-review` skill before reporting the
work done. The default review is scoped to the diff against the task base; do not perform a repository-wide
audit unless the owner explicitly requests one.

The scoped Claude self-review is the review; no change requires an independent Codex review. Mark a change
the `AGENTS.md §14` list calls high risk as such in the report and PR (the owner tracks those in Linear).
Run a Codex review only when the owner asks for one; on the owner's host it needs `--inline` because
Codex's sandbox cannot start with the current user-namespace restriction.

The original Claude-generated operating draft is retained at `docs/reference/CLAUDE-original.md` for provenance only.
