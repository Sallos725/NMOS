---
name: peer-review
description: Use in NMOS after implementing a material change (reconciliation, source history, membership, retrieval or injection, packets, migrations, auth, deployment) and before reporting it done or opening its PR - gets one read-only Codex review through .ai/scripts/peer-review (AGENTS.md §14).
---

# Codex peer review

The rule is `AGENTS.md §14`; the details are `.ai/README.md`. Skip this for trivial edits (docs wording,
typos, test-only renames) and say that you skipped it.

1. Commit or at least finish the change, and run its tests first. The reviewer sees the diff, not your
   intent.
2. Run it in the background (it takes minutes) from the checkout that holds the change. Claude Code's
   sandboxed Bash cannot start Codex's own sandbox, so pass `--inline` and attach what the reviewer needs:

   ```bash
   python3 .ai/scripts/peer-review codex review --base origin/main --inline \
     --attach AGENTS.md --attach docs/phases/PHASE-N.md --attach <touched file> ... \
     "<the path and the property to check, e.g. reroll and swipe invalidation in the fold>"
   ```

   Use `architecture` or `security` instead of `review` for a design or a sensitive-flow question. Stay
   under the 400,000-character limit: attach the phase spec and the touched files, not the whole tree.
   If the run stops on a sensitive or ignored file, leave it out; never attach `.env` or a database.
3. Classify every finding as confirmed, partial or unsupported by reading the cited code yourself. Fix
   what is confirmed and rerun the tests. An `ARCHITECTURE.md §9` question goes to the owner.
4. Report in the reply and the PR body: that Codex reviewed (inline, with which attachments), what you
   fixed, what you rejected and why. One review per change: do not rerun it to get a cleaner answer, and
   never let Codex call Claude back.

If `codex` is missing or its login fails, say so and continue without the review.
