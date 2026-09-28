---
name: peer-review
description: MUST use in NMOS after any non-trivial implementation change and before reporting it done or opening its PR. Review only the diff and minimum dependency cone. Use Claude self-review by default; invoke one read-only Codex review through .ai/scripts/peer-review only when AGENTS.md §14 classifies the change as high risk. Never perform a repository-wide audit unless the owner explicitly requests one.
---

# Scoped peer review

The authority is `AGENTS.md §14`; `.ai/README.md` describes the external-review transport.

## 1. Finish and test the change first

Finish the intended slice and run its narrow tests plus the phase-required checks before review. Inspect
`git status` and do not absorb unrelated owner work into the review.

Trivial edits (wording, typos, test-only renames with no behavior change) may skip this workflow; say that
you skipped it.

## 2. Start from the diff, not the repository

Use the task base, normally `origin/main`:

```bash
git diff --name-only origin/main...HEAD
git diff origin/main...HEAD
```

Review every changed code path. Expand only when needed into:

- direct callers and callees;
- shared interfaces/types used by the changed path;
- directly relevant tests;
- schema/migrations when the changed path depends on them.

Do **not** inspect `fixtures/model/**`, `dist/**`, large JSON/JSONL artifacts, historical changelogs, or
unrelated documentation by default. Read one of them only when a changed path specifically depends on it.
Do not perform a repository-wide audit unless the owner explicitly asks for one.

## 3. Classify review risk

Treat the change as **high risk** when it can materially affect:

- stored data, schema, migrations, upgrades, backfills, deletion, or recovery;
- reconciliation, immutable source history, membership, canon, identity, or provenance;
- authentication, secrets, authorization, security boundaries, or sensitive logging;
- retrieval/injection semantics that change memory selection, isolation, provenance, or fail-open behavior;
- deployment compatibility where a mistake can corrupt persisted state or weaken a security boundary.

If none of those apply, perform the scoped Claude self-review, fix confirmed issues, rerun the relevant
checks, and stop. Do not call Codex merely because the change is non-trivial.

## 4. Escalate high-risk changes once

When Claude leads a high-risk change, run one independent Codex review from the checkout that holds the
change. On the owner's host Codex's sandbox cannot start, so use `--inline` and attach only what the
reviewer actually needs:

```bash
python3 .ai/scripts/peer-review codex review --base origin/main --inline \
  --attach AGENTS.md --attach docs/phases/PHASE-N.md --attach <touched file> ... \
  "<changed path and the specific high-risk property to check>"
```

Use `architecture` instead of `review` for a design/invariant question and `security` for a sensitive
flow. Stay under the 400,000-character inline limit. Never attach `.env`, databases, secrets, the whole
tree, generated bundles, or large fixture/model artifacts unless they are strictly required and permitted.

One external review per change. Do not rerun it to get a cleaner answer, and never let Codex call Claude
back.

If `codex` is unavailable or authentication fails, report that fact and continue without replacing it
with a repository-wide audit.

## 5. Verify findings

Treat every review finding as a hypothesis. Classify it as confirmed, partial, or unsupported by reading
the cited code or reproducing it. Fix confirmed defects, rerun the relevant tests, and report:

- the base and review scope;
- whether the change was high risk;
- whether Codex was invoked;
- what was fixed;
- what was rejected and why;
- remaining risk.

An `ARCHITECTURE.md §9` question goes to the owner.
