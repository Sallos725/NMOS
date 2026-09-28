# CLAUDE.md — NMOS

The canonical implementation-agent instructions are in **`AGENTS.md`**.
Read `AGENTS.md`, `ARCHITECTURE.md`, the current phase file, and `docs/HOST-FACTS.md` before making changes.

When Claude leads a material change, the independent reviewer is Codex (`AGENTS.md §14`):
`python3 .ai/scripts/peer-review codex review --base origin/main <focus>`.

The original Claude-generated operating draft is retained at `docs/reference/CLAUDE-original.md` for provenance only.
