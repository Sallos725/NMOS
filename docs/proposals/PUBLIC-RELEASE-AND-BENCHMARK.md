# Public release and a benchmark — direction after the Archive Center comparison

> Proposal, 2026-09-29. It records the owner's direction and a proposed order. It does not authorize a phase:
> each item below still needs its `docs/phases/PHASE-N.md` and the owner's approval (AGENTS.md §7).

## Owner direction (2026-09-29)

After comparing NMOS with Archive Center 4.8.0 (`docs/perf/archive-center.md`), the owner decided to keep
developing NMOS, with these aims:

1. **Others can use it.** NMOS is today set up and used by its owner only.
2. **A result worth a paper** on long-term memory for LLMs, building on
   [Accountable memory](ACCOUNTABLE-MEMORY.md).
3. **A public announcement** in the role-play community, backed by numbers others can reproduce.
4. The owner's own role-play keeps running on NMOS (preferred there over Archive Center).

Documentation first (this page, the measurements and K33–K35), then the packet change below.

## What the comparison showed

- **Latency.** At 5,000 messages on PocketRisu v1.13.0, NMOS added ≈0.9–1.0 s per generation, Archive Center ≈8.5 s.
- **First sight.** NMOS syncs a long chat in seconds and extracts the recent 100 turns. Archive Center sends one
  critic call per past turn at once, which costs a paid model's price for the whole history.
- **Memory placed.** On the owner's M0 cases with the same extraction model, NMOS answered more on the long chat
  (main: 30 vs 25 of 40) with a tenth of the tokens. Archive Center answered more on the short one (sample 2:
  12 vs 9 of 15) with a fixed ≈36,000-character block, about a third of that whole chat.
- **The packet leaves its budget unused** (K33). Scaled recall limits ("fill") closed the gap on sample 2 at
  ≈3,900 tokens (12 of 15) and raised the main chat to 33 of 40. Above ≈8,000 tokens, stale facts came in.
- **Evaluation pitfalls.** A replay silently falls back to lexical recall on a projection mismatch, and a cold
  embedding model does the same on the request path (K34).

## Proposed order

### P1 — A packet that fills its budget (next)

Scale recall with the budget: excerpts, facts, events and threads, and excerpt length. Guard against stale facts,
the failure seen above ≈8,000 tokens. Choose the default budget from the host context. The owner's preset has
150,000 tokens of context; 4,000–8,000 tokens is 3–5 % of it.

- **Form.** A new packet policy (`packet-v9`) with its ADR, replayable against `packet-v8` on recorded traces.
- **Acceptance.** Draft: M0 main and sample 2 no worse on forbidden phrases than `packet-v8`, and better on cases
  needing memory. Latency within the current margin at 10,000 messages. Vectors on in every evaluation run.

### P2 — Cold embedding model (K34)

Measure how often production requests lose vectors. Then pick one fix: keep-alive guidance, a warm-up ping from the
worker, or a status-tab warning. Small; may ride along with P1.

### P3 — A public benchmark

The owner's chats cannot be published (the repository is public). A benchmark needs:

- **Synthetic long role-play chats in Korean.** Written or generated for the purpose, with the shapes real chats
  have: status blocks, edits and swipes, secrets, name variants, several hundred turns.
- **Case sets per chat.** Gold and forbidden phrases, and answer-level questions.
- **Baselines.** No memory, a full-context window, a rolling summary, plain retrieval, NMOS, and Archive Center.
  Each is run as its authors ship it, and the method is published.
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

Archive Center's installers and in-app update are the bar to compare against (`docs/perf/archive-center.md`, "Setup").

### P5 — Announcement

After P1, P3 and P4: the benchmark, its method and data, a demo, and the release notes. Comparisons with other
plugins state their versions and settings and can be rerun by anyone.

## Open decisions for the owner

1. The place of this work relative to Phase 15 (export and restore, `docs/ROADMAP-1.0.md`).
2. P1's default budget, and whether it follows the host's context setting.
3. P3's scope: how many chats, who writes them, and the answer-level spend.
4. P4's platforms: desktop Docker only, or also Windows without Docker and Termux.
