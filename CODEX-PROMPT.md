# Codex handoff prompt

The repository is designed so this can be the entire initial request:

> **Build NMOS. Follow `AGENTS.md` and the current phase exactly. Work autonomously until you hit a real evidence/owner-decision boundary.**

Expected behavior:

- Codex reads the repository contract first.
- It works on Phase 0A only.
- It may improve/finish the spike and collector.
- It must not fabricate S1–S14 observations.
- Once live PocketRisu evidence is required, it stops with exact run instructions.
- It must not start Phase 0B merely because the production architecture is already documented.

After you provide the recorded fixtures back to Codex, use:

> **Continue NMOS from the recorded Phase 0A evidence. Reconcile `HOST-FACTS.md` and `ARCHITECTURE.md`, surface O3/O4 for my decision if unresolved, and do not unlock 0B until the Phase 0A exit criteria are genuinely met.**
