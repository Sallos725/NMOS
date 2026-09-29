# Public release and a benchmark — direction after a comparison with another memory plugin

> Proposal, 2026-09-29. It records the owner's direction and a proposed order. It does not authorize a phase:
> each item below still needs its `docs/phases/PHASE-N.md` and the owner's approval (AGENTS.md §7).

## Owner direction (2026-09-29)

The owner compared NMOS with another long-term memory plugin for RisuAI/PocketRisu ("plugin B"). The comparison and
its results are kept outside the repository. Afterwards the owner decided to keep developing NMOS, with these aims:

1. **Others can use it.** NMOS is today set up and used by its owner only.
2. **A result worth a paper** on long-term memory for LLMs, building on
   [Accountable memory](ACCOUNTABLE-MEMORY.md).
3. **A public announcement** in the role-play community, backed by numbers others can reproduce.
4. The owner's own role-play keeps running on NMOS.

Documentation first (this page, `docs/perf/packet-fill.md`, K33–K35), then the packet change below.

## What NMOS learned from it

- **Latency.** At 5,000 messages on PocketRisu v1.13.0, NMOS adds ≈0.9–1.0 s per generation.
- **First sight.** NMOS syncs a long chat in seconds and extracts its recent 100 turns; the rest only on request, so
  connecting a long chat does not send a paid model the whole history at once. That default is worth keeping.
- **The packet leaves its budget unused** (K33). A fixed memory block several times larger than NMOS's packet
  answered more on a short chat. Recall that grows with the budget, raw excerpts and facts only, closed that gap on
  the owner's M0 cases at ≈3,000–4,000 tokens. Growing open threads and secrets too placed stale lines above
  ≈8,000 tokens.
- **Evaluation pitfalls.** A replay silently falls back to lexical recall on a projection mismatch, and a cold
  embedding model does the same on the request path (K34).

## Proposed order

### P1 — A packet that fills its budget (next)

Scale recall with the budget: raw excerpts in number and length, and facts up to twice today's limit. Open threads,
events and secrets keep their limits. The default budget is fixed (4,000), not a share of the host's context.
Spec: `docs/phases/PHASE-15.md` (Phase 15, approved 2026-09-29).

### P2 — Cold embedding model (K34)

Measure how often production requests lose vectors. Then pick one fix: keep-alive guidance, a warm-up ping from the
worker, or a status-tab warning. Small; may ride along with P1 (Phase 15 Q5).

### P3 — A public benchmark

The owner's chats cannot be published (the repository is public). A benchmark needs:

- **Synthetic long role-play chats in Korean.** Written or generated for the purpose, with the shapes real chats
  have: status blocks, edits and swipes, secrets, name variants, several hundred turns.
- **Case sets per chat.** Gold and forbidden phrases, and answer-level questions.
- **Baselines.** No memory, a full-context window, a rolling summary, plain retrieval, NMOS, and other memory
  plugins as their authors ship them. The method is published.
- **Two levels of scoring.** What the memory places (as M0 does), and what a response model answers with it
  (paid; budgeted per run as in `docs/perf/stage4-leak-pilot.md`).

The benchmark serves both the paper and the announcement. Candidate contributions for a paper:

1. a Korean long-role-play memory benchmark;
2. accountable selection under a budget, compared with fixed blocks;
3. a source ledger that follows edits, swipes and branches;
4. packets that respect who knows what.

### P4 — Installation for other users

Today NMOS needs Docker, PostgreSQL with pgvector, and model endpoints configured by hand. A minimum for others:

- one command that brings up the sidecar and its database;
- a first-run guide in the panel (sidecar address, extraction and embedding models, a connection test);
- versioned plugin updates.

Other plugins ship per-platform installers and in-app updates; that is the bar.

A user moving from another memory plugin needs no chat migration: NMOS reads the chat from the host. What such a
user may want to bring is what they curated there, such as corrected memories or an imported source work. That
would be owner input with its own source kind, never facts without a source revision (invariant 1). This is a
candidate, not planned.

### P5 — Announcement

After P1, P3 and P4: the benchmark, its method and data, a demo, and the release notes.

## Open decisions for the owner

1. P3's scope: how many chats, who writes them, and the answer-level spend.
2. P4's platforms: desktop Docker only, or also Windows without Docker and Termux.
3. Whether any comparison with other plugins is ever published, and how they are named.
