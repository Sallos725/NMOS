# Starter Contents

> Historical (archived 2026-09-22): this describes the repository as originally packaged (Phase 0A only). For the
> current layout see `ARCHITECTURE.md §7` and `docs/STATUS.md`.

This starter intentionally contains only **Phase 0A executable scaffolding**.

```text
.
├── AGENTS.md
├── ARCHITECTURE.md
├── CLAUDE.md
├── CODEX-PROMPT.md
├── README.md
├── adapters/
│   └── pocketrisu-spike/
│       └── nmos-host-spike.js
├── docs/
│   ├── HOST-FACTS.md
│   ├── PHASE-0A-RUNBOOK.md
│   ├── STATUS.md
│   ├── adr/
│   │   └── README.md
│   ├── phases/
│   │   └── PHASE-0.md
│   └── reference/
│       ├── CLAUDE-original.md
│       ├── initial_narrative_memory_plan.md
│       └── ultimate_narrative_memory_architecture.md
├── fixtures/
│   └── host/
│       ├── README.md
│       └── incoming/
└── tools/
    └── spike_collector.py
```

No production sidecar/database/plugin scaffold exists yet because Phase 0B is locked by design.
