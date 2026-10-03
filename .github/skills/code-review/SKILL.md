---
name: code-review
description: Review NMOS pull requests for correctness, regressions, architectural invariant violations, phase-scope violations, data-integrity risks, fail-open regressions, security issues, and missing tests. Use for pull request and code review. Follow AGENTS.md §14 and keep the review scoped to the diff and its minimum dependency cone.
---

# NMOS code review

Review this change as an independent, read-only reviewer.

The canonical review policy is `AGENTS.md §14`. Follow it rather than inventing a separate review process.

## 1. Read the relevant authority first

Before judging a change, read only the authority needed to understand it:

1. `AGENTS.md`, especially §§2–5, §12, and §14.
2. `ARCHITECTURE.md` for invariants and architectural decisions affected by the diff.
3. `docs/STATUS.md` for the current authorized scope.
4. The current or directly relevant `docs/phases/PHASE-N.md`.
5. `docs/HOST-FACTS.md` if the change depends on PocketRisu behavior.
6. Relevant ADRs when the changed path implements or changes an architectural decision.

Reference documents do not authorize implementation outside the current phase.

## 2. Review the diff, not the repository

Start with the pull request diff.

Review all changed code, then expand only when necessary into the minimum dependency cone:

- direct callers and callees;
- shared interfaces and types used by changed code;
- directly relevant tests;
- schema and migrations used by the changed path;
- relevant phase or architecture documentation.

Do not turn a pull-request review into a repository-wide audit.

Do not inspect generated or bulky material by default, including:

- `fixtures/model/**`;
- `dist/**`;
- large JSON or JSONL artifacts;
- historical changelogs;
- unrelated documentation.

Read these only when the changed code specifically depends on them.

## 3. Prioritize correctness over style

Look primarily for actionable defects or regressions:

- behavior that contradicts the current phase specification;
- violations of an `ARCHITECTURE.md` invariant;
- incorrect state transitions or reconciliation;
- loss, mutation, or corruption of raw or canonical evidence;
- provenance or identity mistakes;
- schema, migration, upgrade, or backfill hazards;
- retrieval or injection changes that can select the wrong memory;
- character/world knowledge isolation failures;
- stale semantic state entering a packet;
- request-path latency or timeout regressions;
- fail-open behavior becoming fail-closed;
- host chat mutation;
- security, authorization, secret, or sensitive-logging problems;
- generation/versioning mistakes for derived data;
- missing tests for a behavior changed by the diff;
- documentation or `docs/STATUS.md` claims that no longer match reality.

Do not report subjective style preferences unless they create a concrete correctness, maintenance, or reliability risk.

Do not propose speculative abstractions or future-phase features as review fixes.

## 4. Protect NMOS invariants explicitly

Pay special attention to these guarantees when the changed path touches them:

- raw evidence is not destroyed;
- derived memory remains rebuildable;
- the response path does not write canonical memory;
- unknown, ambiguous, and conflicting states remain representable;
- current and historical state remain answerable;
- character knowledge is not treated as world knowledge;
- inactive sources do not affect generated packets;
- retrieval and utilization remain distinct;
- automatic semantic claims retain provenance;
- sidecar or embedding failure fails open;
- stale semantic state is not knowingly injected;
- the plugin never mutates host chat data.

A proposed fix must not weaken another invariant.

## 5. Treat evidence claims conservatively

Do not assume that:

- a unit test proves PocketRisu host behavior;
- synthetic fixtures prove a live-host property;
- a benchmark result exists unless it is recorded;
- a model-dependent behavior is verified unless the required model run was actually performed.

If a change is code-complete but still requires live-host, model, performance, or other evidence, report the missing evidence rather than treating the acceptance criterion as satisfied.

Never recommend fabricating or inferring measurements.

## 6. Identify high-risk changes

Classify a change as **high risk** when it can materially affect:

- stored data, migrations, upgrades, backfills, deletion, or recovery;
- reconciliation or immutable source history;
- membership, canon, identity, or provenance;
- authentication, secrets, authorization, or sensitive logging;
- retrieval/injection semantics affecting selection, isolation, provenance, or fail-open behavior;
- deployment compatibility where a defect could corrupt persisted state or weaken a security boundary.

For a high-risk change, explicitly identify the guarantee at risk and verify the relevant tests, upgrade paths, fixtures, or fail-open behavior.

This classification is informational. Do not expand the review scope merely because a change is high risk.

## 7. Evaluate tests against behavior

Check whether tests actually pin the behavior changed by the diff.

Prefer tests that would fail for the specific regression being reviewed.

For bug fixes, look for a regression test when practical.

Do not demand redundant tests for behavior already covered at the appropriate layer.

Do not substitute synthetic tests for required live-host or model evidence.

## 8. Report only actionable findings

For each finding:

- identify the affected file and line or smallest useful range;
- state the concrete condition that triggers the problem;
- explain the observable consequence;
- identify the violated requirement, invariant, or expected behavior when applicable;
- suggest the smallest reasonable correction or missing test.

Prefer findings that the author can act on directly.

Do not duplicate the same root cause across multiple comments.

Do not report hypothetical problems without a plausible execution path.

If uncertainty remains, clearly distinguish a suspected issue from a demonstrated defect.

## 9. Respect scope and owner decisions

A review comment does not authorize new scope.

Do not recommend:

- implementing an unauthorized phase;
- weakening an architectural invariant;
- adding a runtime dependency without owner approval;
- choosing an unresolved owner decision;
- changing verified PocketRisu semantics based on assumption.

When a real owner decision is required, identify the decision boundary instead of selecting an option.

## 10. Review outcome

The goal is a small set of high-signal findings about defects, regressions, missing evidence, or missing tests.

A clean review is preferable to filling the review with low-value comments.
